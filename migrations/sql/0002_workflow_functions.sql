-- No dynamic SQL; every payload, role and event family is closed.
CREATE FUNCTION workflow_update_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
DECLARE allowed text[];
BEGIN
    IF (NEW.id,NEW.incident_id,NEW.creator_id,NEW.definition_version,NEW.deadline_at,NEW.created_at)
       IS DISTINCT FROM (OLD.id,OLD.incident_id,OLD.creator_id,OLD.definition_version,OLD.deadline_at,OLD.created_at)
       OR NEW.version <> OLD.version + 1 OR NEW.budget_spent_ms < OLD.budget_spent_ms
       OR (OLD.cancel_requested_at IS NOT NULL AND NEW.cancel_requested_at IS DISTINCT FROM OLD.cancel_requested_at) THEN
        RAISE EXCEPTION 'Invalid workflow update' USING ERRCODE='22023';
    END IF;
    allowed := CASE OLD.state
      WHEN 'QUEUED' THEN ARRAY['INVESTIGATING','CANCELLED','FAILED']
      WHEN 'INVESTIGATING' THEN ARRAY['PLAN_READY','RETRY_WAIT','NEEDS_OPERATOR','FAILED','CANCELLED']
      WHEN 'PLAN_READY' THEN ARRAY['AWAITING_APPROVAL','EXECUTING','RETRY_WAIT','NEEDS_OPERATOR','CANCELLED']
      WHEN 'AWAITING_APPROVAL' THEN ARRAY['EXECUTING','NEEDS_OPERATOR','CANCELLED']
      WHEN 'EXECUTING' THEN ARRAY['VERIFYING','OUTCOME_UNKNOWN','FAILED','NEEDS_OPERATOR']
      WHEN 'VERIFYING' THEN ARRAY['SUCCEEDED','FAILED','RETRY_WAIT','NEEDS_OPERATOR']
      WHEN 'RETRY_WAIT' THEN ARRAY['INVESTIGATING','PLAN_READY','VERIFYING','NEEDS_OPERATOR','FAILED','CANCELLED']
      WHEN 'OUTCOME_UNKNOWN' THEN ARRAY['VERIFYING','NEEDS_OPERATOR']
      WHEN 'NEEDS_OPERATOR' THEN ARRAY['INVESTIGATING','VERIFYING','CANCELLED']
      ELSE ARRAY[]::text[] END;
    IF (OLD.state IN ('SUCCEEDED','FAILED','CANCELLED'))
       OR (NEW.state <> OLD.state AND NOT NEW.state = ANY(allowed)) THEN
        RAISE EXCEPTION 'Invalid workflow transition' USING ERRCODE='22023';
    END IF;
    IF NEW.state <> 'RETRY_WAIT' THEN NEW.resume_state := NULL; END IF;
    RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION workflow_update_guard() FROM PUBLIC;
CREATE TRIGGER workflows_update_guard BEFORE UPDATE ON workflows
FOR EACH ROW EXECUTE FUNCTION workflow_update_guard();

CREATE FUNCTION evidence_insert_guard() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
DECLARE w public.workflows%ROWTYPE; body jsonb := NEW.payload; digest text;
BEGIN
    SELECT * INTO STRICT w FROM public.workflows WHERE id=NEW.workflow_id;
    IF w.definition_version <> 1 OR w.state <> 'INVESTIGATING'
       OR jsonb_typeof(body) IS DISTINCT FROM 'object'
       OR NOT body ?& ARRAY['schema_version','incident_id','incident_version','workflow_id','definition_version','status','title_hash','description_hash']
       OR body - ARRAY['schema_version','incident_id','incident_version','workflow_id','definition_version','status','title_hash','description_hash'] <> '{}'::jsonb
       OR body->'schema_version' IS DISTINCT FROM '1'::jsonb
       OR body->'incident_version' IS DISTINCT FROM '1'::jsonb
       OR body->'definition_version' IS DISTINCT FROM '1'::jsonb
       OR body->'status' IS DISTINCT FROM '"OPEN"'::jsonb
       OR body->'incident_id' IS DISTINCT FROM to_jsonb(w.incident_id::text)
       OR body->'workflow_id' IS DISTINCT FROM to_jsonb(w.id::text)
       OR jsonb_typeof(body->'title_hash') IS DISTINCT FROM 'string'
       OR jsonb_typeof(body->'description_hash') IS DISTINCT FROM 'string'
       OR length(body->>'title_hash') <> 64 OR (body->>'title_hash') !~ '^[0-9a-f]{64}$'
       OR length(body->>'description_hash') <> 64 OR (body->>'description_hash') !~ '^[0-9a-f]{64}$'
       OR NEW.source_ref <> 'incident:' || w.incident_id::text || ':v1'
       OR octet_length(body::text) > 2048 THEN
       RAISE EXCEPTION 'Invalid intake evidence' USING ERRCODE='22023';
    END IF;
    digest := encode(sha256(convert_to(public.audit_canonical(body::json),'UTF8')),'hex');
    IF NEW.content_hash IS DISTINCT FROM digest THEN
       RAISE EXCEPTION 'Invalid evidence digest' USING ERRCODE='22023';
    END IF;
    NEW.observed_at := clock_timestamp();
    RETURN NEW;
END $$;
GRANT CREATE ON SCHEMA public TO opspilot_audit_owner;
ALTER FUNCTION evidence_insert_guard() OWNER TO opspilot_audit_owner;
REVOKE CREATE ON SCHEMA public FROM opspilot_audit_owner;
REVOKE ALL ON FUNCTION evidence_insert_guard() FROM PUBLIC;
CREATE TRIGGER evidence_insert_guard BEFORE INSERT ON evidence
FOR EACH ROW EXECUTE FUNCTION evidence_insert_guard();

CREATE FUNCTION audit_append_v2(p_stream uuid, p_type text, p_actor uuid,
                                p_trace text, p_payload text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
DECLARE
    body jsonb; raw_body json; w public.workflows%ROWTYPE;
    head public.audit_streams%ROWTYPE; prior jsonb; snapshot jsonb;
    eid uuid := gen_random_uuid(); stamp timestamptz := clock_timestamp();
    wire json; digest text; snapshot_digest text; src text; dst text;
    reason text; evidence_count integer; allowed boolean := false;
BEGIN
    IF p_stream IS NULL OR p_type IS NULL OR p_trace IS NULL OR p_payload IS NULL
       OR octet_length(p_payload) > 8192 OR length(p_trace) <> 32 OR p_trace !~ '^[0-9a-f]{32}$'
       OR p_type NOT IN ('incident.created','workflow.transitioned','workflow.cancel_requested','workflow.blocked') THEN
       RAISE EXCEPTION 'Invalid workflow audit input' USING ERRCODE='22023';
    END IF;
    raw_body := p_payload::json;
    body := public.audit_canonical(raw_body)::jsonb;
    IF jsonb_typeof(body) IS DISTINCT FROM 'object'
       OR NOT body ?& ARRAY['reason_code','aggregate_id','aggregate_version','evidence_ids']
       OR jsonb_typeof(body->'reason_code') IS DISTINCT FROM 'string'
       OR jsonb_typeof(body->'aggregate_id') IS DISTINCT FROM 'string'
       OR body->>'aggregate_id' <> p_stream::text
       OR jsonb_typeof(body->'aggregate_version') IS DISTINCT FROM 'number'
       OR (body->>'aggregate_version') !~ '^[1-9][0-9]*$'
       OR jsonb_typeof(body->'evidence_ids') IS DISTINCT FROM 'array' THEN
       RAISE EXCEPTION 'Invalid workflow audit payload' USING ERRCODE='22023';
    END IF;
    reason := body->>'reason_code';
    evidence_count := jsonb_array_length(body->'evidence_ids');
    IF evidence_count > 1 OR EXISTS (
        SELECT 1 FROM jsonb_array_elements(body->'evidence_ids') a
        WHERE jsonb_typeof(a) <> 'string' OR length(a #>> '{}') <> 36
           OR (a #>> '{}') !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
    ) THEN
       RAISE EXCEPTION 'Invalid workflow evidence references' USING ERRCODE='22023';
    END IF;
    IF p_type = 'incident.created' THEN
        IF session_user <> 'opspilot_app' OR p_actor IS NULL OR reason <> 'INTAKE_ACCEPTED'
           OR body->'aggregate_version' <> '1'::jsonb OR evidence_count <> 0
           OR body - ARRAY['reason_code','aggregate_id','aggregate_version','evidence_ids'] <> '{}'::jsonb THEN
           RAISE EXCEPTION 'Invalid intake audit' USING ERRCODE='22023';
        END IF;
        SELECT * INTO STRICT w FROM public.workflows WHERE incident_id=p_stream
            AND creator_id=p_actor AND state='QUEUED' AND version=1;
    ELSE
        SELECT * INTO STRICT w FROM public.workflows WHERE id=p_stream;
        IF (body->>'aggregate_version')::bigint <> w.version OR w.version < 2
           OR reason <> w.reason_code OR NOT body ? 'snapshot_hash'
           OR jsonb_typeof(body->'snapshot_hash') IS DISTINCT FROM 'string' THEN
           RAISE EXCEPTION 'Invalid workflow audit version' USING ERRCODE='22023';
        END IF;
        snapshot := jsonb_build_object('schema_version',1,'workflow_id',w.id::text,
            'incident_id',w.incident_id::text,'definition_version',w.definition_version,
            'state',w.state,'version',w.version,'reason_code',w.reason_code,
            'cancel_requested_at',CASE WHEN w.cancel_requested_at IS NULL THEN NULL ELSE
              to_char(w.cancel_requested_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"') END);
        snapshot_digest := encode(sha256(convert_to(public.audit_canonical(snapshot::json),'UTF8')),'hex');
        IF body->>'snapshot_hash' <> snapshot_digest THEN
           RAISE EXCEPTION 'Invalid workflow snapshot digest' USING ERRCODE='22023';
        END IF;
        SELECT state_snapshot INTO prior FROM public.audit_events
            WHERE stream_id=p_stream AND schema_version=2 ORDER BY seq DESC LIMIT 1;
        IF w.version <> coalesce((prior->>'version')::bigint,1) + 1 THEN
           RAISE EXCEPTION 'Invalid workflow audit sequence' USING ERRCODE='22023';
        END IF;
        IF p_type = 'workflow.transitioned' THEN
            IF NOT body ? 'transition' OR jsonb_typeof(body->'transition') IS DISTINCT FROM 'object'
               OR NOT (body->'transition') ?& ARRAY['from','to','definition_version']
               OR (body->'transition') - ARRAY['from','to','definition_version'] <> '{}'::jsonb
               OR body - ARRAY['reason_code','aggregate_id','aggregate_version','evidence_ids','transition','snapshot_hash'] <> '{}'::jsonb
               OR body->'transition'->'definition_version' IS DISTINCT FROM to_jsonb(w.definition_version)
               OR body->'transition'->'to' IS DISTINCT FROM to_jsonb(w.state)
               OR jsonb_typeof(body->'transition'->'from') IS DISTINCT FROM 'string' THEN
               RAISE EXCEPTION 'Invalid transition payload' USING ERRCODE='22023';
            END IF;
            src := body->'transition'->>'from'; dst := w.state;
            IF src <> coalesce(prior->>'state','QUEUED') THEN
               RAISE EXCEPTION 'Invalid transition source' USING ERRCODE='22023';
            END IF;
            allowed := CASE reason
              WHEN 'LOCAL_STEP_STARTED' THEN src='QUEUED' AND dst='INVESTIGATING'
              WHEN 'LOCAL_SNAPSHOT_RECORDED' THEN src='INVESTIGATING' AND dst='NEEDS_OPERATOR'
              WHEN 'TRANSIENT_LOCAL_FAILURE' THEN src='INVESTIGATING' AND dst='RETRY_WAIT'
              WHEN 'RETRY_READY' THEN src='RETRY_WAIT' AND dst='INVESTIGATING'
              WHEN 'DEADLINE_EXHAUSTED' THEN (src='QUEUED' AND dst='FAILED') OR (src IN ('INVESTIGATING','RETRY_WAIT') AND dst='NEEDS_OPERATOR')
              WHEN 'RETRY_EXHAUSTED' THEN src='INVESTIGATING' AND dst='NEEDS_OPERATOR'
              WHEN 'PERMANENT_LOCAL_FAILURE' THEN src='INVESTIGATING' AND dst='NEEDS_OPERATOR'
              WHEN 'CANCELLED_BY_OPERATOR' THEN src IN ('QUEUED','INVESTIGATING','PLAN_READY','AWAITING_APPROVAL','RETRY_WAIT','NEEDS_OPERATOR') AND dst='CANCELLED' AND w.cancel_requested_at IS NOT NULL
              ELSE false END;
            IF NOT allowed OR (reason <> 'CANCELLED_BY_OPERATOR' AND w.definition_version <> 1)
               OR (reason='LOCAL_SNAPSHOT_RECORDED' AND evidence_count <> 1)
               OR (reason<>'LOCAL_SNAPSHOT_RECORDED' AND evidence_count <> 0) THEN
               RAISE EXCEPTION 'Invalid transition reason' USING ERRCODE='22023';
            END IF;
            IF reason='CANCELLED_BY_OPERATOR' THEN
                -- Human cancellation must remain bound to the incident creator.
                IF session_user <> 'opspilot_app' OR p_actor IS DISTINCT FROM w.creator_id THEN
                   RAISE EXCEPTION 'Invalid cancellation actor' USING ERRCODE='22023';
                END IF;
            ELSIF session_user <> 'opspilot_worker' OR p_actor IS NOT NULL THEN
                RAISE EXCEPTION 'Invalid worker actor' USING ERRCODE='22023';
            END IF;
            IF reason='LOCAL_SNAPSHOT_RECORDED' AND NOT EXISTS (
                SELECT 1 FROM public.evidence e WHERE e.id=(body->'evidence_ids'->>0)::uuid AND e.workflow_id=w.id
            ) THEN
                RAISE EXCEPTION 'Invalid workflow evidence binding' USING ERRCODE='22023';
            END IF;
        ELSE
            IF evidence_count <> 0
               OR body - ARRAY['reason_code','aggregate_id','aggregate_version','evidence_ids','snapshot_hash'] <> '{}'::jsonb THEN
               RAISE EXCEPTION 'Invalid non-transition payload' USING ERRCODE='22023';
            END IF;
            IF p_type='workflow.blocked' THEN
                IF session_user <> 'opspilot_worker' OR p_actor IS NOT NULL
                   OR reason <> 'UNSUPPORTED_DEFINITION' OR w.definition_version=1
                   OR w.state <> coalesce(prior->>'state','QUEUED') THEN
                   RAISE EXCEPTION 'Invalid blocked workflow' USING ERRCODE='22023';
                END IF;
            ELSIF session_user <> 'opspilot_app' OR p_actor IS DISTINCT FROM w.creator_id
                  OR reason <> 'CANCEL_REQUESTED' OR w.cancel_requested_at IS NULL
                  OR w.state NOT IN ('EXECUTING','VERIFYING','OUTCOME_UNKNOWN')
                  OR (prior IS NOT NULL AND prior->>'state' <> w.state) THEN
                RAISE EXCEPTION 'Invalid deferred cancellation' USING ERRCODE='22023';
            END IF;
        END IF;
    END IF;
    INSERT INTO public.audit_streams VALUES(p_stream,0,repeat('0',64)) ON CONFLICT DO NOTHING;
    SELECT * INTO STRICT head FROM public.audit_streams WHERE stream_id=p_stream FOR UPDATE;
    wire := json_build_object('event_id',eid::text,'stream_id',p_stream::text,
       'seq',head.last_seq+1,'event_type',p_type,'schema_version',2,
       'occurred_at',to_char(stamp AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
       'actor_id',p_actor::text,'trace_id',p_trace,'payload',body,'prev_hash',head.last_hash);
    digest := encode(sha256(convert_to(public.audit_canonical(wire),'UTF8')),'hex');
    INSERT INTO public.audit_events(event_id,stream_id,seq,event_type,schema_version,occurred_at,
       actor_id,trace_id,payload,prev_hash,hash,state_snapshot)
       VALUES(eid,p_stream,head.last_seq+1,p_type,2,stamp,p_actor,p_trace,body,head.last_hash,digest,snapshot);
    UPDATE public.audit_streams SET last_seq=head.last_seq+1,last_hash=digest WHERE stream_id=p_stream;
    RETURN wire::jsonb || jsonb_build_object('hash',digest);
END $$;

GRANT USAGE ON SCHEMA public TO opspilot_worker;
GRANT SELECT,INSERT ON incidents TO opspilot_app;
GRANT SELECT,INSERT ON workflows TO opspilot_app;
GRANT UPDATE(state,version,cancel_requested_at,reason_code) ON workflows TO opspilot_app;
GRANT INSERT ON workflow_steps TO opspilot_app;
GRANT SELECT,INSERT ON jobs TO opspilot_app;
GRANT UPDATE(state,owner,lease_until,fence) ON jobs TO opspilot_app;
GRANT SELECT,INSERT ON api_idempotency TO opspilot_app;
GRANT SELECT ON evidence TO opspilot_app;
GRANT SELECT ON incidents,workflows,workflow_steps,jobs,evidence,alembic_version TO opspilot_worker;
GRANT UPDATE(state,resume_state,version,reason_code,budget_spent_ms) ON workflows TO opspilot_worker;
GRANT INSERT ON workflow_steps,evidence TO opspilot_worker;
GRANT UPDATE(attempt_no,status,input_hash,evidence_id,error_code) ON workflow_steps TO opspilot_worker;
GRANT UPDATE(state,available_at,lease_until,owner,fence,attempts) ON jobs TO opspilot_worker;
GRANT SELECT ON workflows TO opspilot_audit_owner;
GRANT SELECT(id,workflow_id) ON evidence TO opspilot_audit_owner;
GRANT CREATE ON SCHEMA public TO opspilot_audit_owner;
ALTER FUNCTION audit_append_v2(uuid,text,uuid,text,text) OWNER TO opspilot_audit_owner;
REVOKE CREATE ON SCHEMA public FROM opspilot_audit_owner;
REVOKE ALL ON FUNCTION audit_append_v2(uuid,text,uuid,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION audit_append_v2(uuid,text,uuid,text,text) TO opspilot_app,opspilot_worker;
