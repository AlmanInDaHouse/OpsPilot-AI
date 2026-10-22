# PRD — objetivo de producto

Estado: PROPUESTO. Responsable: arquitecto/autor. Revisión: 2026-10-22.

## Problema, usuarios y valor

Operadores IT investigan incidencias consultando fuentes dispersas y realizando
operaciones con permisos excesivos o con evidencia insuficiente. OpsPilot debe
reducir trabajo repetido manteniendo una cadena reconstruible de decisiones.
Solicitante comunica síntomas; operador investiga/propone; aprobador autoriza
acciones concretas; auditor consulta evidencia sin ejecutar. Administrador mantiene
configuración fuera del agente. El autor debe poder explicar y mantener el diseño.

## Caso VPN y requisitos

| ID | Necesidad y aceptación de negocio | Sesión |
|---|---|---|
| REQ-PLAT-01 | API autenticada, autorización separada, estado durable y migraciones reproducibles | 02 |
| REQ-PLAT-02 | Lectura de auditoría restringida y transacciones fail-closed | 02 |
| REQ-WF-01 | Persistir ticket y arrancar workflow atómicamente con deduplicación | 03 |
| REQ-WF-02 | Reinicios, concurrencia y reintentos seguros sin perder ownership | 03 |
| REQ-WF-03 | Resultado externo desconocido bloquea reejecución hasta reconciliación | 03/05 |
| REQ-AI-01 | Diagnóstico estructurado provisional con referencias verificables | 04 |
| REQ-RAG-01 | Recuperación documental filtrada por permisos antes del ranking | 04 |
| REQ-POL-01 | Decisión determinista y default-deny independiente del LLM | 05 |
| REQ-APR-01 | Aprobación vinculada a acción inmutable, vigente y de un tercero | 05 |
| REQ-TOOL-01 | Invocar solo herramientas registradas con argumentos validados | 05 |
| REQ-LAB-01 | Operación VPN real en red aislada y recuperación reproducible | 06 |
| REQ-VER-01 | Verificar acceso desde cliente independiente; éxito de herramienta no cierra ticket | 06 |
| REQ-OPS-01 | Vista de ticket, aprobaciones, errores y evidencias con trazas correlacionadas | 07 |
| REQ-REL-01 | Restauración, pruebas E2E, seguridad y RC con limitaciones explícitas | 08 |
| REQ-HAR-01 | Requisitos, decisiones, tareas, tests y evidencia trazables | 01 |

Flujo: recibir → persistir → clasificar → recuperar documentación autorizada → leer
estado técnico → diagnosticar con evidencias → proponer → evaluar política → aprobar
si aplica → ejecutar → verificar independientemente → informar y auditar.
Alternativas: evidencia insuficiente pide intervención; IdP/LLM/herramienta caídos
producen espera/error explícito; aprobación vencida impide ejecutar; acceso persiste
fallando tras acción lleva a NEEDS_OPERATOR y ticket OPEN.

## Medición del valor

En sesión 08 comparar investigación manual y asistida de diez incidencias equivalentes
en laboratorio: tiempo hasta diagnóstico sustentado, intervenciones, citas correctas,
coste y falsos cierres. Publicar población, variación y errores; diez muestras no
demuestran generalización empresarial. Éxito mínimo del vertical: restablecer túnel
VPN mediante la única acción permitida y probar tráfico cliente→recurso interno;
conservar el caso negativo en que reiniciar el servicio no resuelve el acceso.

No se autoriza autonomía general, soporte de infraestructuras arbitrarias ni
declaración de compliance. La fecha o número de sesiones no sustituye los gates.
