# 003-workflows — tareas y estado

S03 iniciada por petición explícita. El autor aprueba cierre/riesgos S02 y T03-01/
ADR-0008 tras revisión. Nueva petición explícita autoriza exclusivamente T03-03.
Intake implementado; T03-04..08 pendientes, sin worker.
Fuente de criterios: [SESSION_03_SPEC](../../docs/roadmap/SESSION_03_SPEC.md).

| ID | Dependencia | Cambio acotado | Verificación necesaria |
|---|---|---|---|
| T03-01 | GO técnico S02 + revisión/autorización humana | Contratos/ADR-0008 aprobados por autor para implementación | Schemas/golden/negativos probados; no aceptación de auth HTTP/durabilidad S03 |
| T03-02 | T03-01 | IMPLEMENTADO/PROBADO local: [persistencia](persistence.md), 0002, constraints/índices, rol worker, appender y lector v2 | AC03-08 local: vacío/N-1/rollback/grants; regresión 482 PASS, CI final pendiente T03-07 |
| T03-03 | T03-02 | IMPLEMENTADO/PROBADO local: [intake](intake.md), POST + CreateIncident + idempotency/UoW/audit atómicos | [Revisión y resultados reales](../../docs/roadmap/SESSION_03_INTAKE_REVIEW.md): AC03-01/02, 20 requests, dos API, kills, commit PG diferido fallido; 567 PASS/OS, 155 integraciones/OS |
| T03-04 | T03-03 | Lectura autorizada y cancel CAS | AC03-03/06/09, fuga/roles/revoke |
| T03-05 | T03-02/03 | Job store y worker lineal, paso local real | AC03-04/05, leases/fences y dos procesos |
| T03-06 | T03-04/05 | Reclaim, retry, deadline y definición versionada | AC03-04/05/06/07/09, kill points y 100 jobs |
| T03-07 | T03-06 | Regresión completa y CI con evidencia saneada | AC03-10 y todos los gates S02 |
| T03-08 | T03-07 | Revisión humana, riesgos, evidencia y handoff | AC03-01..10 y GO/NO-GO S04 documentado |

Sin marcado PROBADO por existir esta tabla. Completar code/test/evidence en
trazabilidad solo con archivos y resultados reales. Si cambian límites de confianza,
registrar ADR y cerrar contratos antes de continuar.
