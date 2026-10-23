# ADR-0008 — contratos S03 y evolución cerrada de auditoría

- Estado: aprobado para implementación por el autor tras revisión de S02/riesgos,
  T03-01 y este ADR, 2026-10-23; T03-02 implementa esquema/appender/lector.
- Fecha: 2026-10-23.
- Requisitos: REQ-WF-01/02, guardas REQ-WF-03 y regresión REQ-PLAT-02.
- Contexto: arranque S03 solicitado; appender S02 solo permite cinco eventos de
  identidad. No admite transiciones por ampliar un DTO.

## Decisión

Versionar OpenAPI de dominio independiente y contratos estrictos de evento v2,
snapshot de estado y snapshot local de intake. Conservar contratos/migración/v1
históricos. T03-02 crea appender v2 SECURITY DEFINER con search_path fijo, owner
no-login y validación cerrada. Añadir audit_events.state_snapshot privado e inmutable,
validado y ligado por snapshot_hash al evento; NULL para v1. Appender owner recibe
SELECT de workflows para contrastar estado/version, sin acceso al texto de incidents.
La implementación concreta añade SELECT(id,workflow_id) de evidence para impedir
referencias ajenas o inexistentes, sin acceso a su payload; probado por columna.
Migrar checks y lectura HTTP a unión v1/v2 antes
de emitir v2; preservar canonicalización/hash y datos S02. Worker con login PG
dedicado y grants explícitos, sin token de usuario ni permisos DDL.
[Detalle revisable](../../specs/003-workflows/contracts.md).

Evidencia local: hashes/referencias del ticket persistido, sin texto libre ni
diagnóstico. Pausa NEEDS_OPERATOR; ticket OPEN independiente. Definición desconocida
retiene estado, invalida job y registra workflow.blocked: sin arista nueva ni
handler por defecto. Cada transición conserva snapshot inmutable del estado.

## Alternativas y consecuencias

Ampliar audit_append v1 en sitio confundiría compatibilidad S02 con sucesores y
permitiría payloads no revisados: descartado. Appender JSON genérico diluye el
límite de confianza: descartado. Nueva cola/servicio/framework durable innecesarios
para el paso local; reconsiderar R01 si pruebas reales no demuestran invariantes.

Contratos y migración futura, sin dependencias. Schemas v1/v2 exigen tests de
compatibilidad y lectura mixta. Privacidad/retención para datos reales pendientes;
sin GO S04 ni producción.

## Verificación exigida

Schemas/golden/negativos T03-01; appender SQL/Python, instancia, permisos, rollback
y N-1 T03-02/03; worker/fence/leases/crashes reales T03-05/06. La revisión del
asistente no equivale a aceptación humana ni auditoría independiente.
