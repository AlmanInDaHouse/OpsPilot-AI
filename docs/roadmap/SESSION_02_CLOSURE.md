# S02 — cierre técnico formal de 660f7d3

2026-10-23, Europe/Madrid. **GO técnico de S02** exclusivamente para
`660f7d31170de2d8ecb80ddd0bbf7f4c21e8eb20`. R17 RESUELTO TÉCNICAMENTE para ese SHA.
Revisión y aceptación humana del diff/riesgos PENDIENTES: no se encontró acta que
las acredite; «pushealo» autorizó publicación, no aceptación de riesgos.
Sin validación empresarial ni readiness de producción. S03 solo especificada,
sin autorización para implementar el orquestador. Sin commit/push/merge/despliegue.

## Procedencia comprobada

HEAD, origin/main, ls-remote y API refs/heads/main coinciden con el SHA anterior;
Git estaba limpio al iniciar. [Platform S02 39898182916](https://github.com/AlmanInDaHouse/OpsPilot-AI/actions/runs/39898182916),
intento 1, evento push, completed/success; 04:02:31–04:09:25 UTC. Se verificaron
jobs, steps y logs del mismo SHA, sin usar jobs dinámicos de Dependabot como gates.
[Harness 39898182820](https://github.com/AlmanInDaHouse/OpsPilot-AI/actions/runs/39898182820)
también completed/success, mismo SHA e intento 1.

[Artefacto 12477208772](https://github.com/AlmanInDaHouse/OpsPilot-AI/actions/runs/39898182916/artifacts/12477208772),
platform-s02-evidence, 9132 bytes, ligado al run y SHA por la API. ZIP descargado:
SHA-256 coincide con digest GitHub; siete archivos contrastados por tamaño/hash
contra el manifest del runner. El hash de inputs se reprodujo desde los blobs del
commit con el algoritmo del scanner; no se comparó con bytes CRLF del árbol Windows.
Evidencia nueva en [acceptance.json](../../artifacts/session-02/closure-660f7d3/acceptance.json)
y [remote-audit.json](../../artifacts/session-02/closure-660f7d3/remote-audit.json).
El ZIP, URLs temporales y logs completos son privados; copias CI saneadas en ci/.

## Gates técnicos observados

| Gate / job | Resultado real |
|---|---|
| Quality Ubuntu 120233371890 | SUCCESS; check y 162 tests locales PASS, 50 integraciones excluidas explícitamente |
| Quality Windows 120233372189 | SUCCESS; check y 162 tests locales PASS, 50 integraciones excluidas explícitamente |
| Integration 120233939645 | SUCCESS; suite completa Linux 212 PASS, incluidas 50 integraciones PG/Keycloak reales; cero fallos/errores/skips |
| Harness Ubuntu 120233370869 | SUCCESS; docs y 23 tests PASS |
| Harness Windows 120233371030 | SUCCESS; docs y 23 tests PASS |
| Preflight scanner | Ocho casos PASS; host/scanner 1001:1001, tar 0600 readonly y dirs 0700; negativos de permisos incluidos |
| PostgreSQL fresco | PASS; PG18.6, UID 70, volumen nuevo, network none, espera TCP del servidor final |
| Recuperación | PASS; live=200/ready=503/me=503 durante caída PG; ocho eventos y cabezas/hashes idénticos, principal persistido y PKCE nuevo |
| Scan PostgreSQL | PASS, exit 0, JSON válido, identidad y digest coincidentes, 0 HIGH/CRITICAL |
| Scan Keycloak | PASS, exit 0, JSON válido, identidad y digest coincidentes, 0 HIGH/CRITICAL |
| Scan API | PASS, exit 0, JSON válido, identidad y digest coincidentes, 0 HIGH/CRITICAL |

Los tres scans contienen HEAD y hash de inputs coincidentes con el manifest y el
commit. Scanner fijado por digest, sin excepciones ni relajación de severidad.
Los hashes de raw/log son emitidos por el scanner validado; esos ficheros privados
remotos no están en el ZIP y no se rehashearon independientemente aquí. Sí se
verificaron ZIP, manifest y resúmenes, más las validaciones del código que los produjo.
El manifest CI conserva session_03 NO-GO por diseño; es inventario automático, no
acta humana ni veredicto global. La aceptación formal separa esos conceptos.

## Riesgos y alcance del GO

R17: cerrado el bloqueo de aceptación remota de T02-07/AC02-08 para 660f7d3; no
se transforma el run fallido b221037 en PASS ni se confirma su stderr perdido.
Reabrir para una revisión nueva si no se verifican sus propios gates.

R15: mitigación técnica comprobada en el build remoto de ese SHA, con tres scans
limpios según HIGH/CRITICAL y tests reales. Continúa el riesgo de mantenimiento y
cobertura de supply chain: derivada Keycloak 26.8.1 con Alpine/Temurin musl, solo
linux/amd64, inputs fijados, autor responsable de parches/CA/JVM. ADR-0007 sigue
vigente; no certificación del proveedor ni garantía de detectar todo CVE de un JRE
en tar.gz. No se volvieron a ejecutar los probes de trust del snapshot anterior
en CI: se conserva su evidencia histórica, sin atribuirle una ejecución nueva.

GO técnico S02 significa que pasan los controles de esta fase en el laboratorio.
No aprueba IdP corporativo, multitenancy, pentest/auditoría independiente, DR,
backup/restore, HA/SLO/carga, ancla externa de auditoría, privacidad ni producción.
Recovery es reinicio/persistencia, no restauración desde backup ni durabilidad S03.
Revisión humana y aceptación residual siguen pendientes. R01/R02/R14 siguen abiertos
para los hitos que corresponden. La parada local previa exit 137 permanece registrada;
el step stop remoto SUCCESS no demuestra por sí solo todos los exit codes de servicios.

## Continuación y verificación de esta documentación

[SESSION_03_SPEC](SESSION_03_SPEC.md) y [paquete 003](../../specs/003-workflows/spec.md)
están PROPUESTOS: contratos antes de código, intake atómico, cola PG, worker lineal,
leases/fences, cancelación CAS y crash suite real con dos workers/100 jobs. Sin IA,
runner IT ni ejecución externa. La presente petición no inicia su implementación.

Los gates funcionales/integración/scan anteriores se auditaron desde CI real.
Los cambios actuales son solo documentación, trazabilidad y evidencia nueva; las
comprobaciones locales se registran aparte en verification.json. No se presenta
una suite local sin integración como repetición de los 50 casos remotos.
Los snapshots iniciales, remediation, closure-b221037 y scanner-remediation se
conservan. Su NO-GO es histórico; la fuente vigente es closure-660f7d3.

## Auditoría histórica b221037 conservada

Actualización local: [remediación del scanner](SESSION_02_SCANNER_REMEDIATION.md).
La auditoría siguiente se conserva como snapshot histórico. NO-GO S03.

2026-10-23, Europe/Madrid; evidencias UTC. **NO-GO para iniciar S03**.
El run de plataforma terminó en FAIL: falta completar satisfactoriamente los
tres escaneos obligatorios. Calidad, integración funcional, PG fresco y reinicio
sí pasaron. No se modificaron criterios de aceptación, runtime ni workflows.

### Alcance, Git y procedencia

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

### Gates reales

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

### Bloqueo exacto y límites del diagnóstico

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

### Consistencia de aceptación y evidencias

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

### Verificación local de estos registros

python scripts/dev.py check PASS; suite local 126 PASS, 50 integraciones
excluidas explícitamente; harness 23 PASS. La integración remota de 50 casos se
verificó mediante job/log y XML del artefacto, sin arrancar de nuevo el laboratorio.
verification.json separa estas comprobaciones del veredicto del run publicado.
No se convierte el resultado local en aprobación del scanner remoto.

### Riesgos y decisión

R17 permanece ABIERTO y bloqueante: CI de la revisión corregida existe y falla.
R15 solo REMEDIADO LOCALMENTE; la validación supply del build remoto no está
completa. La derivada Keycloak es linux/amd64 y su mantenimiento/procedencia
recaen en el autor; no se afirma certificación del proveedor para musl.
IdP corporativo, auditoría independiente, ancla externa de auditoría y DR completo
siguen fuera de la validación de laboratorio. Ver RISKS y ADR-0007.

**NO-GO S03** hasta que todos los gates obligatorios del SHA corregido pasen.
No se inició S03, ni hubo commit, push, merge, release o despliegue en esta auditoría.
