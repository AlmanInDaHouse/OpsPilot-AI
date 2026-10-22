# Sesión 02 — especificación ejecutable de plataforma

Estado: PROPUESTO, no implementar durante sesión 01. Feature `002-platform`.
Fuente normativa de contratos: [OpenAPI](../../contracts/platform.openapi.json),
[datos](../architecture/DATA_MODEL.md) y [seguridad](../architecture/API_CONTRACTS.md).
Plan y tareas: [plan](../../specs/002-platform/plan.md), [tasks](../../specs/002-platform/tasks.md),
[checklist](../../specs/002-platform/checklist.md). REQ-PLAT-01/02.

## Justificación, historia y precondiciones

Como operador autenticado quiero conocer mi identidad/roles; como auditor quiero
consultar eventos sin poder ejecutar operaciones. Base necesaria para que ningún
workflow futuro opere anónimamente o pierda decisiones al fallar un proceso.
Requiere S01 GO, revisión del autor, Python 3.13, uv/Git, Linux/Docker disponible
y puertos locales libres. Docker daemon aquí está apagado: no sustituir integración
por mocks. Resolver proveedor IdP para lab: recomendado Keycloak real con realm único.
No requiere proveedor LLM, VPN ni credenciales de producción.

## Alcance y exclusiones

Crear API health/live, health/ready, me y lectura audit. JWT/OIDC con permisos locales,
PG18, migraciones, appender y UoW. Provisión local explícita de usuarios/roles y
configuración IdP reproducible. No tickets, workflow engine, tools, RAG, frontend,
approval ni endpoints que aparenten esas funcionalidades. Sin frameworks DI/agents.

## Flujo principal

Migrador inicializa esquema con rol DDL; app usa rol restringido. Operador obtiene
access token real vía cliente de prueba del IdP (Authorization Code+PKCE; cuentas
de test preprovisionadas, no password grant en producto). API valida JWT y carga
principal/roles locales por petición. `/v1/me` devuelve DTO sin claims sensibles.
Auditor consulta stream de eventos paginado por seq. Provisión de principal+evento
es atómica y no asigna rol por defecto. Health no filtra detalles internos.

## Alternativas y fallos

Token faltante/inválido→401 con WWW-Authenticate; sujeto desconocido o deshabilitado→403;
operator sin auditor→403; query inválida→422; DB/JWKS requerido inaccesible→503 redacted.
Readiness falla si schema no exacto o caché JWKS no vigente. Liveness no toca DB.
JWKS desconocido refresca con rate limit; no seguir `jku` del token. Rol revocado en
DB se deniega en siguiente petición; revocación IdP limitada por exp <=5 min documentada.
Si appender falla, provisión hace rollback. API no hace migraciones al arrancar.

## Datos y paquetes exactos

S02 solo tablas `principals`, `role_grants`, `audit_events` y cabeza de stream para seq
atómica (`audit_streams`: stream_id PK, last_seq, last_hash); Alembic version table.
Head row lock evita seq duplicada; creación de stream concurrente por UPSERT. UPDATE
de head permitido solo a función appender; aplicación no altera eventos ni hace DDL.
Grants aprovisionados mediante script local con rol dedicado, no API admin expuesta.
Hash audit v1: JSON UTF-8 sort_keys=True, ensure_ascii=False, separators=(',',':'), sin
floats; timestamp RFC3339 UTC con seis dígitos y sufijo Z; IDs UUID lowercase canónicos.
Campos exactos: event_id,stream_id,seq,event_type,schema_version,occurred_at,actor_id,
trace_id,payload,prev_hash (64 ceros para inicio). `hash` no entra en su propia entrada.
Golden bytes y SQL/Python parity requeridos; appender verifica envelope y hash dentro
de transacción con dueño no-login/search_path fijo; no fiarse de hash cliente.
Canonicalizador SQL recursivo ordena claves por colación C, serializa arrays en orden
y permite solo enteros/cadenas/boolean/null/objetos/arrays del envelope. Rechaza floats
y timestamps no normalizados. Comparar bytes con Python incluyendo Unicode y escapes;
si no coincide, NO-GO T02-04 hasta corregir, sin cambiar frontera de confianza en silencio.

```text
src/opspilot/shared/                 IDs, errores, reloj, puertos UoW
src/opspilot/identity/domain/        Principal, Grant y permisos
src/opspilot/identity/application/   Authenticate/Authorize y repositorios puerto
src/opspilot/audit/domain/           Envelope y canonicalización
src/opspilot/audit/application/      Append/List y puertos
src/opspilot/adapters/postgres/      ORM, UoW, appender y repositorios
src/opspilot/adapters/oidc/          JWT verifier/JWKS cache
src/opspilot/entrypoints/api/        FastAPI composition root y rutas
migrations/                         Alembic + roles documentados
infra/                              Compose, configuración Keycloak sin secretos
tests/unit/ tests/integration/ tests/contract/ tests/architecture/
```

Core no importa FastAPI/ORM/HTTP. Shared no se convierte en cajón de servicios.
Config Pydantic settings valida issuer/audience/DSN/timeouts al arrancar. Credenciales
de test inyectadas desde archivos ignorados; `.env.example` solo nombres y valores no sensibles.

## Dependencias y estrategia de versiones

Runtime mínimo: FastAPI, uvicorn, Pydantic 2 + pydantic-settings, SQLAlchemy 2, psycopg 3,
Alembic, PyJWT con crypto (o equivalente verificado) y httpx para JWKS. No pgvector
hasta S04. Dev: pytest/pytest-cov, Ruff, mypy, JSON Schema/OpenAPI validators, pip-audit
y Bandit, import-linter o AST propio con tests negativos. Evaluar necesidad de cada extra.
Crear pyproject y uv.lock fijado con hashes, Python 3.13 patch elegido, imágenes PG18/
Keycloak fijadas por digest y etiquetas explicativas. Compatibilidad se demuestra
con integración, no con tabla de versiones. Documentar licencia/origen y CVE conocidos.

## Criterios de aceptación (Given/When/Then)

| AC / test | Condición verificable |
|---|---|
| AC02-01 / TEST-02-CONTRACT | Dado proceso vivo sin DB, live=200 y ready=503; con DB/schema/JWKS válidos ready=200; cuerpo exacto OpenAPI |
| AC02-02 / TEST-02-AUTH | Dado token real válido + principal activo, me=200 con UUID/roles; iss/aud/exp/nbf/iat/alg falsos y token ausente=401 |
| AC02-03 / TEST-02-AUTH | Claims admin sin grant local no elevan rol; operador no lee audit; rol revocado se niega inmediatamente; unknown principal=403 |
| AC02-04 / TEST-02-AUDIT | Provisión+audit commit juntos; fallo de appender no deja principal; 20 append concurrentes sin seq repetida/gaps confirmados |
| AC02-05 / TEST-02-AUDIT | Rol app no UPDATE/DELETE audit ni DDL; alteración controlada por rol de test privilegiado se detecta al verificar hash |
| AC02-06 / TEST-02-MIGRATE | PG18 vacío→head; Alembic check sin drift; app rechaza schema incorrecto; volúmenes temporales no afectan host ajeno |
| AC02-07 / TEST-02-ARCH | Fixture domain→ORM/HTTP y ciclo falla; código válido pasa; imports relativos incluidos |
| AC02-08 / TEST-02-SUPPLY | uv frozen reproducible, format/lint/types/scans y CI Linux integración reales ejecutados; ningún crítico omitido |
| AC02-09 / TEST-02-CONTRACT | Request inválida y fallo dependencia devuelven Error cerrado sin cuerpo/token/traceback; audit pagination determinista |
| AC02-10 / TEST-02-AUTH | JWKS cache válido permite token conocido sin red; cache expirado sin red falla cerrado; kid desconocido no provoca SSRF/refresh ilimitado |

## Comandos de verificación y DoD

Ahora solo `python scripts/dev.py doctor/check/test` funcionan. En S02 implementar y
documentar: `python scripts/dev.py install`, `infra`, `migrate`, `up`, `logs` y extender
`check/test` para ejecutar gates reales. Comandos subyacentes objetivo: `uv sync --frozen`,
`uv run ruff format --check .`, `uv run ruff check .`, `uv run mypy src`, `uv run pytest`,
`uv run alembic upgrade head`, `uv run alembic check`, `uv run pip-audit`, `uv run bandit -r src`,
`docker compose config --quiet`. No afirmar que existen hoy ni ejecutarlos prematuramente.
Tests integration requieren markers explícitos y servicio real; ausente implica fail
del gate de integración, no skip verde. Migración solo contra DSN lab validada.

DoD: AC02-01..10 y gates S02 pasan, lock/digests/config reproducibles, scan reports
revisados, OpenAPI de implementación coincide, sin secretos ni endpoints de negocio,
evidencia por tarea y handoff actualizado. Autor revisa riesgos; fallo auth/audit/
migración/concurrencia significa NO-GO S03. No hacer push ni despliegue automáticamente.

## Riesgos y mitigación

Docker apagado→habilitar entorno al iniciar S02 o CI Linux; no prometer integración hoy.
IdP/JWKS complejo→configuración reproducible y negativos reales. Hash de auditoría
multilenguaje→golden bytes y algoritmo explícito con NO-GO si difiere. No reducir
garantía ni sustituir la función privilegiada por un hash recibido del cliente.
Scope creep→rechazar intake/worker/UI en S02. Ocho sesiones son hitos; reestimar tras S03.
