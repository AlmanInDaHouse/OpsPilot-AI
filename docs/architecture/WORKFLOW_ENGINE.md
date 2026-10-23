# Motor durable — especificación normativa

Estado: ejecución de motor PROPUESTA; T03-02 implementa almacenamiento, constraints
y appender/lectura v2; T03-03 añade intake/UoW/idempotencia. Sin worker.
REQ-WF-01/02/03. Fuente de estados/transiciones:
[workflow-v1.json](../../contracts/workflow-v1.json); diagrama derivado en [C4](C4.md).
Workflow, ticket y ejecución externa tienen estados independientes.

## Estados y guardas

| Estado | Entrada / salida válida y autoridad |
|---|---|
| QUEUED | Ticket+job confirmados; worker obtiene lease → INVESTIGATING |
| INVESTIGATING | Lecturas/RAG/evidencia; propuesta validada → PLAN_READY; insuficiente → NEEDS_OPERATOR |
| PLAN_READY | Policy DENY → NEEDS_OPERATOR; REQUIRE_APPROVAL → AWAITING_APPROVAL; ALLOW solo lectura → EXECUTING |
| AWAITING_APPROVAL | Aprobación válida → EXECUTING; rechazo/caducidad → NEEDS_OPERATOR; no reserva worker |
| EXECUTING | Intent con autorización; resultado confirmado → VERIFYING; ambiguo → OUTCOME_UNKNOWN |
| VERIFYING | Verificador independiente → SUCCEEDED si prueba positiva fresca; FAILED si prueba concluyente negativa; inconcluso → NEEDS_OPERATOR |
| RETRY_WAIT | Solo lecturas/LLM/DB transitorios; resume_state permitido y available_at persistido |
| OUTCOME_UNKNOWN | No auto-retry; reconciliación externa → VERIFYING o intervención → NEEDS_OPERATOR |
| NEEDS_OPERATOR | Pausa operable; actor autorizado puede reabrir investigación, reconciliar o cancelar |
| SUCCEEDED / FAILED / CANCELLED | Terminales; nuevo intento exige nuevo workflow y nueva autorización |

FAILED expresa fallo del workflow, no resolución del ticket. SUCCEEDED permite
proponer cierre del ticket solo con evidencia independiente; cierre lo confirma
operador humano con permiso. El modelo jamás puede enviar transición de estado.
Eventos indican reason_code y evidencia de cada guarda; CAS sobre `version` y DB
rechazan transición inexistente. API no expone endpoint genérico `set_state`.
EXECUTING→FAILED solo se permite con fallo permanente confirmado y evidencia de
ausencia de efecto; un timeout o una respuesta ambigua siempre produce OUTCOME_UNKNOWN.
EXECUTING→NEEDS_OPERATOR exige rechazo confirmado antes de envío o reconciliación
completa; nunca evita la cuarentena de un efecto desconocido.

## Entrega, ownership y caídas

Semántica interna: **at-least-once** para jobs; commit local atómico; efectos externos
no exactly-once. Job reclamado con lock corto, `owner` aleatorio, fence creciente y
lease de 60 s; heartbeat cada 15 s usando reloj DB. Poll 2 s con jitter. Worker viejo
no puede guardar resultados si token/lease/version caducaron. Lock PG no cruza red.
Un lease NO impide que una llamada externa antigua siga ejecutándose.

Para mutaciones, gate de recurso + intent UNIQUE + operation_id estable: duplicado
del job ve IN_FLIGHT/UNKNOWN y reconcilia, nunca crea otro envío. Adapter externo debe
deduplicar operation_id y exponer consulta de estado durable. Si no lo ofrece, un
timeout/crash se marca UNKNOWN y recurso en cuarentena; solo operador puede resolver
con evidencia. Fencing local no promete detener una operación remota ya enviada.
La cuarentena pertenece al recurso y sobrevive a nuevos workflows: impide cualquier
nuevo intent mutante hasta que reconciliación concluyente y revisión humana la liberen.
Reabrir investigación no evita esta guarda. Toda salida de NEEDS_OPERATOR requiere
permiso humano y evidencia; no es un retry automático encubierto.

Tras reinicio: barrido de leases expirados. Lecturas vuelven a READY; intent PREPARED
puede reclamarse si nunca pasó IN_FLIGHT; IN_FLIGHT expirado → UNKNOWN y cuarentena.
Crash tras commit del resultado pero antes de ack ve job DONE, no reejecuta.
DB desconectada: no iniciar herramientas ni aceptar tickets; llamada ya en curso
termina localmente y se trata como desconocida hasta poder reconciliar/persistir.

## Reintentos y tiempo

Máximo 3 intentos para lectura/LLM, backoff full jitter U(0,min(30 s,2^attempt s)),
Retry-After acotado por deadline. Fallos auth/schema/policy son permanentes; pasan a
NEEDS_OPERATOR o FAILED según posibilidad de recuperación, con código explícito.
Timeout lectura 10 s, LLM 30 s, mutación 20 s, verificación 30 s; plazos absolutos DB
y presupuesto activo acumulado 300 s. No reiniciar presupuesto al recuperar proceso.
RETRY_WAIT guarda `resume_state` de INVESTIGATING/PLAN_READY/VERIFYING; nunca EXECUTING.
Si se agota plazo en mutación, OUTCOME_UNKNOWN, nunca FAILED por suposición.

## Aprobaciones, carreras y cancelación

TTL 15 min por reloj DB; propuesta canónica immutable incluye tool/version, args,
resource_id, workflow_id/version de plan, policy/version y caducidad. Nonce de un uso.
Aprobador distinto del proponente; revalidar rol local habilitado y policy al dispatch.
Cambio de plan/policy/credenciales relevantes exige nueva propuesta/aprobación.
Dos respuestas concurrentes: fila UNIQUE + lock, primera gana; replay devuelve 409.
Expiry vs dispatch se decide bajo el mismo lock, no por temporizador cliente.

Cancelación es intención auditada, no rollback físico. QUEUED/INVESTIGATING/PLAN_READY/
AWAITING_APPROVAL/RETRY_WAIT pueden ir CANCELLED tras invalidar jobs/propuestas.
Durante EXECUTING/VERIFYING/OUTCOME_UNKNOWN persistir cancel_requested_at, bloquear
nuevos envíos y reconciliar/verificar primero; finalizar en NEEDS_OPERATOR si cancelado
con efectos, no prometer ausencia de efectos. Fencing evita commit tardío que resucite
workflow cancelado. Carrera cancelar/dispatch serializa por workflow+intent.

Compensación: ninguna automática para restart VPN (no es reversible). Futuras acciones
reversibles requieren herramienta compensadora separada, política/aprobación y pruebas;
no tratar saga como transacción distribuida. Reconciliación que prueba no ejecución
lleva a NEEDS_OPERATOR; reintento mutante exige nueva propuesta/aprobación.

## PG, outbox y validación pendiente

PG ya guarda jobs en misma transacción que workflow/audit: no hace falta outbox para
esa cola interna. Cuando se emita a un destino externo, insertar outbox en el mismo
UoW; dispatcher entrega at-least-once y destino deduplica event_id. Marcar delivered
solo tras ack; pérdida de ack provoca duplicado. Audit se persiste antes de exportar.

Suite obligatoria S03/S05: dos workers y reclaim, crash antes/después de claim/commit/
envío, stale fence, cancel/expiry/replay concurrente, PG caído y timeout con efecto
real. Testea invariantes en PG real y cliente externo real S06. El JSON/diagrama de
sesión 01 comprueba estructura, no demuestra estas propiedades.
