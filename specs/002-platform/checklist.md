# 002-platform — checklist de entrada y salida

- [ ] Autor revisó S01 y alcance exclusivo de plataforma.
- [x] PG18 e IdP reales disponibles; secretos de laboratorio fuera de Git.
- [x] Contratos, grants y canonicalización audit cerrados y probados.
- [x] AC02-01..10 técnicos satisfechos para 660f7d3, con negativos/concurrencia y gates supply remotos PASS, sin skips.
- [x] Format/lint/types/unit/contract/architecture/integration/security/SCA pasan para 660f7d3.
- [x] App sin DDL ni edición de audit; no endpoints de negocio ni mocks en producto.
- [x] Evidencia identifica entorno/versiones/lock/resultado y fallos pendientes.
- [x] Handoff y trazabilidad coinciden con archivos y resultados reales.
- [x] GO técnico S02 registrado para 660f7d3; S03 solo especificada, sin autorización de implementar/publicar.
- [ ] Revisión humana del diff y aceptación de riesgos residuales documentadas.

GO técnico vigente: [cierre 660f7d3](../../docs/roadmap/SESSION_02_CLOSURE.md);
[aceptación](../../artifacts/session-02/closure-660f7d3/acceptance.json). No aceptación
humana ni validación empresarial/producción.

Histórico NO-GO: CI remota de b221037 FAIL por tres scans BLOCKED; PG fresco y recovery
sí pasan. La derivada mantenida supera los gates locales anteriores;
ver SESSION_02_CLOSURE y artifacts/session-02/closure-b221037/acceptance.json.
El autor autorizó la ejecución S02; la revisión humana del diff/riesgos no se da por
realizada. No marcar todas las casillas ni continuar a S03 por tener tests funcionales
verdes. Evidencias en SESSION_02_REVIEW y artifacts/session-02.
