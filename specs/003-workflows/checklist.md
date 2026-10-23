# 003-workflows — checklist propuesto

- [x] Base técnica S02 identificada: SHA 660f7d3 y cierre remoto verificable.
- [x] Alcance, exclusiones, tareas y AC03 propuestos documentados.
- [ ] Revisión humana de cierre S02/riesgos y aceptación documentadas.
- [ ] Nueva petición autoriza implementar S03.
- [ ] OpenAPI/eventos/appender/snapshot y RBAC revisados antes de código.
- [ ] Migración N-1 y rol worker aprobados y probados con PG real.
- [ ] AC03-01..10 ejecutados; dos workers, 100 jobs y kill points reales.
- [ ] Gates S02 preservados; CI satisfactoria del SHA final S03.
- [ ] Evidencias, riesgos y aceptación humana de S03 registradas; GO/NO-GO S04.

Estado: PROPUESTO. No orquestador, migraciones ni tests S03 implementados.
GO técnico S02 no equivale a readiness de producción ni a autorización de S04.
