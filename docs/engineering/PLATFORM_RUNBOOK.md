# Runbook de plataforma S02

## Hotfix PostgreSQL / Brotli S03

[Revisión y resultados actuales](../roadmap/SESSION_03_POSTGRES_SECURITY_REVIEW.md).
La base PostgreSQL 18.6/Alpine 3.24.3 por digest conserva su configuración y UID 70;
infra/postgres.Dockerfile instala brotli-libs=1.2.1-r0 firmado desde v3.24/main,
antes de USER postgres. No mezclar ramas ni eliminar la dependencia de libcurl.
Si Alpine retira esa revisión, el build falla: revisar versión mantenida, fijarla
y repetir los gates; no quitar el pin ni el scan como reparación automática.

Para revalidar, construir PG, API y tests; guardar inventario/digests; ejecutar las
suites Windows/Linux secuencialmente, PG fresco, recovery y los tres scans en un
directorio nuevo. Contrastar inspect/config/Trivy de la imagen final y hashes de
datos antes/después. No reutilizar informes de otra imagen o snapshot histórico.

Tras recrear el contenedor PostgreSQL, Keycloak puede mantener conexiones JDBC
cerradas y devolver 500 en PKCE aun con health verde. Reiniciar Keycloak y API del
lab propio, esperar health y comprobar login PKCE real antes de aceptar regresión.
No reprovisionar identidades ni reconstruir el volumen para corregir ese estado.
Mantener pg_data, credenciales y evidencias; no usar down -v ni eliminar volúmenes.
Recovery por restart no sustituye la restauración de backups exigida en S08.

## Actualización S03 — persistencia T03-02

El autor aprobó cierre/riesgos S02 y T03-01/ADR-0008 antes de código. Migración 0002
implementada y aplicada al lab: conserva filas/hashes/función S02; añade seis tablas,
snapshot privado y appender v2. [Revisión T03-02](../roadmap/SESSION_03_PERSISTENCE_REVIEW.md).
Sin intake, worker ejecutable ni aceptación de durabilidad. S04/producción NO-GO.

`init` añade pg_worker y worker.dsn/worker-internal.dsn privados sin rotar archivos
existentes. `bootstrap` crea login dedicado sin DDL/herencia/bypass y CONNECT solo
lab; retira CONNECT/TEMP de PUBLIC también en postgres/template1 del cluster propio.
`migrate` concede permisos por columna; API no monta DSN worker ni migrador. No
usar bootstrap en un cluster compartido o ajeno: sigue limitado al Compose sintético.
Tests crean bases efímeras propias e incluyen N-1, fallo de migración, FK/checks y
negativos de permisos. Incidents continúa OPEN, independiente de cualquier job.

Después de migrar, una API de imagen S02 antigua falla readiness por versión exacta.
Usar `python scripts/dev.py up`, que construye el código actual; no reparar el gate
relajando schema ni arrancando una imagen antigua a mano. T03-02 no afirma build/
scans/CI actuales aprobados por los resultados históricos S02. Al terminar se para
solo el lab propio conservando volumen/credenciales. Historial S02 a continuación.

Remediación actual: [informe](../roadmap/SESSION_02_SECURITY_REMEDIATION.md) y
ADR-0007. Keycloak se construye localmente con Alpine/Temurin mantenidos, inputs
por digest/SHA-256 y paquetes directos fijados; solo linux/amd64. No editar CA/JVM
a mano. `infra` reconstruye el IdP; repetir suites completas, recovery y scan al
cambiar su receta. Imagen oficial UBI anterior conservada solo como evidencia.
Los tags de builds locales se contrastan con los digests/config del manifest de
remediation; no equivalen a imágenes publicadas. La aceptación S03 requiere CI
remota satisfactoria de la revisión corregida, además de los gates locales.

Solo laboratorio single-tenant con datos sintéticos. Repositorio autorizado:
`C:/Users/manul/OneDrive/Escritorio/opspilot-ai`. No usar proyectos vecinos. No hay
deploy, push ni commits automáticos. El estado del gate vive en SESSION_02_REVIEW.

## Arranque reproducible

Python 3.13.14 y uv 0.11.13, Docker Desktop/WSL2 o Docker Linux, Compose v2.
Confirmar que 59432, 59080 y 59000 están libres antes del primer arranque.
El proyecto/volumen/red se llaman `opspilot-s02*`; no operar sobre otros proyectos.

```text
git rev-parse --show-toplevel
python scripts/dev.py doctor
python scripts/dev.py install
python scripts/dev.py infra
python scripts/dev.py up
python scripts/dev.py test
python scripts/dev.py check
```

`infra`: genera secretos → PG endurecido → roles/DB de lab → Alembic → Keycloak →
cuentas sintéticas y grants explícitos. Es repetible: no rota contraseñas existentes,
no repite eventos al reprovisionar y no asigna roles por petición HTTP. Si una etapa
falla, el harness se detiene. API no ejecuta DDL/migraciones por sí misma.

La API queda en `http://127.0.0.1:59000`; IdP en `http://127.0.0.1:59080`; PG loopback
59432. Todas las imágenes upstream están fijadas por digest; imágenes propias tienen
tag explicativo y lock. El usuario runtime es 10001, PG 70 y Keycloak 1000.
No hay Docker socket, privilegios globales ni acceso a VPN en los contenedores.

## Credenciales y configuración

`artifacts/local` está ignorado. `init` crea contraseñas aleatorias, DSN por rol y
`accounts.json` con usuarios sintéticos; no imprimir ni publicar su contenido.
En Linux, directorio 0700, archivos privados 0600; solo fuentes de secretos montados
son 0444 dentro de ese directorio protegido, para que los UID de servicio puedan
leer su bind mount. En Windows `init` elimina herencia amplia y establece ACL de
propietario, SYSTEM y Administrators en artifacts/local; verifica también los
archivos existentes y falla cerrado si queda otro acceso Allow. No solicita
elevación ni cambia permisos de otras carpetas. Requiere PowerShell estándar o pwsh;
importa su módulo de seguridad nativo sin cambiar la política de ejecución.
La API recibe exclusivamente `app-internal.dsn`; no recibe credencial migrador/admin.
No copiar `.env.example` como si contuviese credenciales. Pydantic lee variables de
entorno; `.env` no se carga implícitamente. Referencia: `.env.example` en raíz.

Variables obligatorias: OPSPILOT_ENVIRONMENT (lab/production),
OPSPILOT_DATABASE_DSN_FILE, OPSPILOT_OIDC_ISSUER, OPSPILOT_OIDC_AUDIENCE,
OPSPILOT_OIDC_JWKS_URL. Opcionales: OPSPILOT_JWKS_TTL_SECONDS (1..300),
OPSPILOT_JWKS_REFRESH_SECONDS (30..300), OPSPILOT_HTTP_TIMEOUT_SECONDS (>0..3),
OPSPILOT_DB_TIMEOUT_MS (100..1000 para API). Provisión/UoW usa 5 s; health/API 1 s
por statement, connect timeout 2 s, deadline HTTP 10 s incluyendo body <=16 KiB.
Producción exige OIDC HTTPS y DSN sslmode=verify-full; además requiere proxy TLS,
rate limits, gestor de secretos y gates S08. La opción production no provisiona eso.

Rotación de lab: detener servicios propios, planificar actualización de credenciales
en PG/Keycloak y archivos asociados juntos. `init` no cambia claves de bases ya
existentes. No borrar volúmenes para resolver un fallo de autenticación.

## Identidad y permisos

Cliente `opspilot-lab-pkce`: Authorization Code + PKCE S256, redirect exacto a
`http://127.0.0.1:59081/callback`. Password/implicit/service accounts desactivados.
Tests completan el login real por HTTP, sin un bypass de usuario/token. El driver
de test reproduce la excepción de cookies Secure en loopback que aplica el navegador;
esa adaptación vive únicamente en tests. No hay endpoint de login del backend.
El password grant usado por el script de bootstrap es exclusivamente admin-cli
local de Keycloak, nunca el cliente de producto ni un login alternativo de API.

Roles locales: operator, approver, auditor, admin. `me` requiere principal activo;
audit requiere auditor o admin. Admin no hereda operator/approver. Issuer/sub deben
estar provisionados y habilitados en PG. Claims de roles del IdP no otorgan permisos.
Revocación local se consulta en cada petición; revocación IdP puede tardar hasta exp
(máximo 300 s, más skew 30 s). JWKS TTL 300 s, refresh desconocido como máximo cada
30 s, sin redirects/proxy implícito ni jku/x5u del token. Error necesario de IdP/DB
es 503; token inválido 401; principal/permiso denegado 403; input inválido 422.

Provisión explícita (nunca endpoint admin):

```text
uv run python -m opspilot.entrypoints.provision create --dsn-file artifacts/local/provisioner.dsn --issuer https://idp.example/realm --subject external-subject
uv run python -m opspilot.entrypoints.provision grant --dsn-file artifacts/local/provisioner.dsn --principal-id PRINCIPAL_UUID --role auditor
uv run python -m opspilot.entrypoints.provision revoke --dsn-file artifacts/local/provisioner.dsn --principal-id PRINCIPAL_UUID --role auditor
uv run python -m opspilot.entrypoints.provision disable --dsn-file artifacts/local/provisioner.dsn --principal-id PRINCIPAL_UUID
```

En S02 un mantenedor local es actor de sistema (actor_id null); reason/aggregate/
trace/UTC identifican la operación. No se afirma trazabilidad a una persona física
sin provisión corporativa gobernada. Grants y cambios de identidad tienen audit
durable atómico; denegaciones HTTP se registran en logs estructurados, no se anuncian
como un ledger durable de todos los intentos de acceso.

## Migraciones y recuperación

```text
python scripts/dev.py migrate
uv run alembic check
uv run python scripts/verify_fresh_postgres.py
uv run python scripts/verify_recovery.py
```

Para `alembic check` directo establecer OPSPILOT_MIGRATION_DSN_FILE a
`artifacts/local/migration.dsn`; el wrapper migrate ya lo hace para upgrade.
El migrador rechaza roles/hosts/DB ajenos al lab y no admite downgrade destructivo.
Futura migración empresarial exige ampliar este guard por una decisión explícita.
Revisar migraciones nuevas antes de ejecutarlas; guardar principal/eventos en el
mismo UoW. Un appender fallido revierte ambos, incluso si ya se bloqueó/creó head.

`verify_fresh_postgres` crea un contenedor sin red y volumen anónimo nuevo; prueba
initdb como UID 70 y elimina solo ese recurso efímero mediante Docker --rm.
`verify_recovery` detiene PG propio, comprueba live=200/ready=503/me=503, arranca PG,
reinicia Keycloak/API y verifica los mismos hashes y un nuevo PKCE. Interrumpe
temporalmente el laboratorio. No es backup/restore ni crash suite de workflows.

## Suites y gates

```text
python scripts/dev.py test --suite local
python scripts/dev.py test --suite integration
python scripts/dev.py test
uv run python scripts/scan_images.py
```

Local incluye harness, dominio, JWT/JWKS, configuración, contratos y arquitectura;
all añade PostgreSQL y Keycloak reales. No hay SQLite ni skips de integración. Cada
run de integración migra una DB opspilot_test_UUID vacía y elimina solo esa DB al
terminar; roles/servidor son reales. Tests concurrentes conservan 20 appends, checks
de rollback y 10 creaciones concurrentes del mismo principal.
Para ejecutar la suite en contenedor: `docker compose -f infra/compose.yaml run --rm
--no-deps tests`. En Linux exportar OPSPILOT_TEST_UID/GID con el uid/gid del dueño de
los archivos antes de usar el bind mount privado. No compartir venv Windows/WSL.

`check` conserva el harness documental y ejecuta frozen lock, Ruff, PyMarkdown,
mypy estricto, AST architecture, Bandit, detect-secrets y pip-audit. PyMarkdown usa
reglas Markdownlint; MD013 (ancho arbitrario 80) y MD060 (alineación estética de
tablas) se excluyen por el formato compacto canónico. Enlaces/JSON/fences se siguen
validando con el checker. Secret scanning es heurístico, incluye historial y
archivos eliminados; excepciones solo hashes documentales y fixtures sintéticos
identificados. No prueba ausencia absoluta de secretos.

Trivy fijado por digest analiza imágenes finales sin Docker socket; solo monta
archivos de imagen públicos/de aplicación y caché, nunca credenciales. Raw/SBOM se
guardan ignorados; resumen, CVE y hash raw se versionan. No omitir altos/críticos.
Actions S02 se ejecutó y falló en PG fresco; los pasos recovery/scan se omitieron.
El diagnóstico/ajuste local y resultados nuevos están en el informe de remediación.
Ejecutar comandos localmente no equivale a CI remota satisfactoria del nuevo árbol.
`eval` sigue devolviendo NOT_IMPLEMENTED, código 2.

## Parada, logs y fallos

```text
python scripts/dev.py logs
python scripts/dev.py stop
docker compose -f infra/compose.yaml ps -a
```

`stop` conserva volumen y contraseñas. No ejecutar prune ni down -v sobre servicios
ajenos. Logs de API contienen request_id, trace_id, actor, ruta de contrato, UTC,
resultado y duración, sin query/body/Authorization. No usar logs verbose HTTP con
credenciales reales. Readiness 503 no debe repararse saltando OIDC o migraciones:
comprobar primero servicios propios, revisión Alembic, JWKS configurado y permisos.

## Intake local T03-03

POST /v1/incidents requiere access token validado y grant operator local activo,
Content-Type application/json y un Idempotency-Key UUID con guiones. Body cerrado:
`{"title":"Prueba sintética","description":"Intake local"}`. Nunca usar datos reales
antes de cerrar privacidad. 202 devuelve incident_id/workflow_id después de commit.
Misma key/body recupera esos IDs; otro body devuelve 409. Revocar operator o
deshabilitar principal impide también el replay. Admin no hereda operator.

Ante 503 o pérdida de conexión, repetir con la misma key/body después de recuperar
dependencias. No fabricar una key nueva para resolver incertidumbre de commit.
Los registros se conservan sin limpieza automática. El job READY queda almacenado;
no hay worker/polling ni diagnóstico/resolución. No iniciar T03-04 automáticamente.

La suite completa añade carreras de 20 requests, dos procesos API y kills reales
antes/después de commit. El test-only helper intake_process.py contiene pausas de
sincronización, nunca switches de fallo en src. verify_recovery.py comprueba también
503 del POST durante caída real de PostgreSQL. El smoke T03-03 deja una incidencia
sintética en el volumen del lab y comprueba replay exacto después del reinicio.
[Revisión/evidencias](../roadmap/SESSION_03_INTAKE_REVIEW.md), sin modificar snapshots S02/T03-02.

## Lecturas y cancelación local T03-04

GET /v1/incidents/{incident_id} y GET /v1/workflows/{workflow_id}: operator creador
o auditor local explícito. Sin body/query, no existe conditional GET. Workflow
devuelve ETag fuerte con UUID lowercase y versión. Admin/approver no heredan acceso.
Cancel requiere operator creador y POST /v1/workflows/{workflow_id}/cancel sin body,
con If-Match exactamente igual al tag leído. 202 solo tras commit; devuelve el ETag
nuevo. La incidencia permanece OPEN; no implica revertir efectos ni resolver VPN.

Ante 409 VERSION_CONFLICT o transporte perdido, releer GET workflow autorizado.
Si CANCELLED, repetir con ETag actual da 202 sin cambios; viejo sigue 409. Ante 503
no asumir éxito ni fracaso del commit. SUCCEEDED/FAILED actuales devuelven 409
TERMINAL_WORKFLOW. Ambiguos solo registran intención; no activar reintentos.
Pruebas de T03-04 incluyen caducidad real de token con TTL temporal de un segundo
del cliente PKCE sintético, restaurado tras emisión; ejecutar suites de integración
secuencialmente para evitar interferir con ese cambio local del IdP.

Evidencias nuevas en artifacts/session-03/access-cancel; snapshots anteriores
intactos. Worker, leases/resultados tardíos y AC03-06 completo siguen T03-05/06.

## Scanner aislado y evidencia nueva

Consultar [spec](../../specs/002-platform/scanner-remediation.md). Linux exige UID y
GID efectivos distintos de cero; Trivy usa esos IDs. Staging temporal propio,
fuera del lab, directorios 0700 y tar 0600. Windows usa 10001:10001 y exige I/O real
en Docker Desktop; sus modos 0777 sintéticos no son chmod del host. Solo se montan
el tar como archivo readonly, salida exclusiva y caché exclusiva. Rootfs readonly,
cap_drop ALL, no-new-privileges y ausencia de socket/secretos se conservan.
TMPDIR usa cache/tmp para descargar DB sin agotar el tmpfs de /tmp. La caché es
compartida entre los tres scans de la invocación y se elimina al terminar.

Usar destinos nuevos para conservar snapshots:

```text
python scripts/verify_scanner_environment.py --report artifacts/session-02/NUEVO/scanner-environment.json
uv run python scripts/scan_images.py --evidence-dir artifacts/session-02/NUEVO/scans
uv run python scripts/verify_fresh_postgres.py --report artifacts/session-02/NUEVO/fresh-postgres.json
uv run python scripts/verify_recovery.py --report artifacts/session-02/NUEVO/recovery.json
uv run python scripts/verify_session02.py --manifest-only --evidence-dir artifacts/session-02/NUEVO
```

BLOCKED distingue PERMISSION_DENIED, CACHE_UNWRITABLE, INPUT_UNREADABLE,
SCANNER_RUNTIME_ERROR, SCAN_TIMEOUT, INVALID_REPORT e IMAGE_ID_MISMATCH.
VULNERABILITIES_FOUND es FAIL. Un deadline anfitrión conserva exit_code null si
no se observó la salida de Trivy; no inventa returncode 124. Los hashes identifican
logs y JSON brutos privados. Nunca publicar stdout/stderr completos sin revisión.

Docker clásico devuelve config ID; containerd puede devolver manifest/índice OCI.
Se verifica cada blob SHA-256 desde inspect hasta config linux/amd64, y su igualdad
con Metadata.ImageID de Trivy. Cualquier vínculo roto bloquea el gate.
