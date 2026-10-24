# Modelo de datos objetivo

Estado: tablas S02 y seis tablas S03 implementadas mediante Alembic 0002; worker
local T03-05 utiliza el esquema existente. Reclaim/retry integral T03-06 y campos
de cierre/acciones futuras siguen PROPUESTOS. [Detalle T03-02](../../specs/003-workflows/persistence.md).
UUID para entidades, UTC `timestamptz`, secuencias por agregado,
JSONB solo para payloads validados/versionados. PK/FK/UNIQUE/CHECK en DB, no solo ORM.

| Tabla / sesión | Campos e invariantes principales |
|---|---|
| principals / 02 | id UUID PK, issuer, subject, enabled, created_at; UNIQUE(issuer,subject); identidades sin password |
| role_grants / 02 | principal_id FK, role enum(operator,approver,auditor,admin), version, revoked_at; UNIQUE(principal_id,role); role activo si revoked_at NULL |
| audit_streams / 02 | stream_id UUID PK, last_seq bigint, last_hash; cabeza serializada con row lock; solo appender modifica |
| audit_events / 02 | event_id UUID PK, stream_id, seq bigint, actor_id nullable, event_type, schema_version, occurred_at, trace_id, payload JSONB redacted, prev_hash, hash; UNIQUE(stream_id,seq); append-only |
| incidents / 03 | id, creator_id FK, title <=200, description <=4000, status OPEN/RESOLVED/CLOSED_UNRESOLVED, version, resolution_evidence_id nullable; cierre exige evidencia y actor autorizado |
| workflows / 03 | id, incident_id FK, definition_version, state, resume_state nullable, version, deadline_at, budget_reserved, budget_spent, cancel_requested_at; un run activo por ticket vía índice parcial |
| workflow_steps / 03 | id, workflow_id FK, step_key, attempt_no, status, input_hash, evidence_id, error_code; UNIQUE(workflow_id,step_key,attempt_no) |
| jobs / 03 | id, workflow_id FK, step_id, kind, state READY/LEASED/DONE/DEAD, available_at, lease_until, owner, fence bigint, attempts; índice(state,available_at); payload por referencia |
| resource_locks / 05 | resource_id PK, intent_id FK, owner, fence, lease_until, quarantined; UNKNOWN mantiene quarantined hasta reconciliación |
| api_idempotency / 03 | principal_id, route, key UUID, request_hash, response_status 202, response_body, incident_id, workflow_id, created_at; PK(principal_id,route,key); retención >=7 días sin limpieza automática, clave conflictiva 409 |
| proposals / 05 | id, workflow_id, tool_id/version, resource_id, args, canonical_hash, policy_version, created_by, expires_at; snapshot inmutable |
| approvals / 05 | id, proposal_id FK, approver_id FK, decision APPROVED/DENIED, nonce UNIQUE, expires_at, consumed_at; UNIQUE(proposal_id); aprobador != proponente; versiones y snapshot vinculados |
| execution_intents / 05 | id, proposal_id FK UNIQUE, operation_id UNIQUE, status PREPARED/IN_FLIGHT/SUCCEEDED/FAILED/UNKNOWN, dispatch_fence, sent_at, result_ref; intento mutante uno por propuesta |
| evidence / 03/06 | id, workflow_id, kind, collector_id, source_ref, content_hash, observed_at, expires_at, payload redacted, independence_role; inmutable; snapshots históricos por versión, freshness según tool |
| documents/chunks/document_acl / 04 | documento versionado/hash/source, chunk_id+embedding_model+dimension, ACL de sujeto/grupo; consulta ACL antes de recuperar; revoke invalida índices/caché |
| outbox / 05 cuando haya entrega externa | event_id FK UNIQUE, destination, delivery_state, available_at, attempts, lease/fence; consumer dedup por event_id |

## Límites transaccionales

1. S02 alta de principal: upsert por `(issuer,subject)` y evento en un UoW. Ningún
   rol por defecto; grants de laboratorio por migración/provisión explícita del operador.
2. S03 creación ticket + workflow QUEUED + job READY + evento + respuesta idempotente
   en una transacción. Si falla audit o commit, nada se acepta; nunca responder 202 antes.
3. Claim de job corto `FOR UPDATE SKIP LOCKED`, actualizar lease/fence, commit;
   trabajo de red fuera. Guardar resultado exige owner/fence/lease y version vigentes.
4. Aprobación: lock workflow/proposal/approval; comprobar sujeto, permisos vigentes,
   expiración y hash; persistir decisión + evento + job en un UoW. Orden de locks:
   workflow → proposal → approval → resource → intent → job → audit stream.
5. Dispatch: con locks y checks frescos, consumir aprobación y crear intent PREPARED
   único + evento. Runner cambia PREPARED→IN_FLIGHT con fence antes de red, commit.
   `sent_at` significa intención de enviar, no prueba de efecto. Crash puede ser UNKNOWN.
6. Resultado de intent + evidencia + transición workflow + nuevo job + evento
   en un UoW con CAS. Lectura de auditoría no modifica eventos.

## Auditoría y retención

Appender serializa `seq` por stream mediante row lock. Hash SHA-256 de representación
canónica especificada (JSON UTF-8, sort_keys, separadores compactos, sin floats; campos
prev_hash+event_id+stream_id+seq+type+version+timestamp+actor+payload). RFC/algoritmo exacto
se fija antes del test de golden bytes S02; no depender de serialización ORM.
Cadena detecta modificación salvo reescritura total por administrador; no es WORM.
Exportar raíz firmada a almacenamiento externo con retención en S08 para detectar truncado.
Roles aplicación no UPDATE/DELETE en audit; procedimiento append SECURITY DEFINER
con search_path fijo y dueño no-login. Admin DB sigue siendo amenaza residual.

Propuesta laboratorio: tickets/evidencias 30 días, audit redacted 90 días, logs 7 días,
trazas 3 días; aprobación del responsable privacidad antes de datos reales. Borrado
de payload sensible y retención de hash/tombstone por política legal documentada;
no afirmar derecho de borrado satisfecho manteniendo datos identificables en backups.
Backups caducan según misma política y acceso se audita. No almacenar razonamiento
interno del modelo, solo decisión resumida, fuentes, versión y resultado estructurado.

Migración inicial S02 solo principals, role_grants, audit_streams y audit_events,
conservada intacta. T03-02 añade incidents/workflows/workflow_steps/jobs/api_idempotency/
evidence y audit_events.state_snapshot privado. Incidents solo OPEN/version 1;
resolution_evidence_id y estados de cierre de la tabla objetivo no están implementados.
Workflows añade creator_id ligado por FK a incident, presupuesto activo en ms y
deadline PG. Índices parciales evitan workflow/job activos duplicados. API idempotency
liga principal/incidente/workflow por FK compuesta; evidence solo snapshot de intake,
sin texto libre ni inmutabilidad absoluta frente al administrador. Cierre de ticket,
otras tablas y efectos externos continúan en hitos posteriores.

T03-03 instala intake: incidents/workflows/step PENDING/job READY/audit v2/respuesta
se confirman con el PostgresUow existente. La FK inmediata de idempotency requiere
crear referencias antes del INSERT final. Solo 23505 de su PK implica carrera;
rollback completo del perdedor y nueva transacción para reautorizar/releer. Sin
placeholders, claves recicladas ni filas huérfanas. Tests PG y procesos reales en
[revisión de intake](../roadmap/SESSION_03_INTAKE_REVIEW.md).

T03-04 no añade DDL: usa las columnas/grants existentes para leer proyecciones
cerradas y cancelar con workflow → jobs → audit stream. READY/LEASED a DEAD,
owner/lease NULL, fence+1; intención PG inmutable, version+1 y audit v2 atómicos.
Incidents permanece OPEN. SQL guarda terminales; el resultado tardío del worker
requiere validación adicional owner/fence/lease/version/intención en T03-05/06.
