# S03 — revisión de intake T03-03

2026-10-23, Europe/Madrid. Implementación exclusivamente local solicitada por el
autor. T03-03 IMPLEMENTADA y PROBADA; no cierre de S03 ni validación de producción.
Autocrítica del asistente, no auditoría externa. Sin commit/push/merge/release.

## 1. Estado inicial y trabajo preservado

Root C:/Users/manul/OneDrive/Escritorio/opspilot-ai, rama main, HEAD
3b91f58c2f54a59ea5825c41af0550a9acb416de. Árbol con T03-01/T03-02 sin publicar:
26 archivos tracked modificados y contratos/migración/tests/evidencias untracked.
Sin reset, stash ni sobrescritura de esos cambios. No se reimplementó T03-02.

La [evidencia anterior](../../artifacts/session-03/persistence/verification.json)
reporta 482 PASS Windows/Linux, 121 integraciones por entorno. Baseline actual
antes de editar producto: check PASS y 482 PASS Windows, cero skips.
[Preservación comprobada](../../artifacts/session-03/intake/foundation-preservation.json):
0001/0002 y adaptadores audit/models conservan hashes del manifest T03-02.
Los snapshots start/persistence siguen intactos. No había repositorio de intake:
T03-02 aportaba tablas, appender, modelos y UoW general, no CreateIncident.

## 2. Contratos definitivos y trazabilidad

REQ-WF-01/02 → AC03-01/02 → T03-03 → [spec acotada](../../specs/003-workflows/intake.md)
→ [contrato aprobado](../../specs/003-workflows/contracts.md) y
[OpenAPI](../../contracts/workflows.openapi.json) → implementación/tests/evidencias.
No cambios de wire ni nuevas decisiones de autoridad respecto de T03-01/ADR-0008.
Solo se actualiza el estado de implementación del OpenAPI independiente S03.

POST /v1/incidents: operator local explícito y activo; admin/auditor/approver no lo
heredan. JSON con title 1..200 y description 1..4000 puntos Unicode, sin trim ni
normalización; sin extras/coerción. Idempotency-Key UUID obligatorio con forma
canónica, mayúsculas aceptadas y normalizadas. Rechazo de claves JSON duplicadas,
BOM, NUL, surrogates aislados, NaN/Infinity y UTF-8 inválido. Sin query parameters.
Límite 16 KiB reales/10 s preservado; headers de autoridad repetidos: 422.

202 solo tras commit; body exacto incident_id/workflow_id. Errores cerrados
401/403/409/422/503, sin datos SQL/input. WWW-Authenticate en 401; request_id nuevo,
no-store y nosniff en cada respuesta. Las cuatro rutas GET S02 se conservan;
las tres operaciones de lectura/cancelación S03 todavía no están instaladas.

## 3. Arquitectura implementada

Endpoint/DTO/parser en entrypoints llaman CreateIncident mediante puertos. Dominio
de intake puro, sin FastAPI/SQLAlchemy; adaptador PostgreSQL contiene SQL y enlaza
PostgresWorkflowAppender. PostgresIntakeUow hereda el PostgresUow existente, solo
añade el repositorio y traducción de errores DB. No otra implementación transaccional.
El checker AST aplica también las fronteras del módulo incidents.

El endpoint autoriza antes de parsear input; el repositorio vuelve a comprobar
principal enabled y grant operator vigente antes de replay/escrituras. Un revoke
confirmado antes de esa consulta deniega. Una petición concurrente con revoke
usa el snapshot de autorización vigente de su consulta, como S02; sin cache de grants.

## 4. Archivos creados y modificados por T03-03

- Nuevos: src/opspilot/incidents/domain/intake.py y application/create.py, sus
  inicializadores; adapters/postgres/incidents.py y entrypoints/api/intake.py.
- Modificados: entrypoints/api/app.py y dto.py; identity/domain/principal.py;
  scripts/check_architecture.py y verify_recovery.py; tests/contract/test_api.py,
  integration/conftest.py e integration/test_identity.py.
- Nuevos tests: unit/test_intake.py, contract/test_intake_api.py,
  integration/test_incident_intake.py e integration/intake_process.py.
- Spec intake.md, esta revisión y artifacts/session-03/intake; handoff, tareas,
  checklist, plan/spec, contratos, README/AGENTS, arquitectura y trazabilidad.

Las rutas de código anteriores se entienden bajo src/opspilot y las de tests bajo
tests. El [manifest](../../artifacts/session-03/intake/manifest.json) contiene rutas
completas del repositorio y hashes; Git conserva también los cambios T03-01/02.

## 5. Unit of Work

Una sesión/conexión/transaction contiene incident OPEN/version 1; workflow QUEUED/
version 1/definition 1; step intake_snapshot PENDING/attempt 1; job READY sin owner,
lease ni intentos; incident.created v2 y api_idempotency con respuesta 202.
Deadline y timestamps se asignan con defaults PG aprobados. No evidence de worker
anticipada ni ejecución del job. Se llama commit una sola vez tras todas las escrituras.
PostgresUow.__exit__ hace rollback/close también si una escritura o commit falla.

## 6. Algoritmo durable de idempotencia

Scope PK: principal_id local + ruta literal /v1/incidents + key UUID. request-hash-v1
usa SHA-256 de JSON UTF-8 ensure_ascii=False, sort_keys=True, separadores compactos,
allow_nan=False, body validado + route + schema_version=1. Golden idéntico en ambos OS.
No token, salt, proceso, Redis ni hash() de Python en la autoridad de idempotencia.

Después de autorizar se lee el registro confirmado. Mismo hash: 202/IDs originales,
sin escrituras/eventos nuevos. Otro hash: 409 sin revelar el body previo. Otro sujeto
tiene scope distinto; token renovado del mismo sujeto conserva sus claves. Sin fila:
se preparan todas las referencias y se intenta INSERT de respuesta completa.
No limpieza automática ni reciclaje; se conservan todas las claves, mínimo siete días.

## 7. Concurrencia PostgreSQL

La PK api_idempotency_pkey decide la carrera, no la lectura inicial. Se usa INSERT
normal porque 0002 exige FK inmediata y respuesta completa; ON CONFLICT DO NOTHING
sin rollback conservaría las filas provisionales perdedoras. El índice único espera
al competidor no confirmado. Si ese competidor revierte, el INSERT puede continuar;
si confirma, PostgreSQL devuelve 23505 y solo para esa PK se emite IdempotencyRace.

El UoW perdedor revierte TODO. CreateIncident abre una transacción nueva READ COMMITTED,
reautoriza y relee la respuesta ganadora. No consultas dentro de una sesión abortada,
savepoint que conserve incidentes, mutex Python ni bloqueo global. Los streams de
auditoría son por incidente; keys independientes no comparten esos locks. El orden
de escritura es único, sin locks inversos sobre workflows/jobs existentes.
Statement/lock timeout acotan esperas; timeout/otro error DB/commit incierto: 503.
No retry ciego del commit; reintento cliente con la misma key recupera estado durable.

## 8. Auditoría v2

Se reutiliza audit_append_v2 sin cambiar SQL histórico ni envelope v1. incident.created
usa stream/aggregate_id del incidente, versión 1, INTAKE_ACCEPTED y evidence_ids vacío.
Actor del principal autenticado; el appender SQL comprueba workflow QUEUED del creador.
La correlación workflow está en su FK/registro durable, no se añade al payload cerrado.
Hash chain/seq/fecha/event_id los asigna DB. No texto libre, JWT, prompts ni secretos.
Este evento de creación no lleva state_snapshot: así lo exige el contrato aprobado.

## 9. Tests ejecutados

Suites finales: __567 PASS Windows y 567 PASS Linux__, cero failures/errors/skips;
__155 integraciones reales por entorno__, 34 nuevas de intake. PostgreSQL18 y
Keycloak reales, login PKCE y verificación JWT de producción. Tests Linux bajo UID
no root; ninguna integración sustituida por mock. Warning upstream Starlette/TestClient.

[Resultados Windows](../../artifacts/session-03/intake/tests-windows.json) y
[Linux](../../artifacts/session-03/intake/tests-linux.json) incluyen 15 observaciones
instrumentadas por entorno; raw XML/logs privados identificados mediante hash.
Los fakes de tests unitarios/contrato no se usan para acreditar garantías SQL.
[Verificación completa](../../artifacts/session-03/intake/verification.json) registra
comandos, exit codes, intentos y gates finales, sin atribuir CI remota al árbol local.

## 10. Atomicidad y fallos reales

Triggers de prueba en DB efímera provocan error real en INSERT de incident, workflow,
step, job, audit_event e idempotency. El HTTP devuelve 503 y los siete contadores
incident/workflow/step/job/idempotency/event/stream permanecen iguales. Se prueba
también FK inválida y rechazo SQL de tipo/payload/actor/versión de appender.

Constraint trigger DEFERRABLE INITIALLY DEFERRED en api_idempotency rechaza COMMIT
real: dentro de la sesión ya existe el registro; el commit se intenta y PG lo
rechaza. Otra conexión confirma cero estado parcial, sin 202; la misma key funciona
tras retirar la inyección. No excepción ficticia de commit. Otro test pausa el
commit y comprueba que ni la respuesta HTTP ni las filas son visibles antes de él.

Procesos terminados abruptamente antes/después de commit: antes, cero filas;
después, las siete filas confirmadas. Versiones HTTP reciben TransportError antes
de cualquier respuesta. Replay deja exactamente un conjunto lógico en ambos casos.
El test de timeout bloquea una key con una transacción real, provoca lock_timeout,
comprueba rollback del perdedor y luego replay de la ganadora confirmada.

## 11. Evidencias de concurrencia y recuperación

- Veinte solicitudes misma key/body: 20 respuestas 202 idénticas y una fila nueva
  en cada tabla contabilizada, incluido un único evento lógico de creación.
- Veinte con misma key y dos bodies: 10 respuestas 202 originales y 10 conflictos
  409; una creación. Veinte keys independientes: 20 creaciones.
- Dos principales pueden usar la misma key sin compartir IDs; un JWT renovado del
  mismo principal recupera la respuesta previa. Revoke/disable impiden replay.
- Dos procesos Uvicorn de composición real reciben 20 HTTP concurrentes: 20 respuestas
  idénticas, una creación. Ambos mueren; una tercera instancia recupera bytes iguales.
- Carrera adicional fuerza dos lecturas iniciales sin fila; la PK decide y el perdedor
  revierte, demostrando que la lectura previa no concede exclusividad.

El laboratorio permanente tiene un intake sintético de smoke, sin worker. El gate
de reinicio y replay posterior se registra separado en verification.json; no es
backup/restore ni prueba del futuro motor de jobs.

## 12. Fallos reproducidos y corregidos

Primer paquete: 23 PASS/1 FAIL por llamada incorrecta a verify_chain en el test;
se añadieron head/seq y se afirma su resultado. Segundo: 31 PASS/1 FAIL por import
faltante de DependencyUnavailable en el nuevo test. Ambos intentos se conservan.
Primer run Linux completo: 563 PASS/2 FAIL; SIGTERM era cierre cooperativo de
Uvicorn, que esperaba la pausa de test. SIGKILL/muerte abrupta y limpieza acotada
corrigen el harness de fallos; repetición Linux 565 PASS, cierre ampliado 567 PASS.

Check inicial detectó un literal sintético secret en un negativo de schema; Ruff
desplazó el primer pragma a la llave de cierre. Se situó en la línea del literal y
se repitieron sus cuatro negativos con PG real: PASS. Único cambio posterior a las
suites completas en inputs de tests: ubicación de ese comentario. Manifests de
inputs probados/final separados. Sin nuevos filtros globales ni allowlist.
BuildKit multi-target falló al extraer un snapshot padre ausente; construcción
secuencial tests/API pasó sin borrar cachés/volúmenes. Helper de smoke intentó
contar tablas en la DB administrativa; se corrigió a la DB del DSN app y se reutilizó
la misma clave ya confirmada, sin crear otro incidente.

## 13. Autocrítica, límites y riesgos residuales

Revisión posterior de capas, locks, atomicidad, replay y redaction realizada sobre
código/tests reales. No se identificó un defecto abierto de doble creación o 202
prematuro en este alcance. El perdedor hace trabajo provisional que después revierte;
muchas carreras pueden consumir conexiones y devolver 503 al agotar timeout. Eso
mantiene atomicidad y exige retry con la misma key; no promete disponibilidad ilimitada.

Una desconexión durante commit puede ser ambigua: 503, después replay para conocer
lo confirmado. Los tests matan procesos antes/después de commit y rechazan un commit
real, pero no enumeran todos los fallos físicos posibles del servidor/red/disco.
Las pruebas no acreditan HA, backup/restore ni exactly-once de efectos externos.
Hash chain no es WORM frente al administrador de DB. API tiene los grants T03-02;
la aplicación es frontera confiable, sin nueva promesa de aislamiento RLS por usuario.

R01/R02/R14, privacidad y mantenimiento R15/musl/linux-amd64 siguen vigentes. Ningún
worker, lecturas/cancelación HTTP, retry/reclaim/fence de ejecución ni test de 100 jobs
implementados. REQ-WF-01/02 siguen parciales; REQ-WF-03 no se declara satisfecho.
CI de este árbol sin publicar: NOT_RUN. Sin GO S04 ni producción.

## 14. GO / NO-GO para T03-04

GO técnico local para preparar T03-04, sujeto a los gates finales registrados en
verification.json. No iniciar T03-04 de forma automática. Windows/Linux, contratos,
integraciones, calidad y seguridad se comprueban localmente; no se hereda CI del
SHA S02. Aceptación global S03, publicación/CI y autorización de la siguiente tarea
siguen fuera de este cierre. NO-GO S04/producción.

## 15. Estado Git y operación

HEAD/base main 3b91f58 sin nuevos commits. Cambios T03-01/02 preservados y T03-03
añadidos al mismo árbol local. Sin push/merge/release/despliegue ni infraestructura
externa. Imágenes/tests/laboratorio locales exclusivamente. Estado final y parada
con volumen preservado se registran en verification.json. No modificar snapshots
anteriores para reflejar resultados de este paquete.

## LO QUE DEBE COMPRENDER EL ARQUITECTO

__Por qué es atómica.__ En [CreateIncident.execute](../../src/opspilot/incidents/application/create.py)
create, audit y remember usan uow.incidents; ese repositorio comparte uow.session.
Solo después se llama uow.commit. Si INSERT de jobs falla, PostgresUow.__exit__
revierte también incident/workflow/step. Si falla auditoría, tampoco se confirma el
ticket. El test de constraint diferida verifica incluso el rechazo del COMMIT real.

__Qué hace UNIQUE.__ La PK [api_idempotency](../../migrations/sql/0002_workflows.sql)
impide dos registros con principal/ruta/key iguales, incluso desde procesos distintos.
Una lectura inicial sin fila no reserva nada. Dos APIs pueden preparar IDs diferentes;
solo una puede confirmar la misma clave. No depende de que compartan memoria.

__Cómo evita duplicados.__ En [remember](../../src/opspilot/adapters/postgres/incidents.py)
solo 23505 de api_idempotency_pkey es carrera. Al fallar ese INSERT se revierte toda
la creación provisional perdedora. Una transacción nueva relee los IDs ganadores;
si el hash difiere, devuelve 409. No queda un ticket huérfano del intento perdedor.

__Si muere tras COMMIT.__ La respuesta ya está en PG junto al ticket/job/evento.
Aunque el socket nunca entregue 202, el siguiente POST autorizado con la misma
key/body devuelve los IDs originales. Los tests HTTP matan Uvicorn en ese intervalo
y observan TransportError y replay 202, con un solo conjunto de filas.

__Por qué audit comparte UoW.__ Si se confirmara el ticket antes de auditar, un fallo
de appender dejaría un alta sin ledger; si se auditara antes en otra transacción,
podría quedar un evento de un ticket inexistente. PostgresWorkflowAppender recibe
exactamente la sesión del repositorio: evento/head y alta confirman o revierten juntos.

__Por qué READY no ejecuta nada.__ create hace INSERT de un job con defaults READY,
fence 0, attempts 0, owner/lease NULL. No existe polling/claim/handler en este cambio;
no se arranca un proceso worker. El smoke comprueba esos valores tras el reinicio.
El incidente continúa OPEN y no se afirma que la VPN esté diagnosticada o resuelta.
