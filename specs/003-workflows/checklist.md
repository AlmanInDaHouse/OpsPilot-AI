# 003-workflows — checklist de arranque

- [x] Base técnica S02 identificada: SHA 660f7d3 y cierre remoto verificable.
- [x] Alcance, exclusiones, tareas y AC03 propuestos documentados.
- [x] Revisión humana de cierre S02/riesgos y aceptación documentadas en persistence.md.
- [x] Nueva petición explícita autoriza arrancar S03; registrada en start.md.
- [x] Paquete de contratos/golden/negativos preparado para revisión T03-01.
- [x] OpenAPI/eventos/appender/snapshot y RBAC aprobados por autor antes de código.
- [x] Diseño de migración/rol worker autorizado; implementación N-1/grants probados con PG real.
- [x] T03-03 implementado: intake estricto, PK idempotente, step/job/audit/respuesta en UoW.
- [x] AC03-01/02 locales: fallos SQL/commit PG real, 20 requests y recuperación de procesos API.
- [x] Replays con revoke/disable y roles sin operator denegados con Keycloak real.
- [x] T03-04 implementado: GET autorizados, ETag/If-Match y cancelación CAS/audit/jobs.
- [x] Carreras API/SQL, rollback/COMMIT y crashes HTTP T03-04 con PG18/Keycloak reales.
- [x] Regresión T03-04: 666 PASS/OS, 214 integraciones/OS; check y dependencias PASS.
- [x] Hotfix PG: Brotli 1.2.1-r0 oficial firmado; PG fresco, datos, recovery y 666 PASS/OS.
- [x] Gate imágenes hotfix: PG/Keycloak/API finales PASS, cero HIGH/CRITICAL e IDs verificados.
- [x] GO técnico LOCAL para preparar T03-05 según SESSION_03_POSTGRES_SECURITY_REVIEW; sin inicio automático.
- [x] Nueva petición T03-05 y spec acotada; worker independiente y Job Store PG implementados.
- [x] Claim separado, lease/heartbeat PG, fence/CAS/cancel y resultado/audit atómicos probados localmente.
- [x] Dos procesos reales/100 jobs y rechazos obsoletos en focused; regresión final en worker/verification.json.
- [x] T03-05 local: 715 PASS/OS, 252 integraciones/OS; checks/harness, tres scans, fresh/recovery nuevos PASS.
- [ ] AC03-06 completo con claim/completion del worker real T03-05/06.
- [x] T03-06 local: reclaim/retry/deadline/accounting y commit incierto, 755 PASS/OS y 292 integraciones reales/OS; sin aceptación global S03.
- [x] T03-06 gates locales: check Windows/Linux, PG fresco, recovery y tres scans finales PASS; GO local para preparar T03-07, sin iniciarlo.
- [ ] AC03-01..10 ejecutados; dos workers, 100 jobs y kill points reales.
- [ ] Gates S02 preservados; CI satisfactoria del SHA final S03.
- [ ] Evidencias, riesgos y aceptación humana de S03 registradas; GO/NO-GO S04.

Estado: S03 en curso, T03-01 aprobada, T03-02/03/04 implementadas; gates T03-04 en su revisión.
Worker local T03-05 preservado; T03-06 implementa reclaim/retry/deadline/accounting
y commit incierto. Ver [revisión/gates](../../docs/roadmap/SESSION_03_RECOVERY_REVIEW.md)
para estado PROBADO y dictamen T03-07. No marcar aceptación global por código nuevo.
Cierre/CI/aceptación de S03 pendientes; gates actuales en SESSION_03_WORKER_REVIEW.
GO técnico S02 no equivale a readiness de producción ni a autorización de S04.
