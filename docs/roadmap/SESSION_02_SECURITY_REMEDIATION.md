# S02 — informe de remediación de seguridad

2026-10-23, Europe/Madrid; evidencias UTC. **NO-GO para S03**: remediación local
implementada y probada, CI remota satisfactoria de esta revisión pendiente.
Sin S03, commit, push, merge, release o despliegue; sin excepciones de scanner.

## Git y GitHub Actions

HEAD/origin/main: f165a47b29c22474750be145e5a4caeabd0dc367; árbol inicialmente limpio.
Lectura de AGENTS, constitución, ADR-0001..0006, handoff, revisión/spec y CVE JSON.
Alcance REQ-PLAT-01/02, REQ-HAR-01 → T02-01/05/07/08; supuestos previos en
specs/002-platform/security-remediation.md. Contrato HTTP y alcance S02 preservados.

El [harness publicado](https://github.com/AlmanInDaHouse/OpsPilot-AI/actions/runs/39880622999)
pasó. [Platform S02](https://github.com/AlmanInDaHouse/OpsPilot-AI/actions/runs/39880623171)
falló: quality Windows/Ubuntu PASS, integración 50 PASS, PG fresco FAIL en psql;
recovery/scan SKIPPED. ci-post-push.json conserva jobs y steps reales. NOT_RUN del
cierre inicial era histórico; runs Dependabot de otras revisiones no validan main.

Se reprodujo la carrera de initdb: Unix ya aceptaba conexiones mientras TCP fallaba.
La prueba podía ejecutar psql al detenerse el servidor temporal. Ahora espera TCP
loopback del servidor definitivo, conservando network=none, UID 70, SQL y timeout.
Cinco inicializaciones pasaron; fresh-diagnosis.json conserva Unix=0/TCP=2.
La corrección local no convierte la CI anterior en PASS.

## CVE, impacto y versiones

| Hallazgo original | Impacto y corrección investigados |
|---|---|
| CVE-2026-114406; ca-certificates 2025.2.80_v9.0.305-91.el9; Trivy CRITICAL, affected, sin FixedVersion | Intermediarias eMudhra comprometidas permiten suplantación TLS a un MITM. Los almacenes nativo y Java son distintos y requieren comprobación separada. |
| CVE-2026-91415; java-21-openjdk-headless 1:21.0.12.1.1-1.2.el9; HIGH, affected, sin FixedVersion | Java 2D: exposición de APIs vulnerables puede afectar disponibilidad, integridad y confidencialidad. No se demostró ruta explotable en este Keycloak; headless no demuestra ausencia del componente. Sin excepción. |

[RHSB-2026-012](https://access.redhat.com/security/vulnerabilities/RHSB-2026-012)
y la [solución Red Hat](https://access.redhat.com/solutions/7149312) indicaban
actualización en curso. Metadata UBI9 baseos/appstream con checksum ofrecía las dos
versiones instaladas. Quay confirmó mismo digest para latest/26.8/26.8.1; 26.8.2
devolvió not found. No se eligió nightly ni downgrade.

El [CPU Oracle](https://www.oracle.com/security-alerts/cpuoct2026.html) documenta
91415. [Debian](https://security-tracker.debian.org/tracker/CVE-2026-91415) confirma
corrección en OpenJDK 21.0.13+9 en sid; estable conservaba Java vulnerable. No se
mezcló sid con estable. [Oracle 91403](https://www.oracle.com/security-alerts/alert-cve-2026-91403.html)
relaciona el compromiso de CA con Java, incluso versiones recién actualizadas:
no basta con comprobar la cadena de versión 21.0.13.

[Azul](https://docs.azul.com/core/release-notes.html) anuncia 21.54.107 corregido;
API/índice DEB/imagen públicos consultados seguían en 21.0.12.1, búsqueda específica
21.0.13 devolvió [] y URLs ensayados de binario/checksum, 404. Es disponibilidad
observada, no afirmación universal de inexistencia del parche. Corretto publicaba
21.0.12.13.1. Red Hat JSON/Adoptium API devolvieron 403; no se dan por leídos.
provider-probes.json registra resultados y límites.

## Derivadas y procedencia

[ADR-0007](../decisions/0007-keycloak-maintained-runtime.md) fija la decisión.
El primer candidato Debian 12 + Temurin se rechazó: otros altos/críticos sin parche
en candidate-cves.json. No se quitaron metadata/paquetes para ocultar hallazgos.

La receta elegida conserva /opt/keycloak del digest oficial y usa Alpine 3.24.3
por digest, ca-certificates 20261020-r0 y Temurin 21.0.13+9 musl por SHA-256.
[Release Adoptium](https://github.com/adoptium/temurin21-binaries/releases/tag/jdk-21.0.13%2B9),
[paquete Alpine](https://pkgs.alpinelinux.org/package/v3.24/main/x86_64/ca-certificates)
y [APKBUILD](https://gitlab.alpinelinux.org/alpine/aports/-/raw/3.24-stable/main/ca-certificates/APKBUILD)
aportan procedencia. APK valida repositorios firmados; BuildKit valida el checksum
del archivo. No se ejecutó fuente remota ni se editó ningún trust store.

Paquetes directos fijados y build limitado a linux/amd64. Keycloak soporta
[OpenJDK 21 y PG18](https://www.keycloak.org/server/supported-configurations);
musl es compatibilidad probada localmente, no certificación de la imagen oficial.
Se conservan UID 1000, cap_drop=ALL, secretos mínimos y controles OIDC/RBAC.
Inputs fijados en infra/keycloak.Dockerfile; tags locales identifican builds y el
manifest registra digests OCI/config exactos. El autor mantiene esta derivada y
debe revisar actualizaciones; volver a oficial cuando supere los mismos gates.

Ambos almacenes de la imagen final excluyen las cuatro raíces relacionadas.
Java rechaza las 14 cadenas públicas del incidente y acepta un anchor ordinario.
El original también las rechaza: estos negativos solos no prueban una diferencia
ni explotabilidad. No se atribuye al scanner detección completa de CVE de JRE en
tar.gz; avisos, procedencia, versión y almacenes complementan esa limitación.
final-trust.json registra resultados/hashes y probes/TrustProbe.java conserva el probe.

## Gates y decisión

Evidencias bajo artifacts/session-02/remediation, además de los snapshots iniciales.

| Gate de la receta final | Resultado / evidencia |
|---|---|
| Suite Windows | 176 PASS, cero skips; tests-windows-final.xml, coverage-windows-final.json |
| Suite Linux sin root | 176 PASS, cero skips; tests-linux-final.xml, linux-final-runs.json |
| PKCE/OIDC/RBAC, negativos JWT/JWKS, PG/Alembic/UoW/audit | 50 integraciones incluidas en cada suite completa |
| Harness | 23 negativos preservados, incluidos en ambas suites |
| PG fresco y restart/PKCE nuevo | PASS; fresh-postgres-final.json, recovery-final.json |
| Scan imágenes finales | PASS sin altos/críticos; final/postgres-cves.json, final/keycloak-cves.json, final/api-cves.json |
| Calidad, secretos/historial, dependencias y diff | quality-final.json y manifest.json al cerrar |

Se añaden seis casos de aceptación: evidencia ausente/vieja/incompleta, scanner
fallido o falta de checks no pasan. verify_session02 ya no concede GO global por
éxito local. Warning Starlette/HTTPX conservado; transporte de producto sin cambios.

**NO-GO S03.** R15 remediado localmente; R17 exige CI completa satisfactoria del
árbol corregido. Última CI de main FAIL; esta revisión no se publica por instrucción
del autor. No se transforma pendiente en PASS ni se dispara CI remota. La revisión
humana de diff/riesgos y validación empresarial no se presumen. Tras autorización
de publicación, verificar SHA y todos los jobs quality/integration/fresh/recovery/scan
antes de reconsiderar GO; iniciar S03 requiere otra petición.

El laboratorio se detiene conservando volumen y datos; no se operan recursos ajenos.
Parada final con timeout 60 s: PG/API exit 0; Keycloak exit 143 tras SIGTERM. El
log registra Keycloak stopped; no se presenta como exit 0. Ver shutdown-final.json.
JSON/manifest raíz de session-02 son históricos; remediation/manifest.json indexa
este cambio. Raw privados en artifacts/local, ignorados. Candidatos rechazados no
son runtime; las evidencias conservan sus resultados fallidos.
