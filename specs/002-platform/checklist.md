# 002-platform — checklist de entrada y salida

- [ ] Autor revisó S01 y alcance exclusivo de plataforma.
- [x] PG18 e IdP reales disponibles; secretos de laboratorio fuera de Git.
- [x] Contratos, grants y canonicalización audit cerrados y probados.
- [x] AC02-01..10 ejecutados, con negativos y concurrencia; AC02-08 falla supply, sin skips.
- [ ] Format/lint/types/unit/contract/architecture/integration/security/SCA pasan.
- [x] App sin DDL ni edición de audit; no endpoints de negocio ni mocks en producto.
- [x] Evidencia identifica entorno/versiones/lock/resultado y fallos pendientes.
- [x] Handoff y trazabilidad coinciden con archivos y resultados reales.
- [x] NO-GO S03 registrado; push/deploy no autorizado automáticamente.

NO-GO: Keycloak tiene 1 crítico y 1 alto sin corregir en la imagen seleccionada.
El autor autorizó la ejecución S02; la revisión humana del diff/riesgos no se da por
realizada. No marcar todas las casillas ni continuar a S03 por tener tests funcionales
verdes. Evidencias en SESSION_02_REVIEW y artifacts/session-02.
