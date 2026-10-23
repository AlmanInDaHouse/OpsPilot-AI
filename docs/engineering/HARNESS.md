# Engineering Harness

Estado: checker documental de S01 preservado y extendido en S02 con gates reales.
Los comandos de la tabla histórica de S01 se activaron según
[runbook S02](PLATFORM_RUNBOOK.md), que es la referencia operacional actual.
No confundir con [Agent Runtime Harness](../architecture/AGENT_RUNTIME.md).

## Ciclo de trabajo de Codex

Leer AGENTS→handoff→spec activa→tarea. Inspeccionar estado Git y dependencias,
seleccionar una tarea cuyo contrato esté cerrado y mantener cambios en sus componentes.
Registrar un plan corto con archivos afectados; si aparece cambio de arquitectura,
actualizar ADR/spec antes de implementar. Ejecutar gates correspondientes, revisar
diff y actualizar evidencia/handoff. No conservar contexto solo en memoria del chat.

Fuentes únicas: PRD para valor, SCOPE para exclusiones, ADR para decisiones,
contracts para wire/state, specs para aceptación/tareas y REVIEW para evidencia.
Los documentos enlazan; no copiar políticas completas a AGENTS.

## Fitness functions

| Detección | Mecanismo y fase | Límite |
|---|---|---|
| Documentos/refs/IDs ausentes | `scripts/check_repository.py` S01, enlaces relativos y JSON $ref locales | No comprueba URLs externas ni semántica completa |
| Estados inconsistentes | Igualdad aristas Mermaid/JSON, alcance y terminales S01 | No ejecuta transiciones ni guardas |
| Gates/roadmap incompletos | 8 sesiones con 12 campos, trazas y evidencia S01 | Revisión técnica sigue necesaria |
| Dependencias prohibidas/capas | AST/import-linter por módulos y puertos, S02 | Debe fallar con fixture que importe SQLAlchemy desde domain |
| Ciclos | Grafo imports internos incluyendo relativos + test negativo, S02 | Imports dinámicos prohibidos fuera composition root |
| Acceso infra no autorizado | AST: subprocess/socket/httpx/psycopg/SQLAlchemy solo adapters/entrypoints permitidos, S02/S05 | Complementar permisos PG/egress real; AST no es sandbox |
| Contratos inconsistentes | Validación OpenAPI/JSON Schema, clientes generados y contract tests S02/S04 | Checks S01 solo JSON/refs y auth de rutas |
| Migraciones ausentes | Alembic upgrade desde vacío y N-1, `check` metadata drift, S02 | SQL manual también requiere migración revisada |
| Uso indebido de tools | ToolRegistry cerrado y policy negativos S05 | No basta detectar nombres de imports |
| Pruebas críticas ausentes | Manifiesto de tests críticos y ejecución obligatoria por fase S02+ | Existir archivo no equivale a prueba aprobada |

## Comandos y DX

| Comando `python scripts/dev.py ...` | Ahora | Implementación futura requerida |
|---|---|---|
| doctor | OS/versiones/paths, pasivo; no red ni secretos | Añadir conectividad explícita opcional |
| check | Links/JSON/estados/roadmap/trazas, stdlib | Encadenar formatter/lint/types/arquitectura en S02 |
| test | unittest del harness | S02 seleccionar unit/integration/contract sin esconder skips |
| install | Exit 2, no instala | S02 `uv sync --frozen`, Python pin y hash lock |
| infra | Exit 2 | S02 validar compose y preparar PG/IdP local al pedirlo |
| migrate | Exit 2 | S02 Alembic explícito con rol DDL, sin downgrade automático |
| up / logs | Exit 2 | S02 servicios/logs redacted, no infraestructura externa |
| eval | Exit 2 | S04 golden+ACL+coste con proveedor aprobado |

PowerShell y Linux usan el mismo entrypoint Python, sin Make obligatorio. Windows 11
sirve para edición/harness; integración PG/IdP por Docker Desktop WSL2 o Linux.
No mezclar entornos venv Windows/WSL. CI usa matriz Linux/Windows para harness;
integración S02 corre Linux con servicios reales y evidencia exportada.

## Self-review y evidencia

Comprobar diff contra spec y ADR; guardas de permisos/errores/carreras; contratos
compatibles; tests positivos/negativos ejecutados; sin secretos ni fakes de producto;
docs y limitaciones actualizadas. Compilar no es aceptación. Registrar comando,
entorno, versiones, resultado/exit code, alcance, hash del código/artefacto y fecha.
Si falla un gate, no etiquetar PROBADO. Tests externos no ejecutados: PENDIENTE.

La revisión S01 es autocrítica del mismo asistente, no auditoría independiente de
tercero. El autor debe revisar las decisiones antes de validar para un piloto real.
