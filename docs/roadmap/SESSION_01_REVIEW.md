# Sesión 01 — revisión técnica y evidencia

Estado: sesión 01 completada en su alcance documental/harness. Diseño de producto
PROPUESTO; harness IMPLEMENTADO y PROBADO. No hay funcionalidad de negocio ni
validación empresarial. Fecha de trabajo: 2026-10-22 Europe/Madrid.

## Reconocimiento inicial

Workspace `OpenCar-Copilot-MVP` no era Git. Contenía dos checkouts relacionados:
`opencar-copilot` en `feat/sprint11-real-mode-premium-ui`, HEAD `5006196`, limpio;
`sprint6-baseline`, worktree detached `2099b9d`, limpio. AGENTS y README de ambos
inspeccionados: producto Android CopilotDrive y prototipo Python/web, especificaciones
artesanales, Compose, CI Android/Python. No arquitectura OpsPilot previa encontrada.
Sus reglas no se importan al producto nuevo ni se alteraron archivos del producto ajeno.
Se creó repo local `opspilot-ai` en main, sin remoto ni commits.

Entorno observado: Windows build 26200; Python 3.13.14, Git 2.52.0.windows.1,
uv 0.11.13, Node 24.12.0, Docker CLI 29.1.2. WSL informa Ubuntu, versión 2.
Docker context desktop-linux; daemon no accesible (pipe no existe). specify/openspec/
pytest/ruff no estaban en PATH; uv sin tools instaladas. Skills visibles inspeccionadas
por nombres, sin Spec Kit. No instaladores remotos ejecutados. Fuentes upstream en SOURCES.
Ubuntu/WSL2 permitió ejecutar Python 3.12.3 y el harness; allí uv/node no aparecen en
PATH. T02-01 deberá preparar la toolchain de ese entorno si se elige para desarrollo.

## Autocrítica arquitectónica

Revisión por el mismo asistente adoptando perspectiva externa; no tercero independiente.

| Hallazgo | Corrección / decisión y residual |
|---|---|
| Riesgo de mezclar producto anterior con OpsPilot | Repo hermano independiente; checkouts originales preservados |
| Motor propio puede ser complejidad accidental | Solo secuencia lineal; NO-GO S03 ante crash suite; Temporal alternativa explícita |
| Lease no detiene llamada externa antigua | Intent único, operation_id externo y UNKNOWN/cuarentena; fencing local no promete exactly-once |
| Confusión estado de servicio vs ticket resuelto | Verifier cliente/túnel/tráfico y cierre humano separado del run |
| Approval replay y revoke/dispatch race | Snapshot immutable, nonce/TTL, locks/CAS y checks frescos; efecto ya enviado no es revocable físicamente |
| Hash chain no protege DB admin | Roles append-only y ancla fuera host S08; residual de administrador documentado |
| Outbox duplicaría jobs PG sin necesidad | Cola local ya transaccional; outbox solo para destino externo |
| Multitenancy sin pruebas sería promesa falsa | Single-tenant por DB/realm/red; compartido requiere ADR y RLS/ACL suites |
| SLO sin condiciones no comprobable | Carga/host/muestra/indicador definidos; todos son hipótesis |
| Infra y proveedor no disponibles | Gates por hito y decisiones provisionales con dueño; no mocks en producto |
| Check documental no es garantía runtime | Checks limitados, tests negativos y suites reales previstas; Mermaid aún sin render |
| Ocho sesiones pueden desbordarse | Recortar UI/ingestión/tools antes de persistencia/seguridad/recuperación |

## Resultados de ejecución

| Verificación | Resultado real y evidencia |
|---|---|
| Inventario Windows / WSL | Python 3.13.14 Windows y 3.12.3 Ubuntu/WSL2; doctor ejecutado en ambos |
| Check documental Windows | PASS, exit 0; [checks.json](../../artifacts/session-01/checks.json) |
| Check documental Linux WSL2 | PASS, exit 0; [checks-linux.json](../../artifacts/session-01/checks-linux.json) |
| Tests Windows | 23 tests PASS, exit 0; [tests-windows.json](../../artifacts/session-01/tests-windows.json) |
| Tests Ubuntu WSL2 | 23 tests PASS, exit 0; [tests-linux.json](../../artifacts/session-01/tests-linux.json) |
| YAML CI | Parseado con PyYAML local: 1 job, 4 pasos; no ejecución GitHub Actions |
| Árboles CopilotDrive | git status --porcelain vacío antes/después en ambos checkouts |
| Infra/producto | No ejecutado: PG/IdP, LLM, VPN, auth real, crash suite, restore, SCA/secrets y Mermaid render |

Los 23 tests son del harness; no son 46 escenarios distintos ni tests de producto.
Cubren fallos deliberados de referencias, estados, auth de contrato, roadmap,
trazabilidad, scope, ruta de reporte y orden portable. Los checks inspeccionan 47
archivos fuente/documentales (artifacts/.git/caches excluidos); el hash de entradas
se conserva en los reportes y coincide entre plataformas tras ordenar por ruta POSIX.
No se declara validación JSON Schema/OpenAPI completa: no hay jsonschema instalado.

Intentos fallidos conservados: primera suite abortó con ImportError porque el loader
usaba parents[3], corregido a parents[2]. Después se detectó hash distinto entre OS
por orden de Path, corregido con orden textual explícito y test de regresión.
Las ejecuciones finales pasan. No se han ejecutado pruebas del producto ni CI remota.

## Aceptación y GO

| Criterio S01 | Evidencia documental / alcance |
|---|---|
| Repositorio inspeccionado | Reconocimiento arriba; checkouts previos preservados |
| Producto y alcance inicial | PRD y SCOPE |
| Arquitectura coherente y límites de confianza | ARCHITECTURE, C4 y ADR-0001/0003 |
| Diagramas y contratos alineados | Siete diagramas, aristas de estados verificadas contra JSON, revisión manual de secuencia; sin render visual |
| Workflow engine especificado | WORKFLOW_ENGINE, DATA_MODEL y workflow-v1.json |
| Agent Runtime Harness | AGENT_RUNTIME y threat model |
| Engineering Harness y SDD | HARNESS, SDD, plantilla, trazabilidad y scripts ejecutados |
| Controles de seguridad y ADR | THREAT_MODEL, CONTROL_MATRIX y cinco ADR; controles de producto aún propuestos |
| Tests y puertas de calidad | TEST_STRATEGY, QUALITY_GATES y suites negativas locales |
| Roadmap de ocho sesiones | Ocho secciones con doce campos cada una, comprobadas |
| Sesión 02 ejecutable como especificación | SESSION_02_SPEC, spec/plan/tasks/checklist, contratos exactos |
| Riesgos y handoff | RISKS R01..R14 y HANDOFF con responsables/gates |
| Revisión arquitectónica y consistencia | Autocrítica arriba, correcciones y checks; no auditoría independiente externa |

**GO para comenzar sesión 02 cuando se solicite**, limitado a implementar plataforma.
**NO-GO para despliegue/uso empresarial**: producto sin construir ni validar. La
integración S02 exige habilitar PG/IdP real; Docker daemon no estaba disponible.
No hay blocker documental crítico conocido. R01/R02/R05/R06 siguen como riesgos de
ejecución con gates obligatorios, no como garantías resueltas por escribir documentos.
La sesión 02 no se inicia automáticamente. [Riesgos](RISKS.md) y [handoff](HANDOFF.md)
son parte de la entrega. [Manifest](../../artifacts/session-01/manifest.json) lista
todos los archivos creados; ningún archivo previo fue modificado.
