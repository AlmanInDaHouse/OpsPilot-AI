# Sesión 03 — especificación de continuación durable

Estado: EN CURSO por petición explícita del autor el 2026-10-23. T03-01 y ADR-0008
aprobados tras revisión de cierre/riesgos S02; T03-02 implementada/probada localmente.
Intake T03-03, lecturas/cancelación T03-04 y worker local T03-05 implementados.
Reclaim/retry/crash suite integral pendientes T03-06; AC03-04/05/06 parciales.
Base técnica S02 en 660f7d3, según [cierre](SESSION_02_CLOSURE.md).
[Arranque y supuestos](../../specs/003-workflows/start.md),
[paquete técnico revisable](../../specs/003-workflows/contracts.md) y ADR-0008.
[Alcance de persistencia](../../specs/003-workflows/persistence.md) y
[resultados T03-02](SESSION_03_PERSISTENCE_REVIEW.md). Aceptación humana global S03
pendiente de T03-08; aprobar entrada no valida durabilidad ni producción.
Sin autorización de commit, push ni despliegue.

## Requisitos y objetivo

REQ-WF-01/02 y frontera de REQ-WF-03 del [PRD](../product/PRD.md): aceptar un ticket
una vez, persistir workflow/job/audit/respuesta juntos y recuperar trabajo local
tras crashes. REQ-PLAT-01/02 y REQ-HAR-01 se mantienen como regresión obligatoria.
Paquete: [spec](../../specs/003-workflows/spec.md), [plan](../../specs/003-workflows/plan.md),
[tareas](../../specs/003-workflows/tasks.md) y [checklist](../../specs/003-workflows/checklist.md).

## Entrada y exclusiones

Antes de código: nueva autorización explícita de implementación, revisión humana del
diff/riesgos y contratos S03 cerrados. Confirmar que la base conserva los gates S02,
PG18/IdP reales, lock/digests y secretos locales protegidos. Un cambio de imagen,
contrato o código invalida reutilizar automáticamente el GO de 660f7d3.

Implementación futura limitada a intake, lecturas autorizadas, cancelación CAS,
cola PG, worker lineal, evidencia local, leases/fences y recuperación. Sin LLM,
RAG, frameworks multiagente, approvals, runner IT, VPN, mutaciones externas ni UI.
No crear tablas de propuestas/intents/outbox sin la necesidad de S05. No declarar
resolución del ticket por completar un job. No añadir adaptadores ficticios al producto.

## Contratos que deben cerrarse antes de implementar

Los siguientes son acuerdos propuestos; no modifican el OpenAPI ejecutable de S02.
Versionar un contrato de workflows y sus ejemplos/negativos antes de T03-02.
Mantener los cuatro GET de [plataforma](../architecture/API_CONTRACTS.md).

| Operación propuesta | Contrato y autorización |
|---|---|
| POST /v1/incidents | operator habilitado, título 1..200 y descripción 1..4000, sin campos libres adicionales; Idempotency-Key UUID obligatorio; 202 con incident_id/workflow_id solo después del commit |
| GET /v1/incidents/{id} | operator creador o auditor con grant explícito; mismo 404 para inexistente/no visible, sin revelar metadatos |
| GET /v1/workflows/{id} | Igual visibilidad que el ticket; state/version/definition_version, cancel_requested_at y referencias redacted; nunca owner de lease o credenciales |
| POST /v1/workflows/{id}/cancel | operator creador y If-Match de versión obligatorio; versión obsoleta 409; 202 confirma intención durable, no rollback ni cierre del ticket |

Admin no hereda operator/approver/auditor; el acceso a audit S02 mantiene auditor/admin.
Auditor no cancela ni crea por tener lectura. Token inválido 401, rol no permitido
403, input/header ausente o inválido 422, dependencia indispensable caída 503.
El contrato nuevo debe fijar el wire exacto de If-Match/ETag, errores/replay y
respuesta de terminales antes del código; no resolverlo mediante un set_state genérico.

Idempotencia por principal local (issuer/sub ya ligado por S02), ruta y UUID; hash
de cuerpo validado y canónico, sin floats, con defaults y versión definidos por
contrato. Misma clave/hash devuelve status/cuerpo originales aunque se pierda la
respuesta o el token se renueve; cuerpo distinto 409. Revalidar identidad/permisos
antes de replay, sin devolver datos revocados. Retención mínima 7 días; no reciclar
una clave de un workflow activo. Política exacta de limpieza debe aprobarse antes
de implementarla; S03 puede conservar registros sin borrado automático.

## Persistencia y frontera de confianza

Migración incremental desde 0001: incidents, workflows, workflow_steps, jobs,
api_idempotency y evidence. FK/UNIQUE/CHECK/índice parcial para un workflow activo
por ticket; datos reales de S02 preservados. No modificar migraciones históricas.
[DATA_MODEL](../architecture/DATA_MODEL.md) fija el modelo objetivo.

Transacción de intake: ticket OPEN + workflow QUEUED con definition_version + job
READY + evento + respuesta idempotente. Falla audit/DB/commit: no ticket ni respuesta
aceptada; jamás 202 antes del commit. Carreras de clave se resuelven con constraint
UNIQUE y transacción, no memoria del proceso ni check-then-insert sin protección.

Extender el appender SQL cerrado de ADR-0006 mediante migración y contrato versionado
antes de emitir eventos S03. Servidor asigna seq/hash/actor/tiempo y valida payload;
no habilitar JSON arbitrario para resolver campos nuevos. Pruebas de instancia,
paridad SQL/Python, atomicidad y permisos conservadas. Rol worker dedicado con grants
mínimos revisados; API y worker sin DDL ni UPDATE/DELETE de audit.

Evidence inmutable, con hash/observed_at/collector/source/independence_role y contenido
redacted. Un snapshot de intake no es verificación independiente ni demuestra
resolución. No almacenar tokens, contraseñas ni razonamiento interno. Retención de
lab propuesta en DATA_MODEL; aceptación de privacidad pendiente antes de datos reales.

## Worker lineal y estados permitidos

[WORKFLOW_ENGINE](../architecture/WORKFLOW_ENGINE.md) y
[workflow-v1](../../contracts/workflow-v1.json) son las fuentes normativas. Persistir
version y definition_version; CAS sobre cada transición. Sin nuevas aristas implícitas.

Primer paso S03 propuesto: leer el ticket persistido, validar invariantes y materializar
su snapshot/hash como evidencia local real; pausar en NEEDS_OPERATOR con motivo
cerrado al requerirse investigación que S03 no proporciona. Es una operación durable
verificable; no simula un diagnóstico ni usa una herramienta falsa. El contrato de
ese paso y su error permanente deben revisarse antes de implementación.

QUEUED → INVESTIGATING → NEEDS_OPERATOR es el camino nominal acotado. RETRY_WAIT
solo para fallos transitorios locales, retomando INVESTIGATING. CANCELLED sigue las
guardas normativas. PLAN_READY/AWAITING_APPROVAL/EXECUTING/VERIFYING/SUCCEEDED no
se activan con un executor de prueba en producción. OUTCOME_UNKNOWN permanece
protegido contra reenvío y se prueba como guarda; ejecución/reconciliación externa
y cuarentena real de recurso pertenecen a S05/S06, sin afirmar REQ-WF-03 completo.

Claim corto de job mediante FOR UPDATE SKIP LOCKED; owner aleatorio, fence creciente,
lease 60 s, heartbeat 15 s y reloj DB; poll 2 s con jitter. No lock de DB durante
trabajo fuera de la transacción. Claim modifica solo job; cuando se toque workflow,
respetar orden workflow → job → audit stream. Evitar deadlocks y documentar retries.

Guardar resultado/evidence/siguiente job/audit exige owner, fence, lease no vencida
y versión válidos en el mismo commit. Heartbeat no revive un lease vencido. Reclaim
incrementa fence; worker antiguo no puede confirmar resultado ni resucitar cancelación.
Entrega interna at-least-once con efectos locales deduplicados; no prometer exactly-once.

## Errores, cancelación y recuperación

Máximo 3 intentos transitorios, backoff full jitter acotado a 30 s; deadline y
presupuesto activo 300 s persistidos por reloj DB, sin reset al reiniciar. Sin
proveedor LLM no se reserva coste ficticio; el esqueleto de presupuesto conserva
límites temporales y permite extensión posterior por migración.

Error permanente/auth/schema: no retry automático; pausa con reason_code cerrado.
Deadline agotado sin efectos externos: salida auditada definida en contrato, sin
ciclo infinito. DB caída: sin aceptar tickets ni reclamar trabajo; preservar fail-closed
S02. Tras crash, READY o lease expirado se recupera; DONE no se ejecuta de nuevo.

Cancelación serializada con workflow/job; invalida trabajos pendientes y tokens de
ownership, y persiste auditoría atómica. En estados futuros con efecto ambiguo se
registra cancel_requested_at y se reconcilia, nunca se salta OUTCOME_UNKNOWN a retry.
No cierre automático de incidents: el estado OPEN es independiente del workflow.

## Aceptación propuesta y pruebas obligatorias

| AC / test propuesto | Given / When / Then exigible |
|---|---|
| AC03-01 / TEST-03-ATOMIC | Fallo en cada punto de intake/audit/commit: cero estado parcial, sin 202; éxito: todas las filas y respuesta originales |
| AC03-02 / TEST-03-IDEMPOTENCY | 20 solicitudes concurrentes con misma clave/hash y pérdida de respuesta: un ticket/workflow/job/evento lógico; otro hash 409; otros sujetos/rutas no se mezclan |
| AC03-03 / TEST-03-AUTH | Sin token/grant, rol IdP inventado, principal revocado, replay revocado y acceso cruzado: sin escritura/fuga; admin no hereda operator |
| AC03-04 / TEST-03-CRASH | Dos procesos worker y al menos 100 jobs, kills antes/después de claim, antes/después de resultado+audit y antes de ack: recuperación sin pérdida ni doble efecto local confirmado |
| AC03-05 / TEST-03-FENCE | Worker antiguo tras expiración/reclaim y heartbeat tardío no escribe evidencia/estado/audit; fence y CAS se comprueban con PG real |
| AC03-06 / TEST-03-CANCEL | Cancel vs claim/completion concurrentes y versión antigua: primera transacción válida decide; sin resurrección ni aceptación parcial |
| AC03-07 / TEST-03-RETRY | Reinicio durante RETRY_WAIT y deadline: available_at/intentos/presupuesto persisten, sin reset ni tormenta; fallos permanentes no reintentan |
| AC03-08 / TEST-03-MIGRATE | PG vacío y N-1→head con datos S02; sin drift ni ampliación DDL/audit; rol worker limitado |
| AC03-09 / TEST-03-CONTRACT | API/eventos/snapshot golden y negativos; definición desconocida pausa; aristas ilegales y UNKNOWN→EXECUTING/RETRY_WAIT rechazadas |
| AC03-10 / TEST-03-REGRESSION | Todos los gates S02, fresh PG, recovery, tres scans, contratos y CI de la revisión final aprobados; sin secrets/fakes de producto |

Unit fakes solo en tests. Durabilidad se prueba con PG18, IdP y procesos reales;
registrar kill points, exit codes, fences/owners, contadores y ledger antes/después.
No sleeps ciegos como prueba de crash ni mocks de commit para declarar recuperación.

## Entrega y decisiones pendientes

T03-01 aprobada por autor; T03-02 implementa migración/grants/appender v2 y lectura
mixta con pruebas PG/IdP reales de almacenamiento. T03-03 implementa intake atómico,
idempotencia y recuperación de procesos API. T03-04 implementa lecturas/cancelación
([revisión](SESSION_03_ACCESS_CANCEL_REVIEW.md)); T03-05 implementa worker/leases/fences
y snapshot local ([revisión](SESSION_03_WORKER_REVIEW.md)). T03-06..08 pendientes,
incluidos reclaim/retry y crashes adversariales integrales de jobs S03.
El paquete concreta wire OpenAPI, lectura/cancelación, appender/evento v2, permisos
worker, handler local y DefinitionVersion. Persistencia/appender/lector instalados
en T03-02, rutas de dominio en T03-03/04 y handler local en T03-05. La semántica
objetivo de recuperación/reintentos descrita arriba sigue T03-06.
R01/R02/R14 guían adversariales; si no se logra el motor acotado,
registrar NO-GO y evaluar alternativa por ADR, sin instalar Temporal automáticamente.

DoD futuro: AC03-01..10 ejecutados, migraciones/contratos revisados, CI del SHA final
satisfactoria, evidencia completa y aceptación humana documentada. GO S04 solo tras
ese cierre y una nueva petición; no autoriza IA ni producción por haber pasado S02.
