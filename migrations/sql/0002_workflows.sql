-- Frozen T03-02 DDL. Incremental from 0001; runtime never creates schema.

CREATE TABLE incidents (
	id UUID NOT NULL,
	creator_id UUID NOT NULL,
	title TEXT NOT NULL,
	description TEXT NOT NULL,
	status VARCHAR(24) DEFAULT 'OPEN' NOT NULL,
	version BIGINT DEFAULT 1 NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT clock_timestamp() NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_incident_creator UNIQUE (id, creator_id),
	CONSTRAINT ck_incident_text CHECK (length(title) BETWEEN 1 AND 200 AND length(description) BETWEEN 1 AND 4000),
	CONSTRAINT ck_incident_status CHECK (status = 'OPEN' AND version = 1),
	FOREIGN KEY(creator_id) REFERENCES principals (id)
);

CREATE TABLE workflows (
	id UUID NOT NULL,
	incident_id UUID NOT NULL,
	creator_id UUID NOT NULL,
	definition_version INTEGER DEFAULT 1 NOT NULL,
	state VARCHAR(32) DEFAULT 'QUEUED' NOT NULL,
	resume_state VARCHAR(32),
	version BIGINT DEFAULT 1 NOT NULL,
	deadline_at TIMESTAMP WITH TIME ZONE DEFAULT statement_timestamp() + interval '300 seconds' NOT NULL,
	budget_spent_ms BIGINT DEFAULT 0 NOT NULL,
	cancel_requested_at TIMESTAMP WITH TIME ZONE,
	reason_code VARCHAR(64) DEFAULT 'INTAKE_ACCEPTED' NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT clock_timestamp() NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT fk_workflow_incident_creator FOREIGN KEY(incident_id, creator_id) REFERENCES incidents (id, creator_id),
	CONSTRAINT uq_workflow_incident_creator UNIQUE (id, incident_id, creator_id),
	CONSTRAINT ck_workflow_state CHECK (state IN ('QUEUED','INVESTIGATING','PLAN_READY','AWAITING_APPROVAL','EXECUTING','VERIFYING','RETRY_WAIT','OUTCOME_UNKNOWN','NEEDS_OPERATOR','SUCCEEDED','FAILED','CANCELLED')),
	CONSTRAINT ck_workflow_reason CHECK (reason_code IN ('INTAKE_ACCEPTED','LOCAL_STEP_STARTED','LOCAL_SNAPSHOT_RECORDED','TRANSIENT_LOCAL_FAILURE','RETRY_READY','DEADLINE_EXHAUSTED','RETRY_EXHAUSTED','PERMANENT_LOCAL_FAILURE','UNSUPPORTED_DEFINITION','CANCELLED_BY_OPERATOR','CANCEL_REQUESTED')),
	CONSTRAINT ck_workflow_version CHECK (version >= 1 AND definition_version >= 1),
	CONSTRAINT ck_workflow_budget CHECK (budget_spent_ms BETWEEN 0 AND 300000 AND deadline_at > created_at),
	CONSTRAINT ck_workflow_resume CHECK ((state = 'RETRY_WAIT' AND resume_state IS NOT NULL AND resume_state IN ('INVESTIGATING','PLAN_READY','VERIFYING')) OR (state <> 'RETRY_WAIT' AND resume_state IS NULL)),
	CONSTRAINT ck_workflow_cancel CHECK (state <> 'CANCELLED' OR cancel_requested_at IS NOT NULL)
);

CREATE UNIQUE INDEX uq_workflow_active_incident ON workflows (incident_id) WHERE state NOT IN ('SUCCEEDED','FAILED','CANCELLED');

CREATE TABLE api_idempotency (
	principal_id UUID NOT NULL,
	route VARCHAR(64) NOT NULL,
	key UUID NOT NULL,
	request_hash VARCHAR(64) NOT NULL,
	response_status INTEGER NOT NULL,
	response_body JSONB NOT NULL,
	incident_id UUID NOT NULL,
	workflow_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT clock_timestamp() NOT NULL,
	PRIMARY KEY (principal_id, route, key),
	CONSTRAINT fk_idempotency_workflow_incident FOREIGN KEY(workflow_id, incident_id, principal_id) REFERENCES workflows (id, incident_id, creator_id),
	CONSTRAINT ck_idempotency_route_status CHECK (route = '/v1/incidents' AND response_status = 202),
	CONSTRAINT ck_idempotency_hash CHECK (length(request_hash) = 64 AND request_hash ~ '^[0-9a-f]{64}$'),
	CONSTRAINT ck_idempotency_response CHECK (response_body = jsonb_build_object('incident_id',incident_id::text,'workflow_id',workflow_id::text)),
	FOREIGN KEY(principal_id) REFERENCES principals (id),
	FOREIGN KEY(incident_id) REFERENCES incidents (id)
);

CREATE TABLE evidence (
	id UUID NOT NULL,
	workflow_id UUID NOT NULL,
	step_key VARCHAR(64) NOT NULL,
	kind VARCHAR(32) NOT NULL,
	collector_id VARCHAR(64) NOT NULL,
	source_ref VARCHAR(128) NOT NULL,
	content_hash VARCHAR(64) NOT NULL,
	observed_at TIMESTAMP WITH TIME ZONE DEFAULT clock_timestamp() NOT NULL,
	expires_at TIMESTAMP WITH TIME ZONE,
	payload JSONB NOT NULL,
	independence_role VARCHAR(32) NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_evidence_step_kind UNIQUE (workflow_id, step_key, kind),
	CONSTRAINT uq_evidence_workflow UNIQUE (id, workflow_id),
	CONSTRAINT ck_evidence_kind CHECK (kind = 'INCIDENT_SNAPSHOT_V1' AND step_key = 'intake_snapshot' AND collector_id = 'local-intake-v1' AND independence_role = 'INTAKE_SNAPSHOT'),
	CONSTRAINT ck_evidence_hash CHECK (content_hash ~ '^[0-9a-f]{64}$' AND length(content_hash) = 64),
	CONSTRAINT ck_evidence_expiry CHECK (expires_at IS NULL OR expires_at > observed_at),
	CONSTRAINT ck_evidence_payload CHECK (jsonb_typeof(payload) = 'object'),
	FOREIGN KEY(workflow_id) REFERENCES workflows (id)
);

CREATE TABLE workflow_steps (
	id UUID NOT NULL,
	workflow_id UUID NOT NULL,
	step_key VARCHAR(64) NOT NULL,
	attempt_no INTEGER DEFAULT 1 NOT NULL,
	status VARCHAR(16) DEFAULT 'PENDING' NOT NULL,
	input_hash VARCHAR(64),
	evidence_id UUID,
	error_code VARCHAR(64),
	PRIMARY KEY (id),
	CONSTRAINT uq_step_attempt UNIQUE (workflow_id, step_key, attempt_no),
	CONSTRAINT uq_step_workflow UNIQUE (id, workflow_id),
	CONSTRAINT fk_step_evidence_workflow FOREIGN KEY(evidence_id, workflow_id) REFERENCES evidence (id, workflow_id),
	CONSTRAINT ck_step_key_attempt CHECK (step_key = 'intake_snapshot' AND attempt_no BETWEEN 1 AND 3),
	CONSTRAINT ck_step_status CHECK (status IN ('PENDING','RUNNING','DONE','FAILED','CANCELLED')),
	CONSTRAINT ck_step_hash CHECK (input_hash IS NULL OR (length(input_hash) = 64 AND input_hash ~ '^[0-9a-f]{64}$')),
	CONSTRAINT ck_step_error CHECK (error_code IS NULL OR error_code IN ('TRANSIENT_LOCAL_FAILURE','PERMANENT_LOCAL_FAILURE','DEADLINE_EXHAUSTED','RETRY_EXHAUSTED','UNSUPPORTED_DEFINITION')),
	CONSTRAINT ck_step_done CHECK (status <> 'DONE' OR (evidence_id IS NOT NULL AND input_hash IS NOT NULL AND error_code IS NULL)),
	FOREIGN KEY(workflow_id) REFERENCES workflows (id)
);

CREATE TABLE jobs (
	id UUID NOT NULL,
	workflow_id UUID NOT NULL,
	step_id UUID NOT NULL,
	kind VARCHAR(64) NOT NULL,
	state VARCHAR(16) DEFAULT 'READY' NOT NULL,
	available_at TIMESTAMP WITH TIME ZONE DEFAULT clock_timestamp() NOT NULL,
	lease_until TIMESTAMP WITH TIME ZONE,
	owner UUID,
	fence BIGINT DEFAULT 0 NOT NULL,
	attempts INTEGER DEFAULT 0 NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT fk_job_step_workflow FOREIGN KEY(step_id, workflow_id) REFERENCES workflow_steps (id, workflow_id),
	CONSTRAINT ck_job_state_kind CHECK (kind = 'intake_snapshot' AND state IN ('READY','LEASED','DONE','DEAD')),
	CONSTRAINT ck_job_counters CHECK (fence >= 0 AND attempts BETWEEN 0 AND 3),
	CONSTRAINT ck_job_ownership CHECK ((state = 'LEASED' AND owner IS NOT NULL AND lease_until IS NOT NULL AND fence >= 1) OR (state <> 'LEASED' AND owner IS NULL AND lease_until IS NULL)),
	FOREIGN KEY(workflow_id) REFERENCES workflows (id)
);

CREATE INDEX ix_job_available ON jobs (state, available_at);

CREATE UNIQUE INDEX uq_job_active_workflow ON jobs (workflow_id, kind) WHERE state IN ('READY','LEASED');

ALTER TABLE audit_events ADD COLUMN state_snapshot jsonb;

ALTER TABLE audit_events DROP CONSTRAINT ck_audit_version_seq;

ALTER TABLE audit_events DROP CONSTRAINT ck_audit_type;

ALTER TABLE audit_events ADD CONSTRAINT ck_audit_snapshot CHECK (((schema_version = 1 OR event_type = 'incident.created') AND state_snapshot IS NULL) OR (schema_version = 2 AND event_type <> 'incident.created' AND state_snapshot IS NOT NULL AND jsonb_typeof(state_snapshot) = 'object'));

ALTER TABLE audit_events ADD CONSTRAINT ck_audit_type CHECK ((schema_version = 1 AND event_type IN ('identity.provisioned','identity.disabled','authorization.granted','authorization.revoked','authorization.denied')) OR (schema_version = 2 AND event_type IN ('incident.created','workflow.transitioned','workflow.cancel_requested','workflow.blocked')));

ALTER TABLE audit_events ADD CONSTRAINT ck_audit_version_seq CHECK (seq >= 1 AND schema_version IN (1,2));

CREATE UNIQUE INDEX uq_audit_v2_version ON audit_events (stream_id, (payload ->> 'aggregate_version')) WHERE schema_version = 2;
