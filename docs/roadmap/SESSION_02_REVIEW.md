# Sesión 02 — revisión de ingeniería y evidencias

Fecha de sesión: 2026-10-23, Europe/Madrid. Evidencias con timestamps UTC (la noche
del 22 UTC corresponde al 23 en Madrid). Estado de cierre: **NO-GO para S03**.
Implementación funcional probada; gate obligatorio de imágenes falla por un CVE
crítico y uno alto en la imagen oficial de Keycloak. No se acepta ninguna excepción.
Al cerrar la implementación, antes de la petición de publicación, no se había
realizado push, merge, release, despliegue ni commit en el repositorio.

El autor autorizó después el commit y push de S02 con «pushealo». Esta publicación
no cambia el NO-GO, no inicia S03 ni autoriza release o despliegue. Los resultados
CI NOT_RUN de los artefactos son el snapshot local anterior al push; consultar
GitHub Actions para las ejecuciones posteriores y Git para el commit publicado.

## 1. Estado inicial y alcance

Ruta original de la petición inexistente: se detuvo sin escribir. El autor indicó
`C:/Users/manul/OneDrive/Escritorio/opspilot-ai`; rev-parse confirmó esa raíz, HEAD
43e1d28 y árbol limpio. No se inspeccionaron ni modificaron proyectos vecinos.
Se leyeron AGENTS, handoff, specs/ADR/contratos y documentos canónicos antes de código.
Baseline S01: check PASS y 23 tests PASS. Windows 11, Python 3.13.14, uv 0.11.13,
Docker Engine 29.1.2 y Compose 2.40.3 sobre WSL2. Daemon ya disponible; no se reparó
ni reinició Docker. Había 64 contenedores ajenos en ejecución. Solo se operó sobre
recursos con prefijo opspilot-s02 y bases efímeras creadas por nuestras pruebas.

La spec canónica excluye tickets/workflows y reserva su implementación a S03.
Se respetó ese alcance frente a ejemplos más amplios de la petición: cuatro GET,
identidad, permisos, migración y auditoría reales. No LLM/RAG/tools/VPN/frontend.
Requisitos REQ-PLAT-01/02 y harness REQ-HAR-01. Decisiones previas y correcciones:
[ADR-0006](../decisions/0006-platform-boundaries.md) y
[plan de ejecución](../../specs/002-platform/execution.md).

## 2. Problemas y correcciones

| Hallazgo observado | Acción y verificación |
|---|---|
| Puerto 55432 ocupado | Lab usa 59432/59080/59000, exclusivamente loopback |
| Red internal de Engine 29 no publicó PG; alias perdido al recrear red | Bridge dedicado y recreación solo de contenedores propios; DNS/PG/IdP reales pasan |
| SQLAlchemy interpretó %ROWTYPE como placeholder | no_parameters en ejecución SQL de migración; transacción fallida revertida |
| Transferir función requería CREATE en schema al nuevo owner | Grant temporal dentro de migración y revoke inmediato; test verifica permiso final ausente |
| Cookie Secure en login HTTP loopback | Adaptación exclusivamente en agente HTTP de test; PKCE real, wrong verifier rechazado |
| Imagen tests quiso resincronizar venv como UID sin root | Sync congelado durante build; ejecución directa del intérprete instalado |
| Scanner historial omitía raíz/archivos eliminados | chdir acotado y filtro de existencia deshabilitado solo para diff histórico; fixture con secreto eliminado detectado |
| Timeout health reutilizado para appends bajo cobertura/carga | Escrituras 5 s; API/health conservan 1 s; mismos 20 appends y rollback de lock timeout pasan |
| Windows heredaba Modify para Usuarios en artifacts/local | init protege ACL a propietario/SYSTEM/Administrators sin elevación; archivos verificados, private-acl.json y recovery tras el ajuste |
| gosu upstream PG contiene Go vulnerable | Derivada sin gosu, USER postgres, initdb fresco UID 70 y scan final PASS |
| Base Python con OpenSSL/libuuid vulnerables | Paquetes corregidos fijados; rebuild y rescan final PASS sin altos/críticos |
| Primer análisis Keycloak agotó timeout sin informe | BLOCKED conservado; reintento local completado: detectó 1 crítico y 1 alto, gate FAIL |

Fallos no se convirtieron en skips. Se conservan XML de primeras ejecuciones,
fallo de timeout y resúmenes de CVE iniciales. Raw de scanner/logs bajo artifacts/local,
ignorados; resúmenes con hash bajo artifacts/session-02. No se publican credenciales.

## 3. Componentes, API y persistencia

Monolito modular con shared, identity/domain+application, audit/domain+application,
adapters/postgres+oidc, entrypoints/api y CLI de provisión. Puertos Protocol y DTO
inmutables/estrictos; domain/application no importan HTTP, FastAPI ni SQLAlchemy.
AST fitness tests comprueban imports absolutos/relativos, ciclos y acceso a infra,
incluyendo fixtures inválidas. Composition root crea y cierra pool/cliente/cache.

| Endpoint | Resultado y control |
|---|---|
| GET /health/live | 200 sin DB/IdP; no depende de IA |
| GET /health/ready | SELECT 1, revisión Alembic exacta y JWKS vigente; 503 redacted |
| GET /v1/me | JWT válido y sujeto local activo; UUID/roles locales; 401/403/503 |
| GET /v1/audit-events | auditor/admin; stream UUID, after_seq>=0, limit 1..100; orden seq ascendente; errores 401/403/422/503 |

Error cerrado `{code,request_id}`, WWW-Authenticate en 401, request ID de servidor,
traceparent validado, body real <=16 KiB, deadline HTTP 10 s, no CORS comodín.
Contrato OpenAPI independiente validado con librería estándar y respuestas HTTP;
schema OpenAPI generado por FastAPI también validado y contrastado por rutas,
operationId, códigos y seguridad. JSON Schema prueba envelopes válidos/negativos.

Alembic 0001_platform crea solo principals, role_grants, audit_streams y audit_events
(además de alembic_version). UUID, UTC timestamptz, FK, UNIQUE y CHECK reales.
Sin create_all, SQLite ni migración automática de API. Guard de migración limita
rol/host/base de lab; downgrade destructivo rechazado. PG18 vacío migra a head y
alembic check no encuentra drift. Rol app sin DDL, UPDATE/DELETE/TRUNCATE audit,
edición de head/grants ni SET ROLE del propietario. Provisión tiene login separado.

Appender SECURITY DEFINER, dueño NOLOGIN/search_path fijo, genera UUID/UTC/seq/hash
en DB y valida payload antes de persistirlo. Head con UPSERT + FOR UPDATE serializa
appends. Canonicalizador recursivo SQL y Python coinciden en Unicode, escapes,
arrays, null/bool/enteros; rechazan decimales, exponentes y claves duplicadas en SQL.
Evento+principal/grant se confirman en el mismo UoW; error de FK/appender/lock revierte
todo. Pruebas de 20 appends y 10 altas duplicadas concurrentes, integridad y tampering
por rol privilegiado. Hash chain detecta modificaciones; no es WORM ni resiste a un
administrador que reescriba toda la cadena y heads. Ancla externa pertenece a S08.

## 4. Identidad y autorización

Keycloak 26.8.1 real, realm/cliente versionados sin contraseñas. Access tokens de
Authorization Code + PKCE S256, password/implicit desactivados para producto. Se
prueban login real, rechazo de verifier incorrecto y rechazo de password grant.
PyJWT valida RS256, firma RSA >=2048, iss/aud exactos, exp/iat obligatorios, nbf si
está presente, sub válido y typ=Bearer; vida <=300 s y skew <=30 s. ID tokens,
alg none/HS256, firmas/claims incorrectos y tokens incompletos se rechazan.

JWKS solo desde URL preconfigurada, sin redirects ni jku/x5u del token; tamaño/key
count acotados, caché 300 s, lock y refresh una vez/30 s. Token conocido con caché
vigente funciona sin red; caducada sin red falla cerrado. Rotación, kid malicioso,
claves privadas/débiles/duplicadas y documentos excesivos tienen negativos.
Roles en claims no conceden autoridad. Consulta de identidad+grants en una sentencia
por petición; revocar/deshabilitar en PG afecta al siguiente uso del mismo token.

Operator/approver no leen audit. Auditor y admin sí, por permiso explícito.
No hay herencia admin→operator/approver ni asignación JIT. Sujeto no provisionado
o deshabilitado recibe 403. El token IdP revocado puede vivir hasta exp; deny local
inmediato y ventana IdP documentada. No se construyó autenticación propia ni bypass.

## 5. Pruebas, gates y evidencia

Ejecución más reciente completa: **170 PASS**, cero skips, tanto en Windows como Linux;
95 % de cobertura combinada (líneas+ramas) en Windows sobre todos los paquetes backend.
Los mismos escenarios se replican por plataforma; no son 340 escenarios diferentes.
El gate final ejecuta comandos congelados y deja su veredicto en verification.json.

| Gate | Evidencia disponible / estado |
|---|---|
| Baseline documental/harness S01 | PASS, 23 tests preservados |
| Unit/contract/architecture + PG/IdP Windows | tests-windows.xml; coverage-windows.json; 170 PASS |
| Suite Linux completa | tests-linux.xml: 170 PASS sobre fuente readonly y venv Alpine; integration-linux.xml conserva run separado 50 PASS |
| PG migración, atomicidad, permisos y concurrencia | tests/integration/test_audit.py y fixture Alembic check reales |
| Keycloak real/negativos | test_identity, test_idp_security, PKCE con cuentas sintéticas |
| Reinicio real | recovery.json PASS: 8 eventos, mismos heads/hashes; nuevo PKCE tras restart |
| Inicialización PG sin root | fresh-postgres.json PASS: volumen nuevo, UID 70, servidor 18.6 |
| Ruff/types/Markdown/AST | PASS; comandos/exit codes en verification.json |
| Bandit/pip-audit | PASS sobre lock final; paquete propio no publicado carece de ficha PyPI, terceros sin CVE detectado |
| Secret scan árbol+historial | PASS; checksums documentales revisados, sin secretos sin revisar |
| Imágenes | PG endurecido y API PASS; Keycloak FAIL por 1 crítico y 1 alto |
| CI | YAML implementado, acciones SHA, integración Linux local; GitHub Actions remoto NO EJECUTADO |

El runner contrasta el config digest del archivo escaneado y la identidad Docker
actual, distinguiendo config de índice OCI en Engine 29; un informe viejo de otra
imagen o un scanner caído no produce PASS. Negativos de ese gate incluidos en unit.
Secret scanner conserva hallazgos y solo reconoce como públicos SHA/revisión de Git,
hostname de contenedor en JUnit y fixtures sintéticos señalados, sin excluir XML/JSON
completos ni credenciales por extensión. Cobertura es una métrica,
no una prueba de todas las ramas posibles. No benchmark de producción, RTO/RPO, HA,
VPN, acciones IT, crash suite durable ni restore de backup. [Runbook](../engineering/PLATFORM_RUNBOOK.md).

## 6. Suministro, revisión final y riesgos

Dependencias runtime/dev separadas, pyproject + uv.lock con hashes y Python pin.
Imágenes upstream por digest, paquetes correctivos Alpine por versión exacta,
API sin root/read-only/capabilities, redes y volúmenes propios, salud y recursos
acotados. Credenciales aleatorias en archivos ignorados y mounts mínimos; API sin
credencial de migrador/admin. No secretos de producción ni claves/token en logs.

Revisión de seguridad/capas/transacciones/contratos realizada por el mismo asistente
en un pase separado, más scanners y tests negativos. No es auditoría independiente
de un tercero. El autor debe revisar el diff y aceptar riesgos antes de validar un
piloto. Quedan revisión corporativa de IdP/provisión/personas, proxy TLS/rate limits,
retención/backup/ancla externa y S03 crash/fencing. Warning de deprecación dev de
Starlette TestClient con HTTPX: funciona, sin bypass; evaluar migración dev antes de
retirar esa compatibilidad. No se cambia silenciosamente el transporte de producto.

Bloqueo concreto: Keycloak 26.8.1/digest fijado incluye CVE-2026-114406 en
ca-certificates y CVE-2026-91415 en java-21-openjdk-headless. Trivy informa affected
sin FixedVersion. El [aviso del proveedor](https://access.redhat.com/solutions/7149312)
explica que la actualización de CA está en preparación y ofrece mitigación manual.
No se ha validado una imagen reparada compatible; el tag Keycloak 26.8.2 consultado
no existe. No se alteró a mano el trust store ni se sustituyó silenciosamente el JVM
para ocultar el hallazgo. Corregir mediante imagen/paquetes mantenidos o una derivada
revisada, fijar nuevos hashes y repetir scan+PKCE/RBAC/recovery antes de GO.
Autor responsable de R15; sin fecha ficticia para el arreglo del proveedor.

Archivos creados/modificados y hashes constan en manifest.json. Entorno/versiones y
licencias declaradas por los paquetes en environment.json, sin certificación legal.
Cambios S01 acotados: activar comandos/gates, retirar guard src/infra autorizado,
formato Ruff y mantener 23 negativos (el comando futuro probado pasa de infra a eval).
El cierre de implementación se verificó sin commits/push; la publicación posterior
está autorizada arriba. El scanner de historial usa repos temporales de test con
commits sintéticos; el scanner no modifica el historial del producto.

Laboratorio detenido al cierre; volumen PG conservado, sin operar recursos ajenos.
API y PG salieron con código 0; Keycloak con 137 tras el timeout de Compose stop.
No se presenta ese último cierre como apagado limpio del IdP. La prueba de recovery
con nuevo PKCE corresponde al reinicio anterior, registrado en recovery.json.
Estado final de los tres servicios y volumen en shutdown.json.

## LO QUE DEBE COMPRENDER EL ARQUITECTO

**Autenticación.** Keycloak firma el access token. `OidcVerifier.verify` obtiene una
clave del JWKS configurado y llama a `jwt.decode` con RS256/issuer/audience y tiempos.
Devuelve únicamente ExternalIdentity(issuer,subject): ningún rol del token pasa al
dominio como autoridad. `authenticate` busca el principal local activo; sin mapeo,
403. No existe endpoint que acepte un nombre de usuario como prueba de identidad.
Código: [verifier](../../src/opspilot/adapters/oidc/verifier.py) y
[caso de uso](../../src/opspilot/identity/application/authenticate.py).

**Permisos.** `PostgresPrincipals.find` consulta principal y grants activos en una
sentencia. `Principal.require_audit_read()` exige auditor o admin. Un operador con
JWT válido recibe 403 al leer audit. Grants revocados ya no aparecen en esa lectura.
Admin no obtiene automáticamente permiso de operar o aprobar acciones futuras.
Código: [permisos](../../src/opspilot/identity/domain/principal.py) y
[repositorio](../../src/opspilot/adapters/postgres/identity.py).

**Transacción.** Código real de la provisión, simplificado solo en nombres:

```python
with PostgresUow(sessionmaker(engine)) as uow:
    writer = IdentityWriter(uow.session)
    audit = PostgresAppender(uow.session)
    principal_id = create_identity(writer, audit, issuer, subject, trace_id)
    uow.commit()
```

Los dos adapters reciben la misma Session. `create_identity` inserta el principal
y llama al appender; commit ocurre después de ambos. Si audit falla, `__exit__` hace
rollback y cierra la sesión. SQL calcula seq/hash bajo lock dentro de esa transacción.
El CLI solo imprime éxito después del commit. Tests provocan errores reales de PG.
Código: [UoW](../../src/opspilot/adapters/postgres/database.py),
[provisión](../../src/opspilot/identity/application/provision.py) y
[funciones SQL](../../migrations/sql/0001_platform.sql).

**Persistencia.** S02 demuestra principal+evento persistentes, no tickets. El test
de restart compara 8 eventos y los mismos hashes tras parar/arrancar PG/Keycloak/API;
un login nuevo recupera la misma identidad. Tickets, workflow inicial, job y respuesta
idempotente deberán entrar en una transacción equivalente en S03, con tests propios.
No se afirma que persistan hoy porque aún no existen.

**Monolito.** Identity/audit contienen reglas y puertos; adapters implementan PG/OIDC;
entrypoints compone y traduce HTTP. DTO, entidades y ORM son clases separadas.
Architecture tests rompen ante domain→ORM/HTTP, imports relativos prohibidos o ciclos.

**Tests.** `python scripts/dev.py test` ejecuta todo y requiere servicios reales;
`--suite local` anuncia que excluye integración. Cada run PG migra una DB efímera.
`check` ejecuta calidad y scans; `verify_recovery` interrumpe solo el lab propio.
No se sustituye PG por SQLite ni IdP por un token firmado localmente en integración.

**Preparación durable.** UoW, appender, grants frescos y migraciones ofrecen la frontera
de persistencia para S03. Aún no hay worker, leases, fencing, jobs ni transiciones.
Antes de implementarlos, definir OpenAPI de intake, extender migraciones/contratos
audit y superar suite de crashes y carreras según ADR-0002. Nada avanza automáticamente.
