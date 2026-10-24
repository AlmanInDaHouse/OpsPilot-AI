# S03 — revisión de acceso y cancelación T03-04

2026-10-23, Europe/Madrid. Alcance solicitado: exclusivamente T03-04.
IMPLEMENTADA/PROBADA funcionalmente; NO-GO de avance por gate de imágenes.
Autocrítica del mismo asistente,
no auditoría independiente. Sin worker, commit, push, merge, release ni despliegue.
S03 sigue abierta; NO-GO S04/producción.

## 1. Estado inicial y baseline

Root C:/Users/manul/OneDrive/Escritorio/opspilot-ai, main/HEAD e116767, árbol limpio.
La petición describía T03-02/03 locales; Git muestra que ya estaban publicadas en
ese commit. Se preservan sus snapshots y código de persistencia/intake. Sin reset,
stash, limpieza, cambio de migraciones ni reconstrucción del volumen.
Baseline ejecutado antes de producto: 567 PASS Windows y 567 PASS Linux, incluyendo
155 integraciones reales por OS; check PASS. Laboratorio inicialmente detenido.
`compose start --wait` no existe en esta versión: fallo de CLI sin mutación;
arranque con `up -d --no-build --wait` de las imágenes existentes, sin rebuild.

## 2. Alcance, contratos y trazabilidad

REQ-WF-01/02/03 → AC03-03/06/09 → T03-04 → [spec previa](../../specs/003-workflows/access-cancel.md)
→ [trazabilidad](../../specs/traceability.json) → código/tests/evidencias.
GET incident, GET workflow y POST cancel implementados; POST intake y los cuatro
GET de plataforma conservados. Sin otros endpoints, body/query de dominio,
conditional GET, cambios de wire, dependencias, DDL o grants.

## 3. Consultas autorizadas y no filtración

[PostgresWorkflows.read](../../src/opspilot/adapters/postgres/workflows.py) consulta
roles locales vigentes antes de buscar recursos. La consulta de proyección vuelve
a incluir enabled/grants/creator en su predicado SQL: no reutiliza un booleano de
auditor que pudiera haberse revocado entre consultas. Auditor explícito lee todo
el lab; operator solo sus recursos. Admin/approver no heredan lectura; múltiples
grants suman únicamente sus permisos expresos. El JWT autentica issuer/sub, nunca
otorga estos grants. Deshabilitado/revocado se deniega, sin caché de autoridad.

Faltante y oculto usan el mismo NOT_FOUND/404, body code/request_id sin ETag ni
versiones/creator/SQL. Cancel consulta creator en el propio WHERE antes de CAS.
Operator tampoco puede extraer eventos ajenos por audit: requiere auditor/admin
explícitos conforme al contrato S02. Estos grants de audit conservan su autoridad
propia; no se amplía ni elimina ese permiso preexistente.

GET incident proyecta exactamente Incident, incluido creator_id autorizado y
workflow_id. Solo hay un workflow creado por intake; si se preparan históricos,
la relación elige el más reciente por created_at/id de forma determinista.
GET workflow obtiene estado/version y referencias de evidence en un SELECT,
con un único snapshot READ COMMITTED confirmado. No mezcla evidence de una
consulta posterior con una versión anterior. Sin texto/payload de evidence,
audit privado, claves de idempotencia, ownership, fences o credenciales.

## 4. ETag e input

[WorkflowTag](../../src/opspilot/workflows/domain/access.py) acepta solo etiqueta
fuerte exacta, UUID lowercase y versión decimal positiva sin ceros iniciales,
máximo bigint 9223372036854775807. If-Match ausente, duplicado, weak, wildcard,
listas, espacios y overflow: 422. UUID válido distinto: 409 después de visibilidad.
GET workflow y cancel emiten el ETag de la versión que devuelven. Sin 304 ni
permiso implícito en el tag. DTO cerrados y errores conservan no-store/nosniff,
request_id de servidor y WWW-Authenticate en 401.

## 5. CAS, locks y commit

[WorkflowAccess.cancel](../../src/opspilot/workflows/application/access.py) usa
PostgresAccessUow, una subclase que solo enlaza el repositorio y traduce errores.
Begin/commit/rollback/close proceden del PostgresUow existente; no segundo gestor.
El adaptador autoriza, bloquea workflow del creador, reconsulta grant después de
la espera y compara recurso/version antes de terminales. UPDATE incluye además
WHERE version esperada. No mutex Python ni comparación desprotegida.

Orden: workflow → jobs por id → stream audit. Estado seguro: CANCELLED/version+1,
cancel_requested_at=COALESCE(valor,clock_timestamp()) asignado por PG. El trigger
existente valida arista/version, limpia resume_state y prohíbe borrar intención.
No se toca la incidencia: sigue OPEN/version 1. Commit sucede antes de devolver
el resultado al endpoint. Fallo de statement/appender/constraint/COMMIT: rollback
y 503, jamás 202 supuesto. Timeout HTTP/commit incierto exige releer el estado;
503 no prueba ni éxito ni ausencia de commit.

## 6. Jobs y protección futura

Jobs READY/LEASED pasan a DEAD, owner/lease NULL y fence+1 bajo locks reales.
DONE/DEAD quedan intactos. Overflow numérico falla cerrado y revierte todo.
El trigger de workflows rechaza resucitar CANCELLED aun con rol worker real.
La prueba de predicado SQL obsoleto demuestra que owner/fence antiguos ya no
coinciden; NO demuestra un handler worker implementado.

T03-05/06 debe validar owner/fence/lease vigente/version y cancel_requested_at
antes de cualquier resultado/evidence/nuevo job en el mismo UoW. Claim debe
respetar estado/intención y no mantener job lock mientras espera workflow.
No afirmar AC03-06 completo hasta probar cancel vs claim/completion del worker
real. Tampoco se implementa reconciliador ni cuarentena de recurso futura.

## 7. Terminales y estados ambiguos

CANCELLED actual: 202 con versión/timestamp iguales, sin UPDATE/job/audit nuevo.
Obsoleto: VERSION_CONFLICT antes de cualquier terminal. SUCCEEDED/FAILED actuales:
TERMINAL_WORKFLOW. EXECUTING/VERIFYING/OUTCOME_UNKNOWN conservan estado; intención,
versión y workflow.cancel_requested/CANCEL_REQUESTED se persisten una vez.
Repetición actual no escribe; no retry de acción, eliminación de evidencia ni
liberación de cuarentena. Se invalidan jobs pendientes para impedir nuevo trabajo.
La reconciliación posterior necesita su contrato/implementación de S05/S06.

Los tests preparan estados futuros por privilegios de fixture en bases efímeras,
sin endpoint de prueba. PLAN_READY/AWAITING_APPROVAL requieren un baseline
sintético v2 de definición desconocida, válido en schema/hash, insertado por admin:
el appender actual no produce la historia de un motor futuro. Se comprueba la
cancelación de ese estado preparado; no su alcanzabilidad ni ejecución histórica.

## 8. Auditoría v2 y atomicidad

Se reutiliza PostgresWorkflowAppender/audit_append_v2 sin modificar sus bytes.
Cancelación inmediata: workflow.transitioned/CANCELLED_BY_OPERATOR, creator como
actor, from/to/definition/version y hash del snapshot posterior. Diferida:
workflow.cancel_requested/CANCEL_REQUESTED sin transición inventada. Tiempo,
event_id, seq/hash y stream head los asigna DB. Evidence_ids vacío en cancel;
referencias existentes no se eliminan. Snapshot privado ligado al hash y cadena
validada; no texto libre ni secretos. Eventos v1 históricos intactos.

## 9. Pruebas Windows y Linux

Fuente de resultados, comandos, exit codes y hashes:
[verification.json](../../artifacts/session-03/access-cancel/verification.json).
Revisión final: __666 PASS Windows y 666 PASS Linux__, __214 integraciones reales
por OS__, cero failures/errors/skips. Son 99 pruebas adicionales: 59 integración,
20 unitarias, 14 contratos y 6 negativos de arquitectura. Check completo Windows
PASS; dependencia Linux PASS como UID 10001 con caché temporal escribible.
Los XML/raw permanecen privados; resúmenes y observaciones JSON saneadas en ese
directorio. PG18, Keycloak/PKCE y rol app restringido reales. Linux sin root.
Sin SQLite ni skips de integración; dobles únicamente para unit/contratos.
No CI remota del árbol sin publicar.

Negativos: roles, token ausente/inválido/ID token/caducado, grant revocado,
disabled, operador ajeno con otro token real, auditor read-only, múltiples grants,
body/query, If-Match estricto, entidad/version incorrectas y ruta audit alternativa.
El test de caducidad reduce a un segundo el TTL del cliente PKCE sintético local,
lo restaura inmediatamente tras emitir y espera exp+skew real. No simula reloj,
firma ni verificador; suites completas se ejecutan secuencialmente para no cruzar
esa modificación temporal del IdP.

## 10. Carreras y fallos

Dos y veinte cancelaciones versión igual: un ganador 202, demás 409, un evento y
una versión nueva. Veinte HTTP en dos procesos reales y una tercera API tras
reinicio: mismo resultado durable. Locks observados mediante pg_stat_activity,
barreras y confirmaciones, sin sleeps como prueba de orden. Bloqueo de workflow,
job y appender impide 202 y visibilidad parcial; claim sintético de job mientras
cancel espera acaba invalidado con fence incrementado. Carrera con UPDATE de
versión devuelve conflicto; revoke/disable durante espera se revalidan.

Triggers SQL de test fallan workflow/job/audit; constraint diferida falla en
COMMIT real. Estado y jobs antes/después idénticos, sin evento parcial; retirado
el fallo se acepta. lock_timeout real revierte incluso UPDATE previo de workflow.
Procesos HTTP mueren antes/después de COMMIT, antes de cualquier 202: transporte
perdido y estado durable comprobado por otra conexión. Retry usa versión actual;
tras commit perdido, versión vieja da 409 y GET permite recuperar ETag actual.

PG fresco PASS y recovery real PASS: live 200, ready/me/intake y las tres rutas
nuevas 503 durante caída PG. Tras reinicio, audit heads/hashes iguales y PKCE nuevo
válido. Smoke de imagen final conserva cancelación v2, timestamp, job DEAD/fence 1
y un evento tras reinicio; replay actual 202 sin cambios, viejo 409 e incidente OPEN.
El lab conserva el intake previo T03-03 y añade solo el caso sintético T03-04:
cuatro principals/grants, dos incidents/workflows/jobs, once eventos/siete streams.
La incidencia anterior conserva su job READY; el workflow cancelado solo tiene DEAD.
Laboratorio detenido con volumen/credenciales preservados.

## 11. Fallos de desarrollo conservados

Primer paquete: 63 PASS/1 FAIL por pasar str al helper que exige Role; corregido
el test y repetidas las integraciones. Segundo: 55 PASS. Bloque adicional: 5 PASS.
Primera regresión completa: 616 PASS/50 FAIL; Keycloak mezcla atributos y omitir
el override no restauraba el TTL. Se borra explícitamente con valor vacío y se
verifica mediante GET y token nuevo de 300 s. Dos negativos OIDC calculaban iat/nbf
al recoger tests; ahora los calculan al ejecutarse, manteniendo los mismos límites.
Segunda: 665 PASS/1 FAIL por asumir dos eventos en paginación de un stream que ahora
tiene revocaciones reales; compara las páginas con las secuencias confirmadas PG.
Repetición: 666 PASS. Bandit señaló composición de SQL constante; se sustituyó por
dos consultas completas estáticas sin supresión, y la revisión final pasa 666/OS.

Checker detectó tres inicializadores vacíos sin newline; se añadieron docstrings.
Metadatos usaban nombres no reconocidos para hashes públicos: se adoptaron las
claves hash/raw_sha256 ya admitidas, sin nuevas allowlists. Ruff tuvo un aviso de
caché Windows sin fallo de lint. Primer pip-audit Linux no pudo crear caché bajo
/home/opspilot; XDG_CACHE_HOME temporal permite analizar como UID 10001. Logs de
intentos y hashes conservados; no se relajaron verificadores ni permisos.

## 12. Autocrítica y riesgos

La aplicación sigue siendo frontera confiable: no RLS por usuario y app puede
escribir las columnas autorizadas por 0002. La comprobación de grants tiene un
punto de autorización; revoke posterior a él no revierte retroactivamente una
transacción. Revalidar tras row lock evita usar grants anteriores a una espera,
pero no promete serializar todas las revocaciones concurrentes.

Bloquear todos los jobs por id simplifica orden con la cola mínima; más historial
puede aumentar latencia. Esperas acotadas pueden devolver 503 bajo contención.
El row lock no coordina acciones remotas y fence local no deshace efectos ya
enviados. Hash chain no es WORM frente al admin. Crash suite API no acredita
HA, backup/restore, 100 jobs ni worker/fences operativos. R01/R02/R14, privacidad
R11 y mantenimiento R15/musl/linux-amd64 siguen abiertos en sus fases.
El scan nuevo de PostgreSQL es FAIL: CVE-2026-111497/HIGH en brotli-libs 1.2.0-r1,
FixedVersion 1.2.1-r0 según Trivy. No hay excepción ni herencia del PASS T03-03.
La imagen PG no cambió durante T03-04; la base de vulnerabilidades sí puede revelar
findings nuevos. Requiere remediación/revalidación de imágenes antes de avanzar.
Scans finales Keycloak/API PASS, cero HIGH/CRITICAL; PostgreSQL FAIL por un HIGH.
Identidades OCI de los tres reportes contrastadas con las imágenes actuales.
La base Java tardó unos diez minutos en descargarse; scan completado, no BLOCKED.

## 13. Estado Git y operación

HEAD e116767/main; cambios locales T03-04 sin commits. Migraciones 0001/0002,
audit/models, intake y evidencias históricas conservados. Inventario y preservación
en evidencia propia. Lab operado exclusivamente local; parada final conserva
volumen y credenciales. Sin herramientas IT, IA, UI ni infraestructura externa.

## 14. GO / NO-GO local para T03-05

__NO-GO local para T03-05__: gate de imágenes fallido, aunque la funcionalidad y
las regresiones de código pasan. Resultados de cada imagen en verification.json.
Remediar y revalidar antes de preparar T03-05; no se inicia ni cierra S03. AC03-03/09 en este
alcance y parte API/SQL de AC03-06; worker/claim/completion de AC03-06 pendientes
T03-05/06. CI/publicación/aceptación humana global quedan en T03-07/08.

## LO QUE DEBE COMPRENDER EL ARQUITECTO

__CAS.__ En PostgresWorkflows.cancel se bloquea workflow y se compara version;
UPDATE vuelve a exigirla. Dos peticiones con v1: A confirma v2, B despierta, ve
v2 y devuelve 409. B no puede auditar una segunda transición.

__JWT y autorización.__ actor verifica el token y obtiene principal local.
require_workflow_read y authorize comprueban grants habilitados en PG; un token
de admin o un claim operator no sustituye al grant local ni a ser creador.

__ETag/If-Match.__ WorkflowTag.wire genera comillas, UUID y versión exactos.
GET entrega v1; cancel con ese tag exige v1, y tras commit devuelve v2. Copiar
un tag de otro recurso da conflicto después de comprobar visibilidad; conocer
un UUID/tag nunca permite leer ni cancelar el recurso de otro operador.

__Qué evita el row lock.__ FOR UPDATE hace esperar B mientras A cambia estado.
Sin ese lock, ambas podrían decidir sobre v1 antes de actualizar. El predicado
CAS y los triggers añaden guardas SQL, sin depender de memoria del proceso.

__Cancelar no deshace efectos.__ La rama ambigua de cancel conserva EXECUTING,
VERIFYING u OUTCOME_UNKNOWN, escribe intención y audita; no inventa una prueba
de ausencia de efecto. CANCELLED tampoco cambia incidents.status a resuelto.

__Resultado obsoleto.__ UPDATE jobs elimina owner/lease e incrementa fence;
el token antiguo deja de coincidir. El futuro handler debe comprobar también
version/intención y lease con reloj PG antes de persistir. El test de SQL no
reemplaza ese handler ni sus carreras reales de T03-05/06.

__Workflow, jobs y audit.__ Son tres vistas de una operación durable: estado,
trabajo pendiente y explicación verificable. PostgresAccessUow usa la misma
sesión para los tres; si audit falla, no queda CANCELLED con job READY ni una
cancelación sin ledger. El timestamp original y el evento no se recrean al retry.
