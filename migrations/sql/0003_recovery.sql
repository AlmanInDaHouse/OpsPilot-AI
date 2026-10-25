-- Cursor and counter are assigned by an invoker trigger, never by runtime grants.
ALTER TABLE jobs ADD COLUMN active_since timestamptz;
ALTER TABLE jobs ADD COLUMN active_spent_ms bigint NOT NULL DEFAULT 0;
UPDATE jobs j SET active_since=GREATEST(w.created_at,j.lease_until-interval '60 seconds'),
    active_spent_ms=w.budget_spent_ms
FROM workflows w WHERE w.id=j.workflow_id AND j.state='LEASED';
ALTER TABLE jobs ADD CONSTRAINT ck_job_active CHECK (
    active_spent_ms BETWEEN 0 AND 300000
    AND ((state='LEASED' AND active_since IS NOT NULL) OR
         (state<>'LEASED' AND active_since IS NULL)));
CREATE INDEX ix_job_expired ON jobs(lease_until,id) WHERE state='LEASED';

CREATE FUNCTION job_active_accounting() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public AS $$
DECLARE stamp timestamptz := clock_timestamp(); elapsed bigint := 0;
BEGIN
    IF OLD.active_since IS NOT NULL THEN
        elapsed := GREATEST(0,ceil(extract(epoch FROM
            (LEAST(stamp,OLD.lease_until)-OLD.active_since))*1000)::bigint);
    END IF;
    NEW.active_spent_ms := LEAST(300000,OLD.active_spent_ms+elapsed);
    NEW.active_since := CASE WHEN NEW.state='LEASED' THEN
        CASE WHEN OLD.state='LEASED' THEN GREATEST(OLD.active_since,LEAST(stamp,OLD.lease_until)) ELSE stamp END
        ELSE NULL END;
    RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION job_active_accounting() FROM PUBLIC;
CREATE TRIGGER job_active_accounting BEFORE UPDATE ON jobs
FOR EACH ROW EXECUTE FUNCTION job_active_accounting();

-- Closed read-only confirmation; do not grant the worker access to the audit ledger.
CREATE FUNCTION worker_result_confirmed(p_workflow uuid,p_version bigint,p_evidence uuid)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog,public AS $$
    SELECT session_user='opspilot_worker' AND EXISTS (
        SELECT 1 FROM public.audit_events e
        JOIN public.audit_streams h ON h.stream_id=e.stream_id AND h.last_seq=e.seq
            AND h.last_hash=e.hash
        JOIN public.workflows w ON w.id=e.stream_id AND w.version=p_version
        WHERE e.stream_id=p_workflow AND e.schema_version=2
          AND e.event_type='workflow.transitioned'
          AND e.payload->>'reason_code'='LOCAL_SNAPSHOT_RECORDED'
          AND e.payload->>'aggregate_version'=p_version::text
          AND e.payload->'evidence_ids'=jsonb_build_array(p_evidence::text)
          AND e.state_snapshot->>'state'='NEEDS_OPERATOR'
          AND e.state_snapshot->>'version'=p_version::text
    );
$$;
REVOKE ALL ON FUNCTION worker_result_confirmed(uuid,bigint,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION worker_result_confirmed(uuid,bigint,uuid) TO opspilot_worker;
GRANT CREATE ON SCHEMA public TO opspilot_audit_owner;
ALTER FUNCTION worker_result_confirmed(uuid,bigint,uuid) OWNER TO opspilot_audit_owner;
REVOKE CREATE ON SCHEMA public FROM opspilot_audit_owner;
