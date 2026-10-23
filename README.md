# OpsPilot AI

Enterprise Agentic AI Operations Platform. Fundación backend de la sesión **02/08**,
23 de octubre de 2026. API FastAPI, OIDC, RBAC local, PostgreSQL 18, migraciones y
auditoría transaccional implementados. Resultados y GO/NO-GO en
[revisión S02](docs/roadmap/SESSION_02_REVIEW.md). Tickets/workflows se reservan a S03;
no hay IA, VPN ni frontend implementados.

OpsPilot investigará incidencias IT con documentación autorizada y evidencias,
propondrá acciones y ejecutará un catálogo cerrado bajo políticas y supervisión.
El primer vertical será una incidencia VPN reproducible en un laboratorio aislado.
Una ejecución técnica correcta no demuestra la resolución del ticket.

## Estado y lectura

| Elemento | Estado real |
|---|---|
| Checkouts CopilotDrive vecinos | EXISTENTE, ajeno a OpsPilot; sin cambios |
| Arquitectura, contratos y roadmap | Diseño versionado; S02 implementada, hitos posteriores propuestos |
| Harness y CI | Harness extendido y probado localmente; workflows sin ejecutar en GitHub |
| API/identidad/audit | IMPLEMENTADO y probado con PG/Keycloak reales; ver gates S02 |
| LLM y VPN | PROPUESTO; fuera de S02, sin conexiones ni efectos IT |

Empieza por [alcance](docs/product/SCOPE.md), [arquitectura](docs/architecture/ARCHITECTURE.md),
[roadmap](docs/roadmap/ROADMAP_8_SESSIONS.md) y [revisión con resultados](docs/roadmap/SESSION_01_REVIEW.md).
El [handoff](docs/roadmap/HANDOFF.md) conserva contexto entre sesiones.
Las [fuentes](docs/engineering/SOURCES.md) separan investigación externa de evidencia local.

## Uso reproducible actual

Requiere Python 3.13.14, Git, uv 0.11.13 y Docker Compose/Engine Linux para integración.
Desde esta carpeta en PowerShell (Linux en checkout/venv separados):

```text
python scripts/dev.py doctor
python scripts/dev.py install
python scripts/dev.py infra
python scripts/dev.py up
python scripts/dev.py check
python scripts/dev.py test
python scripts/dev.py stop
```

En WSL/Linux usar `python3` si hace falta; el producto se ejecuta con `uv`/Python 3.13.
No compartir `.venv` entre Windows y WSL. Docker Desktop usa WSL2; la suite de
integración también se ejecuta dentro de una imagen Linux de tests sin root.

`doctor` es pasivo. `check` conserva el checker documental y añade lint, Markdown,
tipos, arquitectura y scans. `test` requiere PG/IdP reales; ausencia es fallo, no skip.
`test --suite local` sirve para trabajo sin infraestructura y anuncia su alcance.
`infra` genera secretos aleatorios ignorados, construye PG sin root, migra y provisiona
Keycloak local. `up` construye/arranca la API; `stop` conserva volúmenes. Solo `eval`
sigue con código 2 NOT_IMPLEMENTED hasta S04. [Runbook](docs/engineering/PLATFORM_RUNBOOK.md).

Endpoints: `GET /health/live`, `GET /health/ready`, `GET /v1/me`, `GET /v1/audit-events`.
API loopback 59000; IdP 59080; PG 59432. API usa rol restringido y no migra al arrancar.
El contrato [OpenAPI](contracts/platform.openapi.json) es independiente de los DTO y
se verifica con HTTP. Compose es laboratorio sintético: no es un despliegue empresarial.

## Organización

```text
AGENTS.md                 mapa para Codex
docs/product/             PRD, alcance e hipótesis SLO
docs/architecture/        diseño, diagramas, datos, API, motor y runtime
docs/security/            amenazas, controles y aplicabilidad
docs/engineering/         constitución, SDD, gates, tests y fuentes
docs/decisions/           decisiones ADR y alternativas
docs/roadmap/             ocho hitos, revisión, siguiente especificación y handoff
specs/                    plantilla, trazabilidad y paquete de sesión 02
contracts/                OpenAPI, eventos, propuestas y estados objetivo
src/opspilot/             shared, identity, audit, adapters y entrypoints
migrations/               Alembic + SQL de tablas, permisos y appender
infra/                    Compose, imagen PG endurecida y realm sin secretos
scripts/                  harness, provisión de lab y verificaciones operativas
tests/harness/            pruebas del harness
.github/workflows/        harness preservado y gates S02 (sin ejecución remota)
```

Este repositorio se creó dentro de un workspace que no era Git, sin importar ni
modificar los dos checkouts Android/Python existentes. El 23 de octubre de 2026 el
autor trasladó el proyecto a `C:\Users\manul\OneDrive\Escritorio\opspilot-ai` y autorizó
su primer commit y push a [AlmanInDaHouse/OpsPilot-AI](https://github.com/AlmanInDaHouse/OpsPilot-AI),
en la rama `main`. El estado histórico de la sesión 01 se conserva en sus evidencias.
Esta publicación del repositorio no implica release, despliegue ni inicio de sesión 02.
