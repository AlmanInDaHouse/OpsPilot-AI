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
- [ ] AC03-01..10 ejecutados; dos workers, 100 jobs y kill points reales.
- [ ] Gates S02 preservados; CI satisfactoria del SHA final S03.
- [ ] Evidencias, riesgos y aceptación humana de S03 registradas; GO/NO-GO S04.

Estado: S03 en curso, T03-01 aprobada, T03-02 y T03-03 implementadas/probadas localmente.
Sin worker ni crash suite de jobs S03. Cierre/CI/aceptación de S03 pendientes.
GO técnico S02 no equivale a readiness de producción ni a autorización de S04.
