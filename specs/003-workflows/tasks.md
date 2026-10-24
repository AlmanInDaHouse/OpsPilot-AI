# 003-workflows — tareas y estado

S03 iniciada por petición explícita. El autor aprueba cierre/riesgos S02 y T03-01/
ADR-0008 tras revisión. T03-04 preservada; nueva petición 2026-10-24 autoriza
exclusivamente T03-05 local.
Intake, acceso/cancelación y worker local implementados; T03-06..08 pendientes.
Fuente de criterios: [SESSION_03_SPEC](../../docs/roadmap/SESSION_03_SPEC.md).

| ID | Dependencia | Cambio acotado | Verificación necesaria |
|---|---|---|---|
| T03-01 | GO técnico S02 + revisión/autorización humana | Contratos/ADR-0008 aprobados por autor para implementación | Schemas/golden/negativos probados; no aceptación de auth HTTP/durabilidad S03 |
| T03-02 | T03-01 | IMPLEMENTADO/PROBADO local: [persistencia](persistence.md), 0002, constraints/índices, rol worker, appender y lector v2 | AC03-08 local: vacío/N-1/rollback/grants; regresión 482 PASS, CI final pendiente T03-07 |
| T03-03 | T03-02 | IMPLEMENTADO/PROBADO local: [intake](intake.md), POST + CreateIncident + idempotency/UoW/audit atómicos | [Revisión y resultados reales](../../docs/roadmap/SESSION_03_INTAKE_REVIEW.md): AC03-01/02, 20 requests, dos API, kills, commit PG diferido fallido; 567 PASS/OS, 155 integraciones/OS |
| T03-04 | T03-03 | IMPLEMENTADO/PROBADO funcionalmente: [lectura autorizada y cancel CAS](access-cancel.md), UoW/audit v2 existentes, sin worker | [Revisión y evidencia](../../docs/roadmap/SESSION_03_ACCESS_CANCEL_REVIEW.md): 666 PASS/OS, 214 integraciones/OS; AC03-03/09 del alcance, AC03-06 parcial API/SQL; NO-GO T03-05 por scan de imágenes |
| T03-05 | T03-02/03/04 + gate hotfix PG | IMPLEMENTADO/PROBADO local: [worker](worker.md), Job Store PG, claim/heartbeat/CAS/evidence/audit reales | [Revisión/evidencia actual](../../docs/roadmap/SESSION_03_WORKER_REVIEW.md): 715 PASS/OS, 252 integraciones/OS; dos procesos/100 jobs, checks/scans/fresh/recovery PASS; AC03-04/05/06 parciales |
| T03-06 | T03-04/05 | Reclaim, retry, deadline y definición versionada | AC03-04/05/06/07/09, kill points y 100 jobs |
| T03-07 | T03-06 | Regresión completa y CI con evidencia saneada | AC03-10 y todos los gates S02 |
| T03-08 | T03-07 | Revisión humana, riesgos, evidencia y handoff | AC03-01..10 y GO/NO-GO S04 documentado |

Sin marcado PROBADO por existir esta tabla. Completar code/test/evidence en
trazabilidad solo con archivos y resultados reales. Si cambian límites de confianza,
registrar ADR y cerrar contratos antes de continuar.

Hotfix previo a T03-05: [spec PostgreSQL/Brotli](postgres-security.md), regresión
AC03-10 acotada a la imagen y controles existentes. Paquete firmado 1.2.1-r0 instalado,
Tres scans finales PASS, cero HIGH/CRITICAL e IDs actuales verificados; 666 PASS/OS
y checks/recovery PASS. GO técnico LOCAL para preparar T03-05 bajo nueva petición.
[Revisión actual](../../docs/roadmap/SESSION_03_POSTGRES_SECURITY_REVIEW.md).
La tabla T03-04 conserva el finding del snapshot anterior; no es el inventario
actual. No iniciar worker con gates pendientes ni declarar S03/S04 aprobadas.
