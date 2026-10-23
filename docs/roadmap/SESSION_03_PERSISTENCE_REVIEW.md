# S03 — revisión de persistencia T03-02

2026-10-23, Europe/Madrid. T03-01 aprobada para implementación por el autor, junto
al cierre/riesgos S02 y ADR-0008: «Apruebo tras revisión; continuar T03-02».
T03-02 IMPLEMENTADA y PROBADA localmente; no aceptación global de S03 ni producción.
Revisión del asistente, no auditoría independiente. Sin commit/push/despliegue.

## Cambio y límites

[Spec acotada](../../specs/003-workflows/persistence.md). Migración 0002 desde 0001
intacta: incidents, workflows, workflow_steps, jobs, api_idempotency y evidence;
FK compuestas, constraints de estado/budget/ownership y dos índices parciales para
workflow/job activos. Evidence solo snapshot de intake redacted, sin UPDATE/DELETE;
idempotency liga respuesta/principal/incidente/workflow, sin limpieza automática.

Appender v2 separado, SECURITY DEFINER con owner no-login/search_path fijo y sin
DDL. Payloads, actores de servicio/creator, aristas/reasons, versión y snapshot
validados; referencias de evidence ligadas a su workflow. Solo dos columnas de
evidence legibles por audit_owner; sin texto de incidents ni payload de evidence.
state_snapshot privado append-only ligado por su hash al evento. Función y hashes
S02 preservados; HTTP/DTO/OpenAPI de audit admiten unión discriminada v1/v2.
Cuatro GET existentes, mismos roles; endpoints de dominio aún no implementados.

Bootstrap añade worker privado sin rotar credenciales existentes; no DDL/herencia/
bypass, CONNECT solo lab, grants por columna de la matriz. PUBLIC sin CONNECT/TEMP
en bases administrativas del cluster sintético propio. API no recibe DSN worker.
No worker ejecutable, claim/heartbeat/retry/reclaim ni efectos externos implementados.
Guardas SQL no sustituyen CAS/leases/fences del job store ni su crash suite futura.

## Pruebas y fallos conservados

Baseline: check PASS y 411 tests PASS antes de modificar producto. Nuevas pruebas
PG detectaron drift del default volátil del deadline: corregido a statement_timestamp
más 300 s, sin desactivar compare_server_default. Primeras ejecuciones del paquete:
9 FAIL/49 PASS por binding de varchar del fixture y precedencia de operadores JSON
en SQL; ambos corregidos. Informes brutos privados preservados, no publican DSNs.

Resultados: 482 tests PASS en Windows y 482 PASS en contenedor Linux sin root, cero
fallos/errores/skips; 121 integraciones reales por entorno (50 S02 + 71 nuevas).
Advertencia upstream Starlette/TestClient, no fallo. Incluyen:

- Base vacía y N-1 con identidad/grant/eventos reales; función v1 y cadena intactas.
- Upgrade repetido no-op; downgrade destructivo rechazado; fallo DDL real revierte
  tablas, constraints y revisión de migración sin estado parcial.
- Paridad SQL/Python de hashes/snapshots y lectura HTTP real v1/v2 con Keycloak,
  sin state_snapshot/hash/ownership en el cuerpo público.
- API/worker/provisioner con permisos reales y negativos; owner sin CREATE/login,
  permisos por columna y CONNECT worker restringidos al lab.
- Evidence deduplicada, payload cerrado, hash/source correctos, FK entre entidades
  y rechazo de evidencia inexistente/ajena; audit fallido revierte transición/head.
- Pausa de definición desconocida sin fallback, cancelación desde RETRY_WAIT y
  cancelación diferida en estados futuros; UNKNOWN→EXECUTING/RETRY_WAIT denegados.

Golden estable copiado a tests/fixtures para incluirlo en la imagen de pruebas;
el snapshot histórico en artifacts/session-03/start no se modifica. Excepciones
del scanner solo para cuatro hashes públicos exactos de ese fixture, contrastados
con bytes canónicos; no filtros nuevos ni secretos suprimidos.

El primer check del capturador final falló por enlazar manifest.json antes de que
el propio capturador lo generase. Se conserva ese intento; check se repite tras
generar la evidencia completa, sin cambiar ni omitir controles.
La repetición señaló formato Ruff pendiente tras mover el fixture; corregido sin
cambio funcional. Se repiten sus 199 pruebas de contrato y se conserva el manifest
de las suites completas, separado del manifest final de documentación/formato.

[Evidencia final](../../artifacts/session-03/persistence/verification.json),
[migración del lab](../../artifacts/session-03/persistence/lab-migration.json) y
[manifest](../../artifacts/session-03/persistence/manifest.json). La migración del
lab conservó cuatro principals, cuatro grants, ocho eventos y cuatro heads S02.
La suite usa bases efímeras separadas y las elimina solo tras comprobar su nombre.

## Siguiente tarea y gates pendientes

T03-03: intake/idempotency/UoW/audit atómicos y carreras reales de 20 requests;
T03-04..06: cancelación HTTP, worker y 100 jobs/crashes/fences. AC03-01..07 y AC03-09
de motor siguen sin aceptación. AC03-08 de almacenamiento probado localmente.
check final y parada del lab se registran con exit codes en evidencia; volumen y
credenciales conservados. No se arrancó una API de imagen antigua contra schema 0002.

No CI del árbol actual, build/scan de API actual, scans nuevos PG/IdP ni recovery
completo de imagen actual: T03-07 pendiente, sin reutilizar el GO de 660f7d3. La imagen
Linux construida es solo de tests, no una release. R01/R02/R14 y privacidad vigentes;
R15 conserva mantenimiento y límites musl/linux-amd64. NO-GO S04/producción.
