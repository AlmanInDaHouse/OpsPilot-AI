# 003-workflows — continuación S03

Estado: PROPUESTO; 2026-10-23, responsable autor. Sin implementación autorizada.
Especificación normativa propuesta: [SESSION_03_SPEC](../../docs/roadmap/SESSION_03_SPEC.md).
Requisitos REQ-WF-01/02 y guardas de REQ-WF-03; regresión REQ-PLAT-01/02/HAR-01.
Valor: no perder tickets ni trabajo local ante duplicados o reinicios.

Historia: operator autenticado crea un ticket idempotente; API confirma su estado
atómico; un worker persiste evidencia local y pausa para el operador. Actor, estado
y éxito se deciden por reglas y DB. Sin LLM, efectos IT ni resolución simulada.

Entrada técnica: cierre S02 de 660f7d3 verificado remotamente. Entrada de gobierno:
revisión humana y autorización de implementar S03 pendientes. Contratos wire y
appender deben cerrarse antes de código. Riesgos y límites de producción siguen vigentes.

La especificación enlazada detalla precondiciones, flujo, transacciones, errores,
seguridad, contratos y AC03-01..10. [Plan](plan.md), [tareas](tasks.md) y
[checklist](checklist.md) descomponen la ejecución futura. Todos los tests/rutas S03
son propuestos; no hay evidencia de implementación ni GO S04.
