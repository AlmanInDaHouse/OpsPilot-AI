# ADR-0002 — coordinación transaccional PG y motor lineal

Estado: aceptado provisionalmente, 2026-10-22. Contexto: secuencia VPN acotada,
necesidad de mostrar durable execution y mantener un único sistema persistente.

Decisión: jobs+state+audit en un UoW; claim SKIP LOCKED, leases y fencing; intent único
y operation_id para efectos externos. UNKNOWN bloquea recurso/reenvío. Outbox solo
al cruzar a destino externo. Entrega interna at-least-once, jamás exactly-once remota.

Temporal es alternativa seria: aporta recuperación/versionado mantenidos y reduce
riesgo de motor propio, a cambio de otro servicio/modelo operativo. Celery requiere
broker y no reemplaza estado de negocio/aprobación. FastAPI BackgroundTasks o memoria
no resuelven durabilidad. Se acepta complejidad propia únicamente para flujo lineal.
Gate: si S03 no supera crash/concurrency suite, NO-GO S04; comparar Temporal y reducir
UI/ingestión para conservar controles. Revisar si hacen falta DAG dinámico, fan-out
masivo, muchas versiones coexistentes o más de un dominio. Responsable: autor.
