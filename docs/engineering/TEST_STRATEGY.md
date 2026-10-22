# Estrategia de validación

Estado: tests del harness disponibles; todos los tests de producto PROPUESTOS.
Tests tienen IDs y trazabilidad. Fixtures/fakes solo en tests; integración no debe
transformarse en fake para obtener verde. Clock/UUID inyectados en dominio.

| Capa / ID | Casos requeridos y entorno |
|---|---|
| TEST-01-HARNESS | Links rotos, JSON refs inexistentes, terminal inválido, arista divergente, roadmap incompleto, trazas falsas y auth de endpoint; tempfile, stdlib |
| TEST-02-AUTH | API sin token, issuer/aud/alg/exp/nbf/iat/kid, unknown principal, role claims falsos, revoke local, cache JWKS expirada; fixtures unit + IdP real en integración |
| TEST-02-AUDIT | Evento+principal atómicos, rollback si appender falla, secuencia concurrente y UPDATE/DELETE denegados, golden hash; PG18 real |
| TEST-02-CONTRACT | Ejemplos válidos/negativos según schema, errores redacted y parity con OpenAPI; FastAPI HTTP y validador estándar |
| TEST-02-MIGRATE | DB vacía→head, N-1→head cuando exista, Alembic check sin drift; roles app no DDL; sin downgrade destructivo |
| TEST-02-ARCH | imports prohibidos, ciclos, acceso HTTP/PG desde dominio, excepción composition root; fixtures negativos separadas |
| TEST-02-SUPPLY | lock/digests, secret scan, SCA/Bandit; conservar reporte y findings |
| TEST-03-ATOMIC | Ticket/workflow/job/audit/idempotency todo o nada; duplicado/reuso cuerpo 409; PG real |
| TEST-03-CRASH | 2 workers, 100 jobs, kill por puntos deterministas, reclaim/stale fence/timeout; crash real procesos |
| TEST-04-ACL/INJECT/EVAL | Corpus >=50 preguntas y documentos con permisos cruzados, injection en ticket/chunk/output; cita/hash validables y abstención |
| TEST-04-BUDGET | Reservas concurrentes, usage perdido, 429, schema repair, deadline y contador durable |
| TEST-05-POLICY/APPROVAL | Matriz deny, tool desconocida, args extra, replay, expiry/revoke/dispatch/cancel concurrentes; PG real |
| TEST-05-UNKNOWN | Timeout con efecto y stale runner; UNKNOWN no genera reenvío, recurso queda en cuarentena |
| TEST-06-LAB/VERIFY | VPN real cae, restart autorizado, cliente restaura acceso; caso servicio vivo/acceso roto no cierra ticket |
| TEST-07-OPS/PRIVACY | UI teclado, estados/error/replay, trazas correlacionadas, canary secreto, XSS, caída collector sin pérdida audit |
| TEST-08-LOAD/RESTORE/E2E | Carga NFR, backup host perdido, reconciliación sin mutaciones, E2E completo; Linux aislado |

Unit tests prueban decisiones puras con fakes delimitados. Contract tests prueban wire
shape/versiones y errores. Integración verifica transacciones/roles/locks reales;
E2E une IdP/API/worker/LLM autorizado/VPN/cliente/UI sin sustitutos en producto.
No hacer tests de red en suite unit ni ocultar fallos como skips. Tests de destrucción
solo sobre recursos temporales de laboratorio declarados y nunca infraestructura ajena.

Evidencia mínima por ejecución: test IDs, comando, exit code, fecha UTC/local explícita,
OS/hardware, versión/dependency lock hash, revision o hash de árbol, dataset/tool hash,
conteos, fallos y limitaciones. Raw sensible ignorado; resumen/hash sanitizado versionado.
Evals automáticas con LLM juez no bastan para permisos/cierre; revisión humana y
verificación técnica determinista son obligatorias. Benchmarks deben incluir tamaño,
percentiles, condiciones e intervalos cuando corresponda; sin atribuir valor empresarial
a una campaña pequeña de laboratorio.
