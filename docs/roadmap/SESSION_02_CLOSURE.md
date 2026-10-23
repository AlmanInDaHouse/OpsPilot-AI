# S02 — auditoría del cierre publicado b221037

Actualización local: [remediación del scanner](SESSION_02_SCANNER_REMEDIATION.md).
La auditoría siguiente se conserva como snapshot histórico. NO-GO S03.

2026-10-23, Europe/Madrid; evidencias UTC. **NO-GO para iniciar S03**.
El run de plataforma terminó en FAIL: falta completar satisfactoriamente los
tres escaneos obligatorios. Calidad, integración funcional, PG fresco y reinicio
sí pasaron. No se modificaron criterios de aceptación, runtime ni workflows.

## Alcance, Git y procedencia

Petición: verificar el cierre publicado; REQ-PLAT-01/02, REQ-HAR-01,
T02-07/08 y AC02-08. Supuesto: un PASS local anterior no valida un build remoto.
Se revisaron AGENTS, README, constitución, handoff, revisión/spec S02, gates,
ADR y el script/workflow publicados. La tarea no incluye implementar S03.

HEAD, origin/main, GitHub refs/heads/main y ls-remote coincidían en `b221037`
al iniciar. El árbol estaba limpio, sin cambios pendientes en HANDOFF.md.
El SHA completo consta en remote-audit.json. Esta auditoría deja documentación
y evidencias nuevas pendientes localmente; no hace commit ni push.

[Platform S02, run 39888916474](https://github.com/AlmanInDaHouse/OpsPilot-AI/actions/runs/39888916474),
intento 1, main, completed/failure; creado 02:19:13 UTC, terminado 02:25:15 UTC.
La API liga el run, sus jobs y el artefacto al mismo SHA completo.
[Artefacto 12473991637](https://github.com/AlmanInDaHouse/OpsPilot-AI/actions/runs/39888916474/artifacts/12473991637):
platform-s02-evidence, 105781 bytes; ZIP descargado, SHA-256 contrastado con
el digest de GitHub y coincidente. remote-audit.json conserva el digest público.
URL firmada temporal y ZIP completo permanecen privados en artifacts/local.

## Gates reales

| Comprobación | Resultado y evidencia |
|---|---|
| Quality Ubuntu, job 120203671714 | SUCCESS; check y suite local SUCCESS |
| Quality Windows, job 120203671880 | SUCCESS; check y suite local SUCCESS |
| Harness del mismo SHA | SUCCESS, run 39888916473 |
| Tests PostgreSQL/Keycloak reales | PASS; integration-ci.xml: 50 tests, 0 fallos/errores/skips |
| Job integration 120204238361 completo | FAIL por scan_images.py, step 11 |
| PostgreSQL fresco, step 9 | PASS; 18.6, UID 70, volumen fresco, network none, TCP final |
| Recuperación tras reinicio, step 10 | PASS; 8 eventos, mismas cabezas/hashes, principal persistido y nuevo PKCE |
| Scan PostgreSQL | BLOCKED, exit 1, sin informe bruto |
| Scan Keycloak | BLOCKED, exit 1, sin informe bruto |
| Scan API | BLOCKED, exit 1, sin informe bruto |
| Artefacto ligado al SHA publicado | VERIFICADO mediante API y digest del ZIP |

Durante la caída PG, live=200, ready=503 y me=503; la recuperación no equivale
a backup/restore ni a workflows durables S03. El harness adicional está en
[run 39888916473](https://github.com/AlmanInDaHouse/OpsPilot-AI/actions/runs/39888916473).
El job integration no debe describirse como SUCCESS aunque sus 50 tests pasen.

## Bloqueo exacto y límites del diagnóstico

El log publicado registra postgres BLOCKED a 02:24:58 UTC, keycloak BLOCKED a
02:25:03 y api BLOCKED a 02:25:07. Los tres JSON tienen exit_code=1,
archive_config_matches=false y carecen de raw_sha256, raw_report e image_id.
En el código publicado, esa combinación implica que no se produjo el informe.
La lista vulnerabilities vacía significa desconocido; no demuestra cero CVE.

summarize() identifica la ausencia del informe, pero main() sobrescribe el motivo
por "Image archive/config mismatch or incomplete report". No se ha demostrado
un desajuste de imagen. El fallo es del gate de escaneo incompleto; no hay datos
para atribuirlo a una vulnerabilidad concreta ni declarar las imágenes limpias.

El workflow solo sube artifacts/session-02; los logs y raw del scanner se escriben
en artifacts/local. Por ello el stderr remoto no está disponible en el artefacto
y no se puede afirmar su causa de bajo nivel con certeza.

Existe un defecto de portabilidad verificable: el script crea bind mounts con
permisos POSIX habituales 0755 del usuario del host y ejecuta Trivy UID 10001.
La prueba local WSL con el mismo scanner por digest y restricciones, directorios
0755 de UID 1000, reprodujo Permission denied al escribir tanto /scan como /cache.
Es una causa plausible del fallo remoto; no sustituye al stderr que falta.
Otra prueba local de Trivy terminó por timeout descargando su DB antes de probar
escrituras; se conserva también, sin presentarla como escaneo de imágenes.

Siguiente corrección necesaria: recuperar logs redacted del scanner; garantizar
escritura de su usuario no privilegiado en directorios dedicados y preservar
el motivo original si falta el informe. Reejecutar todos los gates sobre el SHA
de la corrección y verificar identidad de imágenes/informes. Sin root, chmod 777,
excepciones, desactivar scanner ni rebajar HIGH/CRITICAL. No implementado aquí.

## Consistencia de aceptación y evidencias

Fuente actual: [acceptance.json](../../artifacts/session-02/closure-b221037/acceptance.json)
y [remote-audit.json](../../artifacts/session-02/closure-b221037/remote-audit.json).
HANDOFF y R17 reflejan el mismo NO-GO y el fallo de los tres scans.
No se cambian los criterios de aceptación.

Los acceptance.json raíz y remediation son snapshots históricos anteriores al
push; mantienen NO-GO y describen sus respectivos resultados locales. CI no los
regenera: el ZIP incluye esos archivos del checkout, además de los reports nuevos.
Se verificó igualdad byte a byte de ambos acceptance publicados con los blobs
Git de b221037 y el ZIP; copias exactas quedan bajo published-*-acceptance.json.
Los PASS de remediation/final dentro del ZIP son previos, no scans del runner.
Los manifests históricos permanecen intactos; el manifest de closure-b221037
identifica las copias y sus hashes, sin reinterpretar el snapshot anterior.

## Verificación local de estos registros

python scripts/dev.py check PASS; suite local 126 PASS, 50 integraciones
excluidas explícitamente; harness 23 PASS. La integración remota de 50 casos se
verificó mediante job/log y XML del artefacto, sin arrancar de nuevo el laboratorio.
verification.json separa estas comprobaciones del veredicto del run publicado.
No se convierte el resultado local en aprobación del scanner remoto.

## Riesgos y decisión

R17 permanece ABIERTO y bloqueante: CI de la revisión corregida existe y falla.
R15 solo REMEDIADO LOCALMENTE; la validación supply del build remoto no está
completa. La derivada Keycloak es linux/amd64 y su mantenimiento/procedencia
recaen en el autor; no se afirma certificación del proveedor para musl.
IdP corporativo, auditoría independiente, ancla externa de auditoría y DR completo
siguen fuera de la validación de laboratorio. Ver RISKS y ADR-0007.

**NO-GO S03** hasta que todos los gates obligatorios del SHA corregido pasen.
No se inició S03, ni hubo commit, push, merge, release o despliegue en esta auditoría.
