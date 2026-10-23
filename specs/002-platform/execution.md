# Plan de ejecución S02 — 2026-10-23

Repo verificado C:/Users/manul/OneDrive/Escritorio/opspilot-ai; HEAD 43e1d28, limpio.
S01 baseline check PASS y 23 tests PASS. Windows/Python 3.13.14, uv 0.11.13;
Docker 29.1.2 responde en WSL2, 64 contenedores ajenos en marcha: sin reinicios,
limpieza ni cambios sobre ellos. 12 CPU / 7.65 GiB en Docker, host con memoria
disponible limitada: lab con límites explícitos. Puertos lab 55432/58080/58000.

REQ-PLAT-01 → SESSION_02_SPEC/ADR-0006/API_CONTRACTS → T02-01/02/03/05/06/07/08 →
identity, adapters/oidc, entrypoints/api → TEST-02-AUTH/CONTRACT/ARCH → artifacts/session-02.
REQ-PLAT-02 → SESSION_02_SPEC/ADR-0006/DATA_MODEL → T02-01/02/03/04/06/07/08 →
audit, adapters/postgres, migrations → TEST-02-AUDIT/MIGRATE/CONTRACT → artifacts/session-02.
REQ-HAR-01 y CT-10: conservar checker/23 negativos, activar check/test y comandos
S02; eval sigue NOT_IMPLEMENTED. TEST-02-SUPPLY bloquea ante CVE no resuelto.

Orden y verificaciones: A versiones/lock/contratos; B paquetes/config/arquitectura;
C migración/roles/paridad SQL real; D UoW/provisión/concurrencia/rollback; E JWT/JWKS
y PKCE real; F HTTP contratos/negativos; G logs/correlación/redaction; H Compose,
restart, CI Linux local y scans; I revisión/evidencia/handoff. Corregir fallos antes
de cerrar cada tarea. Alcance medible AC02-01..10, sin reducir gates por entorno.

Decisiones cerradas en ADR-0006 antes de código. Pendientes de ejecución: disponibilidad
de imágenes exactas y scan CVE, memoria del host, integración Linux. CI GitHub remota
no se ejecutará porque push no está autorizado. Eso se distinguirá de CI Linux local.
