# OpsPilot AI

Enterprise Agentic AI Operations Platform. Base de arquitectura de la sesión **01/08**,
22 de octubre de 2026. **No hay API, agente, frontend ni infraestructura del producto
implementados.** El código presente pertenece exclusivamente al engineering harness.

OpsPilot investigará incidencias IT con documentación autorizada y evidencias,
propondrá acciones y ejecutará un catálogo cerrado bajo políticas y supervisión.
El primer vertical será una incidencia VPN reproducible en un laboratorio aislado.
Una ejecución técnica correcta no demuestra la resolución del ticket.

## Estado y lectura

| Elemento | Estado real |
|---|---|
| Checkouts CopilotDrive vecinos | EXISTENTE, ajeno a OpsPilot; sin cambios |
| Arquitectura, contratos y roadmap | PROPUESTO, documentado para revisión |
| Harness documental y CI de sesión 01 | IMPLEMENTADO; resultados en la revisión |
| Producto y controles de runtime | PROPUESTO, no desplegado ni validado |
| IdP, proveedor LLM y VPN de laboratorio | Selección provisional; gates antes de integración |

Empieza por [alcance](docs/product/SCOPE.md), [arquitectura](docs/architecture/ARCHITECTURE.md),
[roadmap](docs/roadmap/ROADMAP_8_SESSIONS.md) y [revisión con resultados](docs/roadmap/SESSION_01_REVIEW.md).
El [handoff](docs/roadmap/HANDOFF.md) conserva contexto entre sesiones.
Las [fuentes](docs/engineering/SOURCES.md) separan investigación externa de evidencia local.

## Uso reproducible actual

Requiere Python >=3.11 (probado aquí con 3.13.14) y Git. Sin dependencias Python externas.
Desde esta carpeta, tanto PowerShell como WSL2/Linux:

```text
python scripts/dev.py doctor
python scripts/dev.py check
python scripts/dev.py test
```

En WSL/Linux usar `python3` si `python` no está disponible; el mismo harness se ha
ejecutado aquí con Python 3.12.3 en Ubuntu/WSL2 y Python 3.13.14 en Windows.

`doctor` es pasivo. `check` verifica documentación, trazabilidad, contratos y coherencia
del modelo de estados; no acredita comportamiento distribuido. `test` ejecuta pruebas
negativas del validador. Los comandos `install`, `infra`, `migrate`, `up`, `logs`, `eval`
están reservados: hoy fallan explícitamente con código 2 y enlazan su hito, sin simular éxito.
No iniciar Docker ni desplegar nada durante sesión 01.

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
scripts/                  comprobaciones del harness, sin lógica de negocio
tests/harness/            pruebas del harness
.github/workflows/        CI de sesión 01 (no ejecutada remotamente)
```

Este repositorio se creó dentro de un workspace que no era Git, sin importar ni
modificar los dos checkouts Android/Python existentes. El 23 de octubre de 2026 el
autor trasladó el proyecto a `C:\Users\manul\OneDrive\Escritorio\opspilot-ai` y autorizó
su primer commit y push a [AlmanInDaHouse/OpsPilot-AI](https://github.com/AlmanInDaHouse/OpsPilot-AI),
en la rama `main`. El estado histórico de la sesión 01 se conserva en sus evidencias.
Esta publicación del repositorio no implica release, despliegue ni inicio de sesión 02.
