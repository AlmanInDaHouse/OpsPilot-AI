# Handoff versionado — próxima sesión 02

Fecha: 2026-10-22, Europe/Madrid. Último hito terminado: S01, arquitectura y harness
documental PROBADO en Windows y Ubuntu/WSL2. GO para empezar S02 bajo nueva petición;
NO-GO para despliegue. No iniciar sesión 02 automáticamente.

Actualización de ubicación/publicación: 2026-10-23, Europe/Madrid. El autor trasladó
el proyecto a `C:\Users\manul\OneDrive\Escritorio\opspilot-ai` y autorizó expresamente
el primer commit y push a `https://github.com/AlmanInDaHouse/OpsPilot-AI.git`, rama
`main`. Consultar `git log -1` y `git status` para el estado efectivo. La autorización
corresponde a esta publicación; no inicia sesión 02 ni autoriza releases/despliegues.

- Decisiones vigentes: ADR-0001..0005; monolito modular single-tenant, PG durable,
  modelo sin autoridad, catálogo cerrado y SDD portable.
- Código modificado: solo scripts/dev.py, scripts/check_repository.py y tests/harness;
  CI documental, JSON contratos y Markdown. No producto, no cambios en CopilotDrive.
- Tests ejecutados: 23/23 PASS en Windows/Python 3.13.14 y Ubuntu WSL2/Python 3.12.3;
  check PASS en ambos. Evidencia JSON en artifacts/session-01 y SESSION_01_REVIEW.
  Primera suite falló por ruta loader; corregida. Orden de hash entre OS corregido.
- Fallos conocidos: Docker daemon no accesible; Spec Kit no instalado; uv/node ausentes
  del PATH de Ubuntu WSL2 (sí disponibles en Windows); runtime sin construir.
- Deuda técnica: gates producto pendientes según QUALITY_GATES; Mermaid sin render;
  versiones exactas del stack por fijar en S02, no confundir mayores objetivo con lock.
- Riesgos abiertos: RISKS R01..R14 con responsables y gates.
- Próximo objetivo autorizado en una nueva petición: ejecutar exclusivamente T02-01..08.

## Arranque de sesión nueva

1. Usar la ubicación del Escritorio indicada arriba y comprobar `git status --short`
   y `git log -1`; preservar cualquier modificación posterior a la publicación de S01.
   Leer AGENTS, constitución y revisión S01.
2. Leer SESSION_02_SPEC, specs/002-platform/spec/plan/tasks/checklist y contratos.
3. Ejecutar `python scripts/dev.py doctor`, `check`, `test` antes de modificar.
4. Cerrar prerrequisitos IdP/PG, versiones/roles/hash; completar una tarea acotada cada vez.
5. Retirar deliberadamente guard de S01 `src/infra` en checker al autorizar S02;
   sustituirlo por fitness tests reales, no desactivar el resto del harness.
6. Ejecutar gates S02 reales y registrar evidencias, fallos/riesgos y GO/NO-GO S03.

No depender de memoria de chat. No push/merge/release/deploy ni infraestructura
externa. No credenciales de producción, LLM ni VPN en S02. No trasladar código de
CopilotDrive: es otro producto. Guía operacional completa en HARNESS y TEST_STRATEGY.
