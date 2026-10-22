# Agent Runtime Harness del producto

Estado: PROPUESTO. Distinto del [engineering harness](../engineering/HARNESS.md), que
controla desarrollo y verificaciones de Codex. Este runtime controlará cada ejecución
del producto; no es un prompt gigante ni un framework multiagente.

| Componente / autoridad | Entrada → salida y control |
|---|---|
| Model Gateway / adapter | Request con modelo/version, schema y límites → response+usage+request_id; allowlist de proveedor, timeout, circuit breaker |
| Context Builder / determinista | Ticket redacted + documentos ACL + evidencias frescas → contexto acotado con procedencia; sin credenciales, roles editables ni chain-of-thought |
| Retrieval Layer / determinista | Sujeto y ACL vigentes, query → chunks versionados; filtros antes del ranking, cita y hash |
| Agent Executor / orquestador | Paso durable+presupuesto → llamada al modelo; máximo 6 llamadas/10 herramientas por run; sin bucle libre |
| Structured Output Validation / determinista | JSON estricto sin campos extra → diagnóstico/propuesta o error; una reparación como máximo y consume presupuesto |
| Tool Registry / configuración | tool_id/version fijo → schema, riesgo, permisos, timeout, idempotencia, verifier; cerrado al arrancar |
| Policy Evaluation / determinista | Identidad, recurso, acción y policy snapshot → DENY/ALLOW/REQUIRE_APPROVAL con reason_code; error DENY |
| Tool Invocation Gateway / determinista | Propuesta validada+permiso+aprobación → intent; modelo no llama adapter directamente |
| Execution Budget / durable | Reserva atómica de coste, tokens, llamadas y tiempo → autorización de siguiente paso o NEEDS_OPERATOR |
| Durable Workflow Context / motor | Estado/version, definition_version, evidence refs → transición CAS y jobs |
| Audit Events / transaccional | Decisión resumida, actor y hashes → evento redacted correlacionado; fallo bloquea mutación |
| Human Approval / API autenticada | Aprobador humano + propuesta inmutable → decisión de un uso; no recibe instrucciones del documento recuperado |
| Result Verification / identidad separada | Intent/evidencia y probe independiente → PASSED/FAILED/INCONCLUSIVE; umbrales fijados antes de acción |
| Failure Recovery / motor | Error clasificado + lease/intent → retry seguro, UNKNOWN, reconciliación o intervención |

## Modelo, orquestador y datos

Modelo interpreta síntomas, clasifica, formula hipótesis y sugiere una herramienta
del catálogo. Diagnóstico incluye afirmaciones, evidence_ids y nivel provisional.
No concede permisos, cambia políticas, aprueba, selecciona credenciales/endpoints ni
declara éxito. Orquestador elige siguiente estado, reserva presupuesto, persiste y
decide recuperación. Policy/argumentos/approval/freshness/commit son deterministas.

Documentos y resultados son datos no confiables, delimitados por fuente/ACL/hash.
Filtrar instrucciones conocidas ayuda pero no es frontera de seguridad. Exfiltración
se limita por minimización de contexto y egress allowlisted; ninguna herramienta de
envío genérico. No prometer que un prompt resuelve injection. Output tool truncado a
64 KiB, sin HTML ejecutable ni referencias a secretos; refs a evidencia persistida.

Cada tool define input JSON Schema estricto, recursos cerrados, política, tipo de
efecto READ/MUTATE, reconciler y verifier. Validar esquema y semántica: recurso de
catálogo, permiso actual, sin hostname/comando del LLM. Ejemplo objetivo:
`vpn.service_status@1`, `vpn.restart_service@1`, `vpn.client_probe@1`.
Restart siempre requiere aprobación; estado lectura puede ser ALLOW si role operator.
Verifier usa cliente independiente sin permiso de reiniciar. Cambios de catálogo
versionan propuestas y no se recargan en un run sin invalidar aprobación.

## Fallos y evaluaciones

LLM 429/5xx: retry seguro con presupuesto; 401/403 o schema reiteradamente inválido:
NEEDS_OPERATOR. Circuit breaker por proveedor, sin fallback silencioso que cambie
región/retención. Documento sin permiso o evidencia vencida: no se entrega al modelo.
Policy indisponible: DENY. Tool timeout mutante: UNKNOWN. Verificación inconclusa no
marca éxito. No ocultar errores bajo respuestas plausibles.

En S04: golden de >=50 preguntas con citas y ACL, injection adversaria en ticket,
documento y output tool, schema violations, agotamiento de presupuesto, 429/timeout;
revisar provider/model/prompt/embedding al cambiar versión. En S05/S06: intento de
herramienta inexistente, argumentos extra, replay, rol revocado y falso cierre.
Evals registran dataset hash, configuración, coste, evidencia humana y fallos.
