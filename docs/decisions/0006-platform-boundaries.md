# ADR-0006 — cierre de contratos de plataforma S02

Estado: aceptado para implementación S02, 2026-10-23 (Europe/Madrid).
Requisitos REQ-PLAT-01/02; tareas T02-01..08. No cambia ADR-0001..0005.

La petición de ejecución incluye tickets como ejemplo, pero ordena respetar la spec
canónica. SESSION_02_SPEC y el roadmap reservan explícitamente intake/workflows a
S03. Se implementan únicamente los cuatro GET ya contratados. Roles exactos:
operator, approver, auditor, admin; admin solo permite lectura audit en S02.

La identidad requiere access token Keycloak `typ=Bearer`, RS256, issuer/audience
exactos, sub no vacío, tiempos enteros exp/iat/nbf (nbf opcional cuando IdP no lo
emite), vida máxima 300 segundos y skew 30 segundos. JWKS fijo configurado; nunca
URLs del token, redirects ni proxy implícito. TTL 300 s, refresh como máximo cada
30 s, lock entre threads. Revocación local consultada por petición. nbf presente
se verifica; exigir nbf ausente en Keycloak impediría interoperabilidad real.

Provisión local con login PG dedicado: create/grant/revoke/disable dentro de UoW,
evento en el mismo commit, sin asignación de roles implícita. Duplicado no produce
otro evento; bloqueo de principal serializa cambios concurrentes. No API admin.
Credenciales aleatorias solo en artifacts/local (ignorado), nunca en argumentos,
logs o archivos versionados. Entorno production exige HTTPS y DSN TLS verify-full.

Appender SECURITY DEFINER, dueño NOLOGIN, search_path pg_catalog,public fijo. El
servidor asigna UUID, timestamp UTC normalizado, seq y hash; el cliente no propone
hash. Payload S02 cerrado a reason_code/aggregate_id/aggregate_version/evidence_ids;
roles expresados mediante reason_code enumerado. Envelope público conserva el schema
existente: hash/prev_hash se almacenan y verifican internamente, sin ampliar la API.
Función SQL canónica usa JSON textual para rechazar exponentes/decimales antes de
JSONB. Python rechaza floats, NUL y surrogates; PG no admite estos últimos. SQL
rechaza claves duplicadas. Digest SHA-256 nativo PG18, sin extensión pgcrypto.
La cadena detecta cambios, no garantiza inmutabilidad ante administrador DB.

Roles PG: migrador/owner DDL, audit_owner NOLOGIN solo eventos/head, provisioner
escribe identidad/grants y ejecuta append; app solo SELECT identidad/grants/audit,
lectura de Alembic y EXECUTE append para futuros UoW. Sin CREATE en public ni
UPDATE/DELETE audit para app/provisioner. El administrador de lab inicializa roles
y contraseñas por un bootstrap separado, nunca al arrancar API.

Lab Compose exclusivo, nombres opspilot-s02, PG18 y Keycloak persistentes en PG,
puertos solo loopback y recursos acotados. HTTP IdP permitido únicamente en lab.
La red data es bridge dedicada: en Docker Engine 29 la red internal impidió publicar
el puerto de PG al host aun con binding loopback. Se conserva aislamiento por red
y exposición exclusiva a 127.0.0.1; no se declara un firewall de egress empresarial.
Cliente de integración PKCE S256 con agente HTTP que completa el login real en tests; flujo
password/implicit deshabilitado. Sin credenciales de producción ni herramientas IT.

Pruebas: TEST-02-AUTH/AUDIT/MIGRATE/ARCH/CONTRACT/SUPPLY, incluyendo paridad bytes
SQL/Python, 20 appends concurrentes, roles reales, revocación y PKCE con Keycloak.
Si infraestructura, imágenes/CVE o suites no se verifican, gate pendiente y NO-GO;
ninguna excepción implícita. Evidencias y límites en SESSION_02_REVIEW.

Revisión de suministro: la imagen upstream PG18.6 contiene gosu compilado con Go
vulnerable. El directorio de datos de la imagen pertenece a postgres y permite
inicializar sin root. Se construye una derivada mínima del mismo digest, se elimina
el helper gosu y se fija USER postgres; no se omiten CVE por una excepción de scanner.
Validar nueva inicialización sobre volumen temporal, migraciones, restart y nuevo
scan antes de cerrar el gate. Imágenes finales y CVE se registran con evidencia.
Python Linux usa 3.13.14/alpine3.24 fijado por digest, conservando interpreter/lock;
evita una base Debian más antigua y reduce superficie. Wheels musllinux deben
resolver sin compiladores y superar la misma suite. Git 2.54.0-r0 solo en imagen
de tests para probar el scanner de historial; nunca en runtime.

La suite con cobertura y scanner concurrente detectó que el timeout de health (1 s)
se estaba reutilizando para todas las escrituras: un append esperando el head fue
cancelado. Se conserva 1 s para queries del API/health; UoW de provisión/escritura
dispone de 5 s para statement/lock y espera de pool. Sigue siendo un presupuesto
acotado, inferior al deadline API 10 s. Se mantiene la prueba de 20 appends; no se
reduce concurrencia ni se transforma timeout en éxito. Un timeout provoca rollback
y se prueba también su integridad. S03 definirá la política de reintentos transitorios.

El scan inicial de la base Python encontró 9 entradas altas: OpenSSL 3.5.7 y
libuuid 2.42. Se verificaron paquetes corregidos en el repositorio firmado de Alpine
v3.24 y se fijan libcrypto3/libssl3 3.5.9-r0 y libuuid 2.42.3-r1 en la base común.
No se usa upgrade flotante ni exclusión de CVE. Rebuild y nuevo scan obligatorios.
El primer scan de Keycloak agotó el timeout durante análisis, sin informe: BLOCKED,
no cero vulnerabilidades. Reintento con imagen local, caché y presupuesto de 20 min.
