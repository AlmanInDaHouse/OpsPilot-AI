# S03 — revisión técnica del arranque T03-01

2026-10-23, Europe/Madrid. S03 iniciada por petición expresa. T03-01 tiene paquete
técnico para revisión humana; no está aceptada ni se declara S03 completada.
Revisión del propio asistente, no auditoría independiente. Sin commit/push.

## Base y alcance observado

Git inicial limpio en main, HEAD 3b91f58. GO técnico S02 para 660f7d3 con evidencia
remota en SESSION_02_CLOSURE, intacta. No se extrapola al árbol actual. La petición
de arranque no acredita la revisión humana de diff/riesgos S02 que sigue pendiente.

[Arranque/supuestos](../../specs/003-workflows/start.md),
[contratos concretos](../../specs/003-workflows/contracts.md) y
[ADR-0008 propuesto](../decisions/0008-workflow-contract-boundary.md). Contratos nuevos:
OpenAPI de cuatro operaciones, eventos v2, dos snapshots, paso y matriz de grants.
Se fijan If-Match/ETag por entidad/versión, errores, replay/revoke, retención sin
limpieza automática, cancelación terminal/ambigua y frontera de independencia.

Definición desconocida: retener estado, job DEAD y workflow.blocked, sin inventar
arista QUEUED→NEEDS_OPERATOR ni ejecutar v1 por defecto. Ledger v2 propuesto con
snapshot privado inmutable; v1 y sus hashes conservados. Worker dedicado sin DDL,
claims IdP, secretos de API ni escritura audit directa. Evidence de intake sin
texto libre; job completo no declara ticket resuelto.

Sin cambios en src, migrations, infra, imágenes, lock, dependencias o workflows CI.
Sin endpoints ni motor S03, LLM, RAG, VPN, runners ni efectos externos. Cada nueva
garantía operativa exige implementación y pruebas PG/IdP/procesos reales posteriores.

## Verificación y limitaciones

Inicial: doctor PASS, check PASS; test con lab detenido: 162 PASS, 2 FAIL, 48 ERROR.
No se omitieron ni convirtieron fallos en éxito. Arranque exclusivo de contenedores
existentes opspilot-s02; PG/Keycloak/API saludables, sin reconstruir ni borrar datos.
Repetición: 212 PASS, cero skips, 50 integraciones reales. Logs completos privados.

Contrato nuevo: 199 pruebas PASS. Incluyen OpenAPI/JSON Schema estándar, todas las
parejas de estados contra reasons/aristas permitidos, UNKNOWN, actores de sistema/
operator, definición desconocida, longitudes/campos extra, ETags, códigos de error,
referencias redacted y golden canónico UTF-8. No son pruebas de auth HTTP S03, CAS,
SQL, permisos instalados, leases, atomicidad ni crashes. Matriz RBAC comprobada como
especificación, no como autorización ejecutable.

Suite completa posterior: 411 PASS, cero skips, 50 integraciones S02 reales y 199
tests de contrato nuevos. Advertencia upstream de Starlette/TestClient; no fallo.
Scanner inicial del paquete detectó dos hashes de texto sintético del golden;
se contrastaron con los bytes de entrada y registraron dos excepciones exactas,
con razón documentada; sin desactivar filtros ni ampliar exclusiones del scanner.
Resultados finales y hashes en [evidencia](../../artifacts/session-03/start/verification.json).

No se ejecutaron scans nuevos, PG fresco/recovery ni CI S03: no cambiaron sus inputs
de runtime. Son gates pendientes para implementación S03, no PASS heredados. El GO
S02 sigue limitado a su SHA; R15 mantiene restricciones musl/linux-amd64 y mantenimiento.

## Revisión pendiente y siguiente tarea

SESSION_03_SPEC exige «revisión humana del diff/riesgos y contratos S03 cerrados»
antes del código. El paquete anterior deja esa revisión concreta. Se solicita
aceptación humana de cierre/riesgos S02 y T03-01; no se marca por inferencia.
Después: T03-02, migración incremental y grants/appender versionado; luego intake,
worker/fences, crashes y gates T03-03..08. R01/R02/R14 y privacidad siguen abiertos.
NO-GO S04 y producción. No publicación ni infraestructura externa autorizadas.
