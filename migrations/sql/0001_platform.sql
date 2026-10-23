REVOKE CREATE ON SCHEMA public FROM PUBLIC;
CREATE TABLE principals (
    id uuid PRIMARY KEY,
    issuer text NOT NULL,
    subject text NOT NULL,
    enabled boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_principal_external UNIQUE (issuer,subject),
    CONSTRAINT ck_identity_lengths CHECK (length(issuer) BETWEEN 1 AND 2048 AND length(subject) BETWEEN 1 AND 255)
);
CREATE TABLE role_grants (
    principal_id uuid NOT NULL REFERENCES principals(id),
    role varchar(16) NOT NULL,
    version integer NOT NULL DEFAULT 1,
    revoked_at timestamptz,
    PRIMARY KEY(principal_id,role),
    CONSTRAINT ck_role CHECK (role IN ('operator','approver','auditor','admin')),
    CONSTRAINT ck_grant_version CHECK (version >= 1)
);
CREATE TABLE audit_streams (
    stream_id uuid PRIMARY KEY,
    last_seq bigint NOT NULL,
    last_hash varchar(64) NOT NULL,
    CONSTRAINT ck_stream_head CHECK (last_seq >= 0 AND last_hash ~ '^[0-9a-f]{64}$')
);
CREATE TABLE audit_events (
    event_id uuid PRIMARY KEY,
    stream_id uuid NOT NULL REFERENCES audit_streams(stream_id),
    seq bigint NOT NULL,
    event_type varchar(64) NOT NULL,
    schema_version integer NOT NULL,
    occurred_at timestamptz NOT NULL,
    actor_id uuid REFERENCES principals(id),
    trace_id varchar(32) NOT NULL,
    payload jsonb NOT NULL,
    prev_hash varchar(64) NOT NULL,
    hash varchar(64) NOT NULL,
    CONSTRAINT uq_audit_stream_seq UNIQUE (stream_id,seq),
    CONSTRAINT ck_audit_version_seq CHECK (seq >= 1 AND schema_version = 1),
    CONSTRAINT ck_audit_hash CHECK (prev_hash ~ '^[0-9a-f]{64}$' AND hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_audit_trace CHECK (trace_id ~ '^[0-9a-f]{32}$'),
    CONSTRAINT ck_audit_type CHECK (event_type IN ('identity.provisioned','identity.disabled','authorization.granted','authorization.revoked','authorization.denied'))
);

CREATE FUNCTION audit_canonical(v json) RETURNS text
LANGUAGE plpgsql IMMUTABLE STRICT SET search_path = pg_catalog, public AS $$
DECLARE result text; kind text := json_typeof(v);
BEGIN
    CASE kind
      WHEN 'object' THEN
        IF (SELECT count(*) <> count(DISTINCT key) FROM json_each(v)) THEN
          RAISE EXCEPTION 'Duplicate JSON keys' USING ERRCODE='22023';
        END IF;
        SELECT '{' || coalesce(string_agg(to_json(key)::text || ':' || public.audit_canonical(value), ',' ORDER BY key COLLATE "C"), '') || '}'
          INTO result FROM json_each(v);
      WHEN 'array' THEN
        SELECT '[' || coalesce(string_agg(public.audit_canonical(value), ',' ORDER BY ord), '') || ']'
          INTO result FROM json_array_elements(v) WITH ORDINALITY AS a(value,ord);
      WHEN 'number' THEN
        IF v::text !~ '^-?(0|[1-9][0-9]*)$' THEN
          RAISE EXCEPTION 'Only integer JSON numbers allowed' USING ERRCODE='22023';
        END IF;
        result := (v::text::numeric)::text;
      WHEN 'string' THEN result := to_json(v #>> '{}')::text;
      WHEN 'boolean' THEN result := v::text;
      WHEN 'null' THEN result := 'null';
      ELSE RAISE EXCEPTION 'Invalid JSON' USING ERRCODE='22023';
    END CASE;
    RETURN result;
END $$;

CREATE FUNCTION audit_append(p_stream uuid, p_type text, p_actor uuid,
                             p_trace text, p_payload text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
DECLARE
    payload_json json; payload_obj jsonb; canonical text;
    head public.audit_streams%ROWTYPE;
    eid uuid := gen_random_uuid(); stamp timestamptz := clock_timestamp();
    envelope json; digest text; normalized text;
BEGIN
    IF p_stream IS NULL OR p_type IS NULL OR p_trace IS NULL OR p_payload IS NULL
       OR octet_length(p_payload) > 8192 OR p_trace !~ '^[0-9a-f]{32}$'
       OR p_type NOT IN ('identity.provisioned','identity.disabled','authorization.granted','authorization.revoked','authorization.denied') THEN
       RAISE EXCEPTION 'Invalid audit input' USING ERRCODE='22023';
    END IF;
    payload_json := p_payload::json;
    canonical := public.audit_canonical(payload_json);
    payload_obj := canonical::jsonb;
    IF jsonb_typeof(payload_obj) <> 'object' THEN
       RAISE EXCEPTION 'Invalid audit payload' USING ERRCODE='22023';
    END IF;
    IF (SELECT count(*) FROM jsonb_object_keys(payload_obj)) <> 4
       OR NOT payload_obj ?& ARRAY['reason_code','aggregate_id','aggregate_version','evidence_ids']
       OR jsonb_typeof(payload_obj->'reason_code') <> 'string'
       OR (payload_obj->>'reason_code') !~ '^[A-Z][A-Z0-9_]{0,63}$'
       OR jsonb_typeof(payload_obj->'aggregate_id') <> 'string'
       OR (payload_obj->>'aggregate_id') !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
       OR jsonb_typeof(payload_obj->'aggregate_version') <> 'number'
       OR (payload_obj->>'aggregate_version') !~ '^(0|[1-9][0-9]*)$'
       OR jsonb_typeof(payload_obj->'evidence_ids') <> 'array' THEN
       RAISE EXCEPTION 'Invalid audit payload fields' USING ERRCODE='22023';
    END IF;
    IF jsonb_array_length(payload_obj->'evidence_ids') > 20
       OR EXISTS (SELECT 1 FROM jsonb_array_elements(payload_obj->'evidence_ids') a
                  WHERE jsonb_typeof(a) <> 'string' OR (a #>> '{}') !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$') THEN
       RAISE EXCEPTION 'Invalid evidence references' USING ERRCODE='22023';
    END IF;
    INSERT INTO public.audit_streams VALUES (p_stream,0,repeat('0',64)) ON CONFLICT DO NOTHING;
    SELECT * INTO STRICT head FROM public.audit_streams WHERE stream_id=p_stream FOR UPDATE;
    normalized := to_char(stamp AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"');
    envelope := json_build_object('event_id',eid::text,'stream_id',p_stream::text,
       'seq',head.last_seq+1,'event_type',p_type,'schema_version',1,'occurred_at',normalized,
       'actor_id',p_actor::text,'trace_id',p_trace,'payload',payload_json,'prev_hash',head.last_hash);
    digest := encode(sha256(convert_to(public.audit_canonical(envelope),'UTF8')),'hex');
    INSERT INTO public.audit_events VALUES (eid,p_stream,head.last_seq+1,p_type,1,stamp,
       p_actor,p_trace,payload_obj,head.last_hash,digest);
    UPDATE public.audit_streams SET last_seq=head.last_seq+1,last_hash=digest WHERE stream_id=p_stream;
    RETURN envelope::jsonb || jsonb_build_object('hash',digest);
END $$;

GRANT USAGE ON SCHEMA public TO opspilot_app,opspilot_provisioner,opspilot_audit_owner;
GRANT SELECT ON principals,role_grants,audit_events,audit_streams,alembic_version TO opspilot_app;
GRANT SELECT,INSERT,UPDATE ON principals,role_grants TO opspilot_provisioner;
GRANT SELECT ON audit_events,audit_streams TO opspilot_provisioner;
GRANT SELECT,INSERT ON audit_events TO opspilot_audit_owner;
GRANT SELECT,INSERT,UPDATE ON audit_streams TO opspilot_audit_owner;
-- PostgreSQL requires CREATE on the containing schema while transferring ownership.
GRANT CREATE ON SCHEMA public TO opspilot_audit_owner;
ALTER FUNCTION audit_append(uuid,text,uuid,text,text) OWNER TO opspilot_audit_owner;
REVOKE CREATE ON SCHEMA public FROM opspilot_audit_owner;
REVOKE ALL ON FUNCTION audit_append(uuid,text,uuid,text,text) FROM PUBLIC;
REVOKE ALL ON FUNCTION audit_canonical(json) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION audit_canonical(json) TO opspilot_audit_owner,opspilot_app,opspilot_provisioner;
GRANT EXECUTE ON FUNCTION audit_append(uuid,text,uuid,text,text) TO opspilot_app,opspilot_provisioner;
