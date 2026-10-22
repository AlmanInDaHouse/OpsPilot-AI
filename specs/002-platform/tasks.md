# 002-platform — tareas secuenciadas

Estado de todas: PROPUESTO; ninguna se ejecuta en sesión 01.

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
