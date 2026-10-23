# 003-workflows — continuación S03

Estado: S03 EN CURSO, 2026-10-23. T03-01 aprobada por autor; T03-02 implementa
persistencia/appender/lectura mixta probadas localmente. [T03-03](intake.md)
implementa intake atómico/idempotente; sin worker.
[Arranque histórico](start.md), [contratos](contracts.md) y [persistencia](persistence.md).
Especificación normativa propuesta: [SESSION_03_SPEC](../../docs/roadmap/SESSION_03_SPEC.md).
Requisitos REQ-WF-01/02 y guardas de REQ-WF-03; regresión REQ-PLAT-01/02/HAR-01.
Valor: no perder tickets ni trabajo local ante duplicados o reinicios.

Historia: operator autenticado crea un ticket idempotente; API confirma su estado
atómico; un worker persiste evidencia local y pausa para el operador. Actor, estado
y éxito se deciden por reglas y DB. Sin LLM, efectos IT ni resolución simulada.

Entrada técnica: cierre S02 de 660f7d3 verificado remotamente. Entrada de gobierno:
revisión humana S02/riesgos y aprobación T03-01/ADR-0008 confirmadas por el autor
antes de implementar T03-02. La aprobación no es validación del motor pendiente
ni de producción; el cierre humano de toda S03 se reserva a T03-08.

La especificación enlazada detalla precondiciones, flujo, transacciones, errores,
seguridad, contratos y AC03-01..10. [Plan](plan.md), [tareas](tasks.md) y
[checklist](checklist.md) descomponen la ejecución. Tests de contrato T03-01 existentes;
intake y sus pruebas PG/HTTP/process crash implementados. Las rutas de lectura,
cancelación y ejecución durable del worker siguen propuestas. Sin GO S04.
