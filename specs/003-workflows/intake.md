# T03-03 — intake atómico e idempotente

2026-10-23. Alcance autorizado: REQ-WF-01/02 → AC03-01/02 → T03-03;
regresión de identidad S02 y negativos de AC03-03/09. Sin lecturas, cancelación,
worker ni ejecución del job. T03-01/ADR-0008 aprobados; T03-02 local preservada.

## Decisiones de implementación antes de código

Se reutilizan 0001/0002 sin cambios, PostgresUow y audit_append_v2. La FK inmediata
y columnas NOT NULL de api_idempotency requieren crear las referencias antes de
insertar la respuesta completa. Una lectura inicial evita trabajo en replay; no
decide exclusividad. La PK (principal_id,route,key) decide la carrera final. Solo
su unique_violation se traduce a carrera: rollback del UoW completo, nueva
transacción READ COMMITTED, revalidación local de operator y relectura confirmada.
No savepoint que conserve filas perdedoras, placeholders ni locks de proceso.
El resto de errores SQL y commit incierto son 503; el cliente reintenta con la clave.

Orden: transporte/headers duplicados → JWT/principal/operator → input estricto →
UoW con nueva comprobación local → replay o incident/workflow/step/job/audit/response
→ commit → 202. Transacciones acotadas por statement/lock timeout existentes.
Cada creación usa su propio stream de incidente; no hay mutex global. Revoke ya
confirmado antes de la lectura de autorización deniega; una petición concurrente
con revoke se autoriza en su snapshot vigente, como S02, sin cache de grants.

request-hash-v1 conserva bytes Unicode exactos, esquema 1/ruta literal y claves
ordenadas. UUID de header con forma canónica (acepta mayúsculas, normaliza al leer).
El evento aprobado incident.created usa stream/aggregate del incidente y versión 1;
0002 comprueba workflow QUEUED del actor. No añadir workflow_id al payload cerrado.
La relación se conserva en workflows y respuesta durable. No guardar texto en audit.

## Verificación exigida

PG18/Keycloak reales, 20 requests concurrentes, procesos independientes, reinicio,
replay revocado y body distinto. Fallos SQL por cada escritura y constraint diferida
real al commit; muerte de proceso antes/después del commit. Cero estado parcial.
Suites Windows/Linux y check, evidencia propia en artifacts/session-03/intake.
Sin limpieza automática, retención de todas las claves; CI remota pendiente.
