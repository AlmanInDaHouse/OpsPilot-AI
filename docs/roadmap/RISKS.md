# Registro de riesgos y decisiones abiertas

## T03-06 — 2026-10-25

R01: reclaim/retry/deadline/commit incierto implementados localmente; gates efectivos
en [revisión recovery](SESSION_03_RECOVERY_REVIEW.md) y verification.json separado.
Owner autor, cierre global S03 pendiente. Accounting tras crash es conservador hasta
lease_until, con redondeo superior por segmento; no mide CPU. Registros históricos
0002 conservan solo budget conocido y última ventana de lease, sin reconstrucción
de procesamiento anterior. Jobs es fuente durable y budget de workflow proyección
en transiciones, sin versiones artificiales por heartbeat. Inconsistencias se retienen
fail-closed. Función nueva solo boolean/EXECUTE worker, sin grants del ledger.
R16: ejecutar reconstrucción/reinicio y suites de integración secuencialmente;
arranque/edición concurrentes invalidaron el primer baseline y recreación PG
interrumpió un focused. Fallos conservados, nunca contados como PASS.
También se reprodujo un retroceso de reloj PG de aproximadamente 5 s tras claim
válido (selection-diagnostic.json). Cursor de accounting monotónico evita doble
cómputo; fixtures envejecidas evitan asumir elegibilidad inmediata tras ese salto.
Las fechas absolutas no se reinician. Dueño autor: estabilizar reloj del servidor
para interpretar duraciones físicas/SLO; no afirmar HA ni reloj monotónico de PG.
R02/R14 externos, privacidad y R15/musl/linux-amd64 continúan; no HA/backup/restore,
exactly-once externo ni WORM frente al administrador. Sin GO S04/producción.

## T03-05 — 2026-10-24

R01 sigue ABIERTO: worker PG real con dos procesos/100 jobs, leases/fences/CAS,
cancelación y commit atómico; [revisión y gates](SESSION_03_WORKER_REVIEW.md).
No reclaim/retry integral ni recuperación adversarial completa hasta T03-06.
Tras crash, LEASED retenido evita ejecución especulativa pero requiere recuperación
posterior: no se acredita eventual progreso de todos los jobs. Deadline/presupuesto
solo guardas mínimas. DB/commit incierto exige inspección durable antes de recuperación.
Dueño autor, gate S03; sin GO S04. R02/R14 externos, R11/privacidad y R15/mantenimiento
musl/linux-amd64 continúan. Audit no es WORM ni estas pruebas auditoría independiente.
Regresión final 715 PASS/OS y nuevos checks/scans/fresh/recovery PASS. R16 conserva
sensibilidad del lab compartido: primer run Linux falló en intake antiguo, sin causa
confirmada; diagnóstico aislado y repetición nativa completa pasaron sin tocar tests
antiguos/timeouts. Rama COMMIT_UNCERTAIN implementada, pérdida de transporte justo
durante COMMIT worker todavía no ejercitada; campaña completa T03-06.
Snapshots inferiores conservan decisiones y findings históricos.

Estado: evaluación de diseño, no incidentes de producción. Autor = responsable técnico.
Prioridad crítica implica NO-GO en hito indicado si no se resuelve. Alternativas no
autorizan cambios externos ni reejecución de operaciones ambiguas.

## Hotfix PG / R15 — 2026-10-24

R15: brotli-libs 1.2.0-r1/CVE-2026-111497 HIGH confirmado en la imagen PG local.
Hotfix instala 1.2.1-r0 oficial firmado de la misma rama Alpine 3.24, sin retirar
dependencias, cambiar distribución ni exceptuar CVE. Solo ese paquete cambia.
PG final scan PASS, suites 666 PASS/OS, 214 integraciones/OS, checks, PG fresco,
recovery y hashes de datos PASS. Tres scans finales PASS, cero HIGH/CRITICAL,
identidad/procedencia verificadas: R15 REMEDIADO LOCALMENTE para este build;
GO técnico LOCAL para preparar T03-05, sin inicio automático ni cierre global S03.
Fuente actual: [revisión](SESSION_03_POSTGRES_SECURITY_REVIEW.md).

Dueño autor: mantener base/pin y repetir todos los scans por build; disponibilidad
del APK histórico no garantizada. Sin GO remoto/empresarial. Persisten ADR-0007
musl/linux-amd64, R01/AC03-06 parcial, R02/R14, privacidad y ausencia de backup/restore
probado. Después de recrear PG, Keycloak puede conservar conexiones JDBC cerradas:
reiniciar dependientes y comprobar PKCE real; health verde fue insuficiente.
Se conservan a continuación los estados históricos del build anterior.

## T03-04 — alcance local, 2026-10-23

R01 continúa ABIERTO: cancelación CAS, carreras API/SQL, audit/rollback y procesos
HTTP probados con PG/Keycloak; no worker ni 100 jobs. AC03-06 solo parcial hasta
claim/completion real T03-05/06. API invalida jobs/ownership/fence; el handler futuro
debe validar además versión, lease e intención, sin espera workflow bajo job lock.
Revocación concurrente se decide en el último punto de autorización; no es
retroactiva ni serializa todos los cambios de grants. Aplicación confiable, sin RLS.
R02/R14 siguen pendientes: cancelar no deshace efectos remotos ni libera UNKNOWN.
R11/privacidad y R15/musl/linux-amd64 vigentes; sin GO S04/producción ni CI nueva.
Autocrítica y resultados actuales en SESSION_03_ACCESS_CANCEL_REVIEW.md.
R15 / gate de imágenes del árbol T03-04: PostgreSQL FAIL por
CVE-2026-111497/HIGH, brotli-libs 1.2.0-r1, corrección 1.2.1-r0 según Trivy.
Imagen PG preservada desde baseline; no se hereda el scan PASS histórico.
Dueño autor; NO-GO T03-05 hasta remediación de imagen y revalidación del build.

## Arranque S03 — T03-01, 2026-10-23

Actualización T03-02: el autor aprueba cierre/riesgos S02 y T03-01/ADR-0008 tras
revisión. Esquema/grants/appender/lectura v2 implementados y probados localmente;
ver SESSION_03_PERSISTENCE_REVIEW. R01 sigue abierto: 121 integraciones de
almacenamiento/regresión no equivalen a crash suite de worker. Revisión humana de
entrada satisfecha; cierre humano global S03 y CI/scans/recovery actuales pendientes.
Los párrafos de arranque siguientes conservan su estado histórico.

Petición de inicio recibida; [contratos y decisiones para revisión](../../specs/003-workflows/contracts.md)
y ADR-0008 preparados. Revisión humana pendiente antes del motor. R01 sigue ABIERTO:
schemas/golden/negativos no prueban durabilidad, fencing ni cancelación real S03.
R02/R14 mantienen gates S05/S06; worker local no realiza efectos externos.
R11 exige privacidad/retención antes de datos reales. No GO S04/producción.
Estado técnico S02 limitado al SHA de la sección siguiente, sin herencia al árbol nuevo.

## Estado vigente R15/R17 — cierre de 660f7d3

R17 / alta: **RESUELTO TÉCNICAMENTE PARA EL SHA**
660f7d31170de2d8ecb80ddd0bbf7f4c21e8eb20. CI 39898182916 y harness 39898182820
SUCCESS; jobs, SHA, artefacto, scans, PG fresco y recovery contrastados en
[SESSION_02_CLOSURE](SESSION_02_CLOSURE.md). Dueño autor, T02-07/08/AC02-08.
El bloqueo remoto de S02 queda resuelto; no implica aceptación humana ni autoriza
S03. Si cambian revisión/imágenes o fallan gates, reevaluar/reabrir para ese build.
La causa exacta de los scans incompletos de b221037 sigue sin stderr remoto.

R15 / alta: **MITIGADO TÉCNICAMENTE EN EL BUILD VALIDADO**, no eliminado como riesgo
continuo. Tres scans remotos con 0 HIGH/CRITICAL, identidades y reportes válidos.
Derivada Keycloak/Temurin/Alpine musl solo linux/amd64; no certificación de proveedor,
ni cobertura completa garantizada para JRE en archivo. Autor mantiene CA/JVM,
digests y revalidación de cada cambio; ADR-0007 vigente. Sin excepciones de CVE.

Revisión y aceptación humana de riesgos PENDIENTES; no hay acta que las acredite.
La autorización de push no las sustituye. No validación empresarial ni readiness
de producción; IdP corporativo, auditoría independiente, DR/HA y ancla externa
siguen pendientes. R01/R02/R14 conservan sus gates futuros. Los apartados S02
inferiores son históricos y conservan sus resultados originales.

| ID / prioridad | Riesgo, impacto y alternativas | Mitigación / dueño / gate |
|---|---|---|
| R01 / crítica | Motor propio introduce carreras/pérdida; Temporal reduce código a cambio de servicio extra | Flujo lineal, suite crash/fence/PG; autor S03, NO-GO S04 si falla |
| R02 / crítica | Efecto remoto ambiguo y duplicados tras caída | Intent único, operation_id durable externo, UNKNOWN/cuarentena; autor S05/S06 |
| R03 / alta | Docker daemon no disponible; integración S02 no ejecutable ahora | Iniciar entorno al solicitar S02 o Linux CI; autor antes T02-04; no sustituir por fake |
| R04 / alta | IdP de lab/provisión y grants aún no construidos | Keycloak recomendado, config repetible y negativos; IdP corporativo alternativa; autor T02-02 |
| R05 / alta | Hash audit local no resiste DB admin; canonicalización incorrecta rompe integridad | SQL canonicalizer con golden bytes, roles; ancla externa S08; autor T02-04/S08 |
| R06 / crítica | Privilegios/red WireGuard contaminan host o verifier comparte fallo | VM dedicada, cliente separado y servicio con credencial mínima; autor S06; no privileged general |
| R07 / alta | Proveedor LLM/región/retención/coste sin elegir | Un adapter, revisión de datos/contrato y budget antes de enviar; autor + privacidad S04 |
| R08 / alta | ACL RAG/caches revelan documentos internos | ACL previo ranking y revocación, tests negativos; autor S04 |
| R09 / alta | Ocho sesiones no bastan con UI/ingestión amplias | Un vertical, un formato, una mutación; reducir pantallas antes de seguridad; autor revisión S03 y S06 |
| R10 / alta | Host/PG SPOF; SLO/RPO solo hipótesis | Backup externo+WAL/restore real; HA futura por ADR; autor S08; no anunciar disponibilidad medida |
| R11 / alta | Ámbito legal/tenant desconocido | Single-tenant, sintéticos, evaluación caso/rol/contratos; autor + privacidad antes piloto externo |
| R12 / media | Spec Kit no instalado, compatibilidad solo declarada | SDD stdlib usable; opcional scratch pin 1.2.3 sin overwrite; autor cuando aporte valor |
| R13 / media | Mermaid no renderizado y checks no prueban semántica | Revisión humana; render toolchain fijada S02; autor antes publicar diagramas |
| R14 / alta | Worker antiguo puede ejecutar después de revoke/cancel tras envío | Revalidar bajo locks antes dispatch; efecto ya enviado se reconcilia, no se promete revocación física; autor S05 |

## Actualización S02 — 2026-10-23

R03 resuelto para el laboratorio: Docker responde, PG18/Keycloak reales y suites
Windows/Linux ejecutadas. R04 resuelto en lab con PKCE, provisión y grants locales;
IdP corporativo continúa pendiente. R05: paridad SQL/Python, permisos y tampering
probados; administrador DB y truncado total requieren ancla externa S08.

R15 / alta: CVE en imágenes/dependencias de runtime. Scanner de imágenes fijado,
sin excepción para altos/críticos; imagen PG derivada sin gosu vulnerable y sin root.
Gate supply FAIL: Keycloak tiene CVE-2026-114406 crítico y CVE-2026-91415 alto;
PG y API finales pasan. No se ha validado una imagen de IdP reparada. Dueño autor T02-07;
ver SESSION_02_REVIEW para veredicto efectivo. R16 / media: host compartido con
memoria limitada; timeout de escritura corregido a 5 s manteniendo health 1 s y
prueba de 20 appends. No es un benchmark de capacidad ni un SLO de producción.
R13 sigue pendiente antes de publicar diagramas; no bloquea el runtime S02 y no
se afirma render visual de Mermaid. La auditoría externa no se ha ejecutado;
la actualización siguiente registra los resultados reales de Actions.

## Remediación de seguridad S02 — 2026-10-23

R15: REMEDIADO LOCALMENTE mediante la derivada de ADR-0007, sin excepción.
Imagen oficial sin corregir; derivada Debian rechazada por otros CVE. Alpine/Temurin
con inputs fijados, inventario de ambos almacenes, scan final sin altos/críticos,
176 tests Windows/Linux, PG fresco y recovery PASS. El autor mantiene parches y
procedencia; debe revalidar cada cambio. No es certificación del proveedor para musl.

R17 / alta, ABIERTO: aceptación remota bloqueada. La corrección publicada b221037
tiene CI 39888916474 FAIL: quality Windows/Ubuntu, 50 integraciones, PG fresco y
recovery pasan; los tres scans son BLOCKED sin informe. Logs privados del scanner
no incluidos en el artefacto; no se puede afirmar su causa remota exacta. Escritura
denegada con UID 10001 y bind mounts POSIX 0755 reproducida localmente, causa
plausible. Dueño autor, T02-07/AC02-08: corregir sin elevar privilegios ni rebajar scanner,
conservar diagnóstico y aprobar todos los jobs/gates del mismo SHA antes de GO S03.
R15 continúa remediado solo localmente, sin validación supply del build remoto.
No aprobar scans incompletos ni reutilizar PASS anteriores del checkout.
Informe/evidencia: SESSION_02_CLOSURE y artifacts/session-02/closure-b221037.

Decisiones de aislamiento/entrega/autorización están fijadas en ADR. IdP/proveedor/lab
son elecciones provisionales con gates explícitos; no se necesita inventar requisitos
de cliente para completar S01. Validación de uso empresarial queda fuera de esta entrega.

## Remediación local del scanner CI — 2026-10-23

R17 ABIERTO. Defecto UID/mount POSIX reproducido, causa remota exacta aún incierta.
Aislamiento y diagnóstico corregidos, probes y suites reales Windows/Linux; ver
SESSION_02_SCANNER_REMEDIATION y acceptance/manifest en scanner-remediation.
La CI anterior sigue FAIL y este árbol no está publicado. CI satisfactoria del
nuevo commit, revisión humana y otra petición siguen siendo gates para S03.
R15 continúa con mantenimiento a cargo del autor y límites de ADR-0007; no
excepciones de CVE. Docker Desktop sintetiza permisos POSIX: su probe real es
obligatorio, no se traslada un PASS Windows a Ubuntu. DB grandes requieren disco
local y red; errores de descarga/runtime/timeout mantienen BLOCKED.
