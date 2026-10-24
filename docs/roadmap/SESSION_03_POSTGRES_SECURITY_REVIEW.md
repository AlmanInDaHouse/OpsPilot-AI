# S03 — revisión de seguridad PostgreSQL / Brotli

2026-10-24, Europe/Madrid. Hotfix local autorizado previo a T03-05.
IMPLEMENTADO/PROBADO localmente. **GO técnico LOCAL para preparar T03-05**.
Autocrítica del mismo asistente; no auditoría independiente ni validación empresarial.
Sin implementación T03-05, commit, push, merge, release o despliegue.

## 1. Causa y alcance

CVE-2026-111497 afecta al decodificador Brotli: escritura fuera de límites al
procesar un stream construido para explotar el fallo. Puede comprometer memoria,
disponibilidad o ejecución de código. La [release del proveedor 1.2.1](https://github.com/google/brotli/releases/tag/v1.2.1)
publica la corrección. La base oficial por digest conservaba brotli-libs 1.2.0-r1.
La clasificación local Trivy es HIGH, estado fixed y FixedVersion 1.2.1-r0.
No se ha demostrado explotación de PostgreSQL ni exposición de una ruta concreta
desde la API. El gate de inventario bloquea la imagen afectada sin exigir explotar
la biblioteca. No se ha eliminado el paquete ni aplicado una excepción.

## 2. Baseline y procedencia

Git main/HEAD e116767635c2f723456dd27cb7d52ce267e147ac, con cambios locales T03-04.
Se conserva el baseline del autor: 666 PASS y 214 integraciones reales por OS,
scan PG FAIL, API/Keycloak PASS; esos resultados son históricos.
El hash del informe bruto real se contrastó con el resumen versionado:
f10fe51694ccedc97ba2868da2104cbd1bd58da826b6b3bacb57e7070c8abbf4.
Identidad OCI antigua a88335c32e200cb4d4a9476632aea4bea9e881afd2f13cf7ab4883920bc2226c;
config Trivy 4030d72fe5e55d7782a50108224e6d912baa4510881caa5a3fb9d69bf259a475.

Inspección real: PostgreSQL 18.6, Alpine 3.24.3 x86_64, UID/GID 70.
Repositorios exclusivamente v3.24/main y v3.24/community del CDN oficial Alpine.
Dependencia observada en la base instalada:
`.postgresql-rundeps → so:libcurl.so.4 → so:libbrotlidec.so.1 → musl`.
libcurl 8.22.0-r0 permanece sin cambios; quitar Brotli rompería esa dependencia.

[Alpine v3.24/main](https://dl-cdn.alpinelinux.org/alpine/v3.24/main/x86_64/)
publica el APK 1.2.1-r0. [Alpine Secdb](https://secdb.alpinelinux.org/v3.24/main.json)
asocia esa revisión con el CVE; consulta real y hash en sources.json. El inventario
instalado y la firma APK se comprobaron separadamente de la disponibilidad web.

## 3. Cambio exacto y reproducibilidad

Único cambio ejecutable: [infra/postgres.Dockerfile](../../infra/postgres.Dockerfile)
añade antes de USER postgres:

```dockerfile
# CVE-2026-111497: signed Alpine 3.24/main fix; retain libcurl's Brotli dependency.
RUN apk add --no-cache 'brotli-libs=1.2.1-r0'
```

Base conservada:
`postgres:18.6-alpine@sha256:898c60cb390d1085bc97bdd6a1ae968757421df394b071848b52b1c09c89d6a5`.
La simulación APK previa resolvió exactamente una actualización. Build normal y
build sin caché ejecutados; versión fijada y paquete firmado, sin mezclar ramas.
La receta falla si esa revisión deja de estar disponible: no hay fallback a edge
ni actualización indiscriminada. No se promete un digest idéntico entre builds:
timestamps de APK/capas y attestations de BuildKit pueden variar. Se registran
identidades de cada build y hashes de las bibliotecas efectivas.

APK SHA-256: 62a7e37e43bbfc1f8525a00ad2125fd5897135dc93b849733884cb78ffd8e26c.
`apk verify` devuelve OK usando las claves Alpine de la base. El inventario completo
confirma que solo brotli-libs cambia a 1.2.1-r0. Sin recompilación ad hoc.
USER postgres, gosu ausente, Compose, UID/GID, secretos, mounts, puertos, redes,
volumen permanente, capabilities, health checks y configuración PG conservados.
Root se usa únicamente para instalar paquetes durante build; PostgreSQL ejecuta
con UID 70. La consulta administrativa de integridad es de solo lectura.

## 4. Imagen final y scans nuevos

Imagen local `opspilot-postgres:18.6-s02`, OCI/index:
39d00c5aa3ce070fafcec7db188b7bea93dbbe87fbe8c521d50a19ec7cc6b993.
Config de build: d8cd50ddd2b30b89523579865861b7edb8ac7322578a84349469db37dbe019ef.
Son identidades del almacén local, no publicación en un registry.
Trivy mantiene su digest, UID 10001, aislamiento, validación de informe completo y
cadena inspect → blobs OCI → config → Metadata.ImageID. Sin cambios de scanner.

| Gate actual | Resultado |
|---|---|
| PostgreSQL final HIGH/CRITICAL | PASS, 0 hallazgos, exit 0 |
| API final HIGH/CRITICAL | PASS, 0 hallazgos, exit 0 |
| Keycloak final HIGH/CRITICAL | PASS, 0 hallazgos, exit 0 |
| Windows completo | 666 PASS, 214 integraciones, 0 failures/errors/skips |
| Linux completo sin root | 666 PASS, 214 integraciones, 0 failures/errors/skips, UID/GID 10001 |
| Check Windows/Linux | PASS ambos, exit 0 |
| PG fresco UID 70 | PASS |
| Datos antes/después de sustituir imagen | PASS |
| Recovery y replay después de reinicio | PASS, hashes de once tablas iguales |

Sin diferencia respecto al baseline de 666 pruebas. Cada OS conserva 30
observaciones de concurrencia/rollback/kill con PG real. Hay un warning de
deprecación Starlette/httpx ya existente por OS, sin tests omitidos ni cambio de
dependencias para ocultarlo. Check incluye lock, Ruff, Markdown, mypy, arquitectura,
Bandit, secretos sobre árbol/historial y pip-audit. Este último no audita el proyecto
local no publicado en PyPI; todas las dependencias indexadas pasan y el código
propio conserva análisis estático/tests. No se ha añadido ninguna excepción.

El check Linux usa copia de archivos públicos y Git montado readonly, UID 10001,
venv Linux construido con el mismo lock frozen y UV_NO_SYNC para reutilizarlo en
la copia readonly, con cachés temporales. `uv lock --check` se ejecuta igualmente.
No se comparte .venv Windows ni se omite ningún paso del harness.

Los JSON brutos nuevos se contrastan por hash; contienen detección OS Alpine y,
donde procede, targets JAR/Python. IDs actuales de inspect y contenedores usados en
la regresión coinciden con los informes finales. image-consistency.json registra
los tres vínculos y el mismo input_sha256 actual. La descarga Java DB terminó antes
del PASS Keycloak; no se aceptó ningún informe parcial ni histórico.

## 5. Integridad, migraciones y recuperación

Snapshot de solo lectura con aislamiento REPEATABLE READ: hashes SHA-256 de filas
ordenadas de las once tablas públicas, revisión 0002_workflows y verificación de
las siete cadenas audit. Comparación tras sustituir imagen: igualdad completa.
Cuatro principals, cuatro grants, once eventos, dos incidents/workflows/jobs,
dos respuestas idempotentes y dos steps conservados; evidence sigue vacía.
El laboratorio permanente no se migra ni limpia para ocultar diferencias.
Durante caída real: live 200; ready/me/intake/lecturas/cancel 503. Tras reinicio,
PKCE nuevo conserva identidad y cadenas audit; replay de cancelación da 202 sin
evento adicional, ETag obsoleto 409, job DEAD/fence 1 e incidente OPEN. Hashes de
todas las tablas iguales también después de recovery. El volumen nominal creado
el 22 de octubre sigue presente; parada local conserva datos y credenciales.

PG fresco usa contenedor propio sin red y volumen anónimo efímero. La suite usa
bases opspilot_test_UUID propias para Alembic 0001/0002, N-1 con datos, rollback DDL
y de transacción/COMMIT, permisos restringidos, revoke/disable, auditoría v1/v2,
intake atómico, idempotencia concurrente y cancelación CAS/fence API/SQL.
Claim/completion del worker y AC03-06 completo siguen pendientes de T03-05/06.

## 6. Intentos fallidos y límites

La primera captura de todas las tablas con rol app falló por permiso de SELECT
en workflow_steps. Se repitió con conexión administrativa existente y transacción
de solo lectura; no se ampliaron grants del producto.
`apk fetch` por nombre sin índice descargado no resolvió el paquete en el probe;
la descarga directa del APK oficial y `apk verify` sí pasaron. Build APK pasó.

La primera suite Windows devolvió 564 PASS, 1 FAIL y 101 ERROR: Keycloak respondió
500 al autenticar después de recrear PG, con conexiones JDBC cerradas en logs.
Health verde no acreditó OIDC. Se reiniciaron Keycloak/API y se repitió la suite
completa; el intento fallido se conserva. Operativamente, tras recrear PostgreSQL
hay que comprobar PKCE real y reiniciar los clientes que retengan conexiones rotas.

Primer check detectó hashes públicos del inventario como cadenas de alta entropía.
La evidencia se normalizó al formato de checksum ya admitido por el scanner;
capturas originales privadas con hash conservadas, sin excepciones nuevas ni
cambios de scanner/metadatos APK de la imagen. El check Linux inicial no llegó
a arrancar por faltar el punto de montaje .git dentro de la copia readonly; se
creó el directorio vacío antes de montarlo y el harness completo posterior pasó.

## 7. Evidencias, riesgos y decisión

[Spec previa](../../specs/003-workflows/postgres-security.md),
[evidencias nuevas](../../artifacts/session-03/postgres-security) y verificación
actual en ese directorio. Raw/XML/logs privados permanecen en artifacts/local;
resúmenes saneados, hashes y manifests permiten contrastar los resultados.
Los snapshots anteriores no se modifican; baseline.json identifica el árbol inicial.

R15 requiere mantenimiento continuo: fijar base/paquete no congela el conocimiento
de CVE ni garantiza disponibilidad indefinida del repositorio. Los tres scans se
deben repetir tras cada build. Keycloak derivado musl/linux-amd64 conserva los
límites ADR-0007. Recovery por restart no acredita backup/restore ni HA. R01,
R02/R14 y privacidad siguen abiertos; auditoría no equivale a WORM.

Decisión técnica LOCAL T03-05: **GO** para este árbol e imágenes verificadas.
El bloqueo concreto de R15/CVE-2026-111497 queda remediado localmente. Comenzar
T03-05 requiere una nueva petición; este hotfix no implementa ni autoriza el worker.
S03 abierta, T03-05/06 sin implementar, CI del árbol sin publicar NOT_RUN,
sin GO S03 completa/S04/producción ni readiness empresarial.

Git final: main/HEAD e116767, sin commit/push. T03-04 pendiente permanece intacta.
97 archivos de src/contratos/migraciones/scripts/tests y 187 evidencias históricas
conservan los hashes iniciales. Además del Dockerfile se actualizan solo los
documentos de imágenes/handoff/riesgos, checklist/tareas y trazabilidad; se añaden
esta revisión, spec acotada y evidencias propias. preservation.json y manifest.json
permiten revisar el alcance sin confundirlo con el diff previo de T03-04.

## LO QUE DEBE COMPRENDER EL ARQUITECTO

Los tests funcionales demuestran comportamientos concretos de aplicación y DB;
no recorren todas las entradas maliciosas de cada biblioteca del sistema. Una
dependencia transitiva instalada forma parte del runtime aunque el código Python
no la importe directamente. Si un decodificador permite corrupción de memoria,
los controles de aplicación y los tests verdes no reparan ese código nativo.
Por eso el gate supply puede bloquear el producto con 666 tests correctos.
La corrección exige paquete mantenido, procedencia verificable, scan de la imagen
final y regresión real de datos/identidad/auditoría. Un PASS de scan tiene alcance
de imagen, fecha y base de vulnerabilidades; no demuestra ausencia absoluta de riesgo.
