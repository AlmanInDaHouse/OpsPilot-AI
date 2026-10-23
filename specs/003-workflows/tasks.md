# 003-workflows — tareas propuestas

Todas PROPUESTAS. Ninguna autoriza implementación en este turno.
Fuente de criterios: [SESSION_03_SPEC](../../docs/roadmap/SESSION_03_SPEC.md).

| ID | Dependencia | Cambio futuro acotado | Verificación necesaria |
|---|---|---|---|
| T03-01 | GO técnico S02 + revisión/autorización humana | Cerrar OpenAPI, evento/appender, step snapshot y RBAC | AC03-03/09; ejemplos y negativos revisados |
| T03-02 | T03-01 | Migración incremental, constraints/índices y rol worker | AC03-08, N-1 y grants reales |
| T03-03 | T03-02 | CreateIncident + idempotency/UoW/audit atómicos | AC03-01/02, 20 carreras y commit fallido |
| T03-04 | T03-03 | Lectura autorizada y cancel CAS | AC03-03/06/09, fuga/roles/revoke |
| T03-05 | T03-02/03 | Job store y worker lineal, paso local real | AC03-04/05, leases/fences y dos procesos |
| T03-06 | T03-04/05 | Reclaim, retry, deadline y definición versionada | AC03-04/05/06/07/09, kill points y 100 jobs |
| T03-07 | T03-06 | Regresión completa y CI con evidencia saneada | AC03-10 y todos los gates S02 |
| T03-08 | T03-07 | Revisión humana, riesgos, evidencia y handoff | AC03-01..10 y GO/NO-GO S04 documentado |

Sin marcado PROBADO por existir esta tabla. Completar code/test/evidence en
trazabilidad solo con archivos y resultados reales. Si cambian límites de confianza,
registrar ADR y cerrar contratos antes de continuar.
