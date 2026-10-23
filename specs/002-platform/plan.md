# 002-platform — plan técnico

Estado: EJECUTADO; NO-GO S03 por CVE del IdP, no por ausencia de integración.
Diseño rector: [arquitectura](../../docs/architecture/ARCHITECTURE.md),
[ADR-0005](../../docs/decisions/0005-platform-stack.md) y [spec](spec.md).

Secuencia: entorno/versiones→contratos→paquetes/CI→migraciones/roles/UoW→identidad→API→
integración/scans→revisión/evidencia. No invertir contrato e implementación.
Primero demostrar en PG real appender/roles/canonicalización; después auth e interfaz.
No introducir base vectorial, broker ni worker. IdP en red separada con configuración
de realm/client PKCE exportable sin claves/secretos. PG y Keycloak solo loopback/red
de test. Compose de integración usa proyecto/volúmenes temporales con nombres únicos.

El conjunto exacto de paquetes/dependencias/AC está en SESSION_02_SPEC, fuente única.
Tests unit usan puertos; integration usa PG18 e IdP reales; contratos se validan con
implementación y schemas; arquitectura usa fixtures negativos. Rollback de esquema
destructivo prohibido; errores de inicialización deben dejar sistema no-ready.

Impacto seguridad: CT-01/02/10 y TH-04/11/12/14. Antes de código cerrar política de
provisión de usuarios, rol de función audit y bytes canónicos. Las decisiones de
proveedor LLM y VPN no bloquean S02; IdP/PG sí. Evidencia y aprobación de aceptación
por autor; no se presenta GO documental como validación empresarial.
