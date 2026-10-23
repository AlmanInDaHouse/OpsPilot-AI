# S02 — remediación del scanner CI

2026-10-23, Europe/Madrid. REQ-HAR-01 / REQ-PLAT-01, T02-07/08, AC02-08.
**NO-GO S03**: cambios locales sin commit/push; CI del nuevo commit pendiente.
Se conservan la auditoría b221037, snapshots anteriores y modificaciones locales
que ya existían al comenzar. No cambios en negocio, contratos, imágenes ni S03.

## Causa e incertidumbres

Reproducido con el scanner fijado: host Ubuntu WSL2 UID/GID 1000:1000 y mounts
0755 de ese propietario impiden escribir como 10001:10001. El probe real devuelve
exit 1 y Permission denied tanto en salida como en caché. Confirma el defecto
POSIX. El stderr de Trivy del run remoto 39888916474 sigue ausente: su causa exacta
permanece sin confirmar. Su log de job se consultó nuevamente mediante GitHub.

Durante la corrección se observaron otros dos fallos locales, conservados:
Docker Desktop 29 usa Id de índice OCI, distinto del config ID; y el primer
rootfs readonly con tmpfs 256 MiB agotó espacio al descargar la DB. Ninguno se
atribuye al run remoto. scans-windows-first y scans-windows-second son intentos
BLOCKED históricos de este trabajo, no resultados aprobados.

## Implementación y permisos

[Spec acotada](../../specs/002-platform/scanner-remediation.md). Staging temporal
propio, fuera de artifacts/local. Montajes: un solo tar readonly, salida propia
y caché propia. No se expone el directorio privado del lab, socket ni credenciales.
Linux usa UID/GID efectivos no cero, directorios 0700 y tar 0600. Windows conserva
10001:10001, con lectura/escritura reales verificadas por Docker Desktop. Sus
modos POSIX 0777 son sintéticos: no se ejecuta chmod 777 ni se amplían ACL del lab.

Rootfs readonly, sin capacidades, no-new-privileges y límites de CPU/memoria.
El probe no tiene red. El scan necesita red para las DB oficiales; TMPDIR apunta
a cache/tmp, con espacio de disco dentro del único mount de caché. Sin excepciones
ni skip de actualización. El staging se elimina al terminar cada invocación.

Identidad: se conserva inspect/config/reporte para Docker clásico; para containerd
se verifica SHA-256 de cada blob índice → manifest linux/amd64 → config, y la
igualdad del config con Metadata.ImageID. No se omite la identidad por ser distinta
la representación del backend Docker. Tar y scanner siguen fijados/contrastados.

## Diagnóstico y CI

Returncode observado, existencia/validez del JSON, UID/GID, owner/modo, I/O y hashes
quedan en evidencia. Deadline anfitrión implica exit_code null, no código inventado.
Las causas son PERMISSION_DENIED, CACHE_UNWRITABLE, INPUT_UNREADABLE,
SCANNER_RUNTIME_ERROR, SCAN_TIMEOUT, INVALID_REPORT, VULNERABILITIES_FOUND e
IMAGE_ID_MISMATCH. JSON ausente o corrupto siempre bloquea. CVE HIGH/CRITICAL falla.

Raw/logs íntegros permanecen ignorados bajo artifacts/local/image-scans; las pruebas
finales usan además artifacts/local/scanner-remediation. Solo se publican campos
permitidos, diagnóstico fijo y hashes. No se copian líneas arbitrarias de stderr.
CI ejecuta preflight, suite completa real y scans independientes; un fallo conserva
el job fallido, con manifest/upload always de artifacts/session-02/ci exclusivamente.
No sube snapshots antiguos del checkout como evidencia actual. El manifest calcula
integridad, no concede GO. HEAD más hash de inputs distingue cambios sin commit.

## Verificación y evidencia

Directorio nuevo: artifacts/session-02/scanner-remediation. Los resultados finales
y hashes se consolidan en acceptance.json y manifest.json de ese directorio.
Los intentos anteriores se conservan con su resultado y hash de inputs propio;
un resultado con inputs distintos no se presenta como validación del árbol final.

Suites finales Windows y Linux (contenedor Alpine/Python 3.13.14): 212 PASS cada
una, 0 skips; incluyen 50 casos con
PG/Keycloak reales y los 23 tests del harness. Las 49 pruebas de scanner/aceptación
incluyen permisos, timeout, código inesperado, JSON ausente/corrupto, CRITICAL,
identidad incorrecta, cadena OCI alterada y contención. Probes reales: 4 casos
Windows y 8 Ubuntu PASS. En Windows los negativos son mounts readonly/entrada
ausente; Ubuntu añade permisos 0500/0000 y UID distinto del propietario.
PG fresco y recovery PASS; reinicio no equivale a backup/restore ni S03 durable.
Warning Starlette/HTTPX existente conservado.

Los scans finales repiten las tres imágenes con la función real de producción
scan, en ambos anfitriones. Reutilizan únicamente la DB de vulnerabilidades ya
descargada en esta sesión; Trivy conserva su comprobación normal de actualización.
El driver privado no simula subprocess ni scanner y no usa skip-db-update.
Los JSON brutos se contrastan con sus hashes y las identidades Docker actuales.

## Riesgos y entrega

R17 sigue ABIERTO: CI remota satisfactoria del nuevo commit es obligatoria antes
de reconsiderar GO. R15 requiere mantenimiento de imágenes y DB de scanner; el
scan de Trivy no certifica toda la supply chain ni elimina los límites del JRE en
tar.gz documentados en ADR-0007. La derivada sigue limitada a linux/amd64/musl.
DB de Trivy grande requiere disco/red; errores o deadlines bloquean, sin excepciones.
IdP corporativo, DR y auditoría independiente siguen pendientes fuera del lab.

No commit, push, merge, release, dispatch ni despliegue. Rama main, HEAD b221037;
árbol con cambios previos preservados más esta remediación. No autorización de S03.

Parada final: comando stop exit 0; PG exit 0, API y Keycloak exit 137, OOMKilled
false. No se presenta como parada graceful. Volúmenes/datos conservados; el scope
del scanner no cambia el runtime para ocultar esa observación. Ver shutdown.json.

Cierre de evidencias: los seis scans finales PASS (PostgreSQL, Keycloak y API en
Windows y Ubuntu), 0 HIGH/CRITICAL, JSON válidos y hashes brutos/logs contrastados.
Ambas series coinciden con HEAD y hash de inputs actual; acceptance.json y los dos
verification-*.json mantienen S03 NO-GO. check Windows/Linux, secretos/historial,
dependencias, links/Markdown y diff aprobados; 95 % cobertura combinada de backend.
Los 23 tests del harness se ejecutaron además por su entrypoint. Ningún snapshot
histórico fue modificado; manifest.json enumera evidencias nuevas y sus hashes.
