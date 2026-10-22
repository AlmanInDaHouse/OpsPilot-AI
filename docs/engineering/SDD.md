# Spec-driven delivery y evaluación de Spec Kit

Estado local: specify/openspec no encontrados en PATH, `uv tool list` vacío; no
`.specify` ni integración instalada en este proyecto. Hay specs Markdown artesanales
en CopilotDrive, ajenos al producto. Python 3.13 y uv están disponibles.

Upstream inspeccionado: Spec Kit **v1.2.3**, Python >=3.11, integración `codex` con
skills en `.agents/skills/speckit-<command>/SKILL.md`, invocación con `$` en chat.
Compatibilidad declarada, no validada localmente. Ver [fuentes](SOURCES.md).
No se invocaron comandos inexistentes ni se instalaron dependencias.

## Proceso operativo sin dependencia de CLI

1. Constitución: verificar P1–P10 y decisiones vigentes.
2. Especificación: copiar [plantilla](../../specs/TEMPLATE.md), asignar Requirement ID,
   motivo, historia, precondiciones, flujo, alternativas, NFR y seguridad.
3. Clarificación: registrar ambigüedades con impacto/alternativas/responsable/gate;
   no implementar decisiones que afecten aislamiento, permisos o semántica sin cerrarlas.
4. Plan técnico: contratos/datos/interfaces/migración, amenazas y diseño por ADR.
5. Checklist: aceptación medible y pruebas negativas de fallos/carreras, no solo happy path.
6. Tareas: IDs acotados, dependencias, archivos previstos, tests y evidencia por tarea.
7. Consistencia: requisito→spec→diseño→tarea→código→test→evidencia en
   [traceability.json](../../specs/traceability.json); `python scripts/dev.py check`.
8. Implementación: un incremento autorizado; actualizar estado solo cuando exista código.
9. Convergencia: ejecutar gates de fase, revisar diff/seguridad y enlazar evidencia real.
   Fallos críticos implican NO-GO, no avance por tiempo. Actualizar handoff.

`PROPUESTO` permite rutas de código/test futuras en trazabilidad sin fingir archivos.
`IMPLEMENTADO` exige rutas existentes; `PROBADO`/`VALIDADO` exigen además evidencia
versionada y resultado declarado, con alcance y limitaciones. El validador no juzga
veracidad de toda evidencia ni demuestra propiedades del producto.

## Incorporación posterior de Spec Kit (opcional, no necesaria para S02)

Primero revisar tag/SHA y dependencias upstream, licencias y avisos. En carpeta
temporal fuera del checkout crear entorno local; no instalar globalmente. Secuencia
documentada para v1.2.3, **no ejecutada aquí**:

```text
uv venv .venv-speckit
uv pip install --python .venv-speckit/Scripts/python.exe "specify-cli @ git+https://github.com/github/spec-kit.git@v1.2.3"
.venv-speckit/Scripts/specify.exe --help
.venv-speckit/Scripts/specify.exe init scratch-opspilot --integration codex --events false
```

En WSL/Linux sustituir `Scripts/python.exe` por `bin/python` y `Scripts/specify.exe`
por `bin/specify`. El venv y scratch se crean en espacio temporal elegido, no dentro
del repositorio actual. Inspeccionar diff generado, handlers y comandos antes de copiar
solo plantillas/skills necesarias. No ejecutar init con overwrite sobre este repo.
Constitución actual sigue siendo fuente única; enlazar/adaptar `.specify/memory/constitution.md`
sin mantener dos políticas divergentes. Mapear spec.md/plan.md/tasks.md actuales,
conservar IDs y evidencia. Probar integración en Codex y registrar versiones reales.

Después, usar solo skills efectivamente instaladas: constitution, specify, clarify,
plan, checklist, tasks, analyze, implement y converge según inventario local. Ningún
nombre en esta página implica que ya esté disponible. No sustituir tests por una
declaración de convergencia del asistente.
