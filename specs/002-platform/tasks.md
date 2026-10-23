# 002-platform — tareas secuenciadas

Estado S02: implementación y suites funcionales ejecutadas; T02-07 no aceptada por
scan de Keycloak FAIL. No se declara una cadena completa aceptada mientras falle ese
gate. Ver [revisión](../../docs/roadmap/SESSION_02_REVIEW.md) y ejecución abajo.

| ID | Dependencia | Cambio acotado y archivos previstos | Tests/evidencia obligatoria |
|---|---|---|---|
| T02-01 | S01 GO | pyproject/uv.lock, Python pin, DX, versiones/digests y Compose PG18+Keycloak | doctor, lock frozen, compose config, provenance y scans iniciales |
| T02-02 | T02-01 | Revisar OpenAPI, provisión IdP/roles y algoritmo audit exacto; fixtures de contratos en tests | TEST-02-CONTRACT, golden bytes, decisión de trust boundary |
| T02-03 | T02-02 | src/opspilot shared/domain/ports, composition root y architecture checks | TEST-02-ARCH con imports relativos/ciclos/infra negativos |
| T02-04 | T02-03 | migrations + adapters/postgres: principals/grants/audit_streams/events, roles/UoW/appender | TEST-02-MIGRATE/AUDIT, rollback y 20 appends concurrentes reales |
| T02-05 | T02-04 | adapters/oidc + identity/application: JWT/JWKS y autorización local | TEST-02-AUTH unit+IdP real, SSRF/kid/expiry/revoke |
| T02-06 | T02-05 | entrypoints/api: live/ready/me/audit, DTO error redacted, logs/request IDs | TEST-02-CONTRACT/AUTH y DB caída/schema inválido |
| T02-07 | T02-06 | CI Linux integración + gates Python, roles imagen sin root/secretos | TEST-02-SUPPLY + check/test completos y reportes redacted |
| T02-08 | T02-07 | Actualizar traceability, handoff y revisión S02/DoD/riesgos | AC02-01..10, diff review y GO/NO-GO explícito |

Cada tarea cambia solo componentes indicados. Si una decisión requiere nuevo ADR,
actualizar spec antes de implementar. Código/test/evidencia se rellenan con rutas
existentes al pasar a IMPLEMENTADO/PROBADO; no inventar reportes futuros.

## Estado y trazabilidad de ejecución

| Tarea | Estado real | Código/test/evidencia existente |
|---|---|---|
| T02-01 | IMPLEMENTADO, gate imagen IdP no aceptado | pyproject.toml, uv.lock, Dockerfile, infra/compose.yaml; scans de imágenes en artifacts/session-02 |
| T02-02 | PROBADO | ADR-0006, contracts, audit/domain/envelope.py; tests/unit/test_canonical.py, tests/contract/test_api.py, integración SQL parity |
| T02-03 | PROBADO | src/opspilot y scripts/check_architecture.py; tests/architecture/test_layers.py; tests-windows.xml |
| T02-04 | PROBADO | migrations, adapters/postgres; tests/integration/test_audit.py; tests-windows.xml, integration-linux.xml, fresh-postgres.json, recovery.json |
| T02-05 | PROBADO funcional, dependencia vulnerable | adapters/oidc, identity/application; tests/unit/test_oidc.py, test_identity/test_idp_security de integración; XML Windows/Linux |
| T02-06 | PROBADO | entrypoints/api y DTO; tests/contract/test_api.py, test_entrypoints/test_identity reales; XML y recovery.json |
| T02-07 | IMPLEMENTADO / NO-GO | workflows/harness+platform, scripts/dev.py/check_secrets.py/scan_images.py; Bandit/pip-audit y scans; keycloak-cves.json FAIL |
| T02-08 | IMPLEMENTADO, cierre NO-GO | traceability.json, checklist, SESSION_02_REVIEW, HANDOFF; manifest/evidencia S02 |

Rutas fuente abreviadas relativas a src/opspilot, tests o .github donde corresponde;
las rutas máquina exactas están en traceability.json. No CI remota ni aprobación
humana de riesgos declaradas. T02-07 debe repetirse tras corregir dependencia.
