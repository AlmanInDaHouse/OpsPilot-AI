# T03-06 — recuperación local durable

Diseño previo al código, 2026-10-25 Europe/Madrid. Base main limpia
224c5ad5c648e231af6bef5bdceeab5c5c14d190. Gate de entrada remoto SUCCESS:
plataforma 40054234985 y harness 40054235016, SHA exacto. Evidencia separada en
artifacts/session-03/recovery/entry-gate.json. Requisito REQ-WF-02, tarea T03-06,
AC03-04/05/06/07/09. Autorización exclusivamente local, sin commit/publicación.

## Invariantes y estados

Solo intake_snapshot definición 1. No efectos externos ni cierre de incidents.
DONE/DEAD nunca se recuperan. Cancelación mantiene CAS y no resucita. Evidence
confirmada es inmutable; cualquier inconsistencia bloquea por defecto. Tres claims
como máximo, incluidos crashes anteriores a start. Reclaim no consume un intento:
invalida la generación vencida; el siguiente claim consume el siguiente intento.

| Estado observado | Recuperación permitida |
|---|---|
| QUEUED + LEASED vencido | READY con fence+1; sin transición artificial |
| INVESTIGATING + LEASED vencido | RETRY_WAIT/TRANSIENT_LOCAL_FAILURE y READY con backoff |
| RETRY_WAIT + READY disponible | Claim y RETRY_READY hacia INVESTIGATING |
| LEASED vivo | No reclaim, salvo deadline/budget agotado |
| QUEUED vencido | FAILED/DEADLINE_EXHAUSTED y DEAD |
| INVESTIGATING o RETRY_WAIT vencido | NEEDS_OPERATOR/DEADLINE_EXHAUSTED y DEAD |
| Tercer intento perdido | NEEDS_OPERATOR/RETRY_EXHAUSTED; si QUEUED, primero inicio auditado |
| Definición desconocida | workflow.blocked/UNSUPPORTED_DEFINITION, estado conservado, DEAD |
| CANCELLED, DONE o DEAD | Sin reactivación |

## Locks y carreras

Selección orientativa sin locks; relectura workflow FOR UPDATE SKIP LOCKED antes de
job FOR UPDATE SKIP LOCKED. Revalidar fechas/estado/cancel/owner bajo esos locks.
Después step y audit; nunca esperar workflow manteniendo job. Claim sigue siendo
job-only y termina antes de start. Heartbeat/completion/cancel/reclaim se serializan
por workflow; el primer commit válido decide. Última guarda después de audit evita
confirmar resultado tras expiración mientras espera. Heartbeat no revive lease.
Retry/cancel/deadline comparten este orden; cancelar RETRY_WAIT debe limpiar resume.
Dos reclaimers pueden seleccionar lo mismo: solo uno modifica la generación.

## Tiempo y migración incremental

0002 tiene deadline_at inmutable, attempts, available_at, lease_until, owner/fence,
resume_state y budget_spent_ms. No tiene cursor de procesamiento persistente.
0003 añade jobs.active_since y jobs.active_spent_ms, CHECK correlacionado
y trigger invoker sin grants adicionales. SELECT existente cubre las columnas;
ningún runtime recibe UPDATE directo de ellas. La reconciliación necesita leer el
resultado auditado: worker_result_confirmed es una función SECURITY DEFINER cerrada,
solo SELECT, con dueño audit_owner existente y EXECUTE solo worker. Devuelve boolean,
sin exponer ledger/identidades; no amplía grants de tablas ni del dueño. Negativos
obligatorios: PUBLIC/app no EXECUTE; worker sin SELECT audit ni DML directo.
Índice parcial lease_until para
barrido de vencidos. Migraciones 0001/0002 y appender v2 conservados.

Tiempo de vida: intake a deadline (300 s), incluye READY/RETRY_WAIT. Tiempo activo:
desde claim hasta liberación o último vencimiento de lease; crash consume hasta
lease_until, cota conservadora por desconocer el instante físico de muerte. Renovar
liquida el segmento anterior y mueve cursor con reloj PG. Liberar liquida y anula
cursor. Reclaim no vuelve a contar ese segmento. RETRY_WAIT no consume activo.
El cursor usa GREATEST con su valor previo: un retroceso del reloj DB no vuelve a
cobrar un segmento ya liquidado. Deadline y lease siguen usando tiempo absoluto PG.
Contador durable en jobs; workflows.budget_spent_ms es su proyección en transiciones
auditadas, evitando incrementar version por heartbeat. Saturación 300000 ms.
Registros históricos LEASED: cursor inicial lease_until-60 s, sin inventar duración
previa a esa última renovación; límite histórico explícito. No reset de deadline.

Full jitter U(0,min(30,2^attempts)) se guarda como available_at PG antes de liberar;
solo fallos SQL locales clasificados transitorios y crash local de este handler.
Auth/schema/invariante/permanente no tienen retry genérico. Error audit permanente
detiene el worker. Conexión perdida al COMMIT exige reconciliar antes de decidir.

## Commit incierto y campaña de pruebas

Nueva conexión/transacción bloquea workflow/job en orden para esperar resolución
del backend anterior; relee workflow/job/step/evidence/audit. Solo conjunto completo
DONE + NEEDS_OPERATOR + step DONE + evidencia/hash + evento v2 enlazado confirma
resultado. Sin prueba completa no declarar éxito ni repetir inmediatamente: lease
retenido, recuperación posterior por expiración. No basarse en logs. Pruebas con
COMMIT real PostgreSQL y ACK descartado en transporte, y desconexión con rollback.

Procesos reales y barreras test-only antes/después de claim/start/snapshot/evidence/
audit/commit/ack; observador independiente, locks PG, kills y expiración observada.
Dos procesos/100 jobs, dos reclaimers, 20 carreras de cancelación, fence antiguo,
deadline/retry agotados, definición desconocida, fallo appender y reinicio PG.
Regresión Windows/Linux, checks, fresh/recovery y tres scans nuevos. Solo resultados
ejecutados se marcarán PROBADOS; CI nueva requiere publicación futura autorizada.

El laboratorio mostró retrocesos de aproximadamente 5 s después de un claim válido
([diagnóstico](../../artifacts/session-03/recovery/selection-diagnostic.json)). Las
fixtures READY se preparan 30 s en pasado y los vencimientos cortos se observan con
margen temporal; no se cambian los 60/15/300 s ni backoff del producto. El test de
expiración real conserva lease 60 s y comprueba accounting de al menos 59000 ms.
