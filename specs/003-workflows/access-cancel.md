# T03-04 — lecturas autorizadas y cancelación CAS

Autorización explícita del autor, 2026-10-23. Alcance exclusivo T03-04;
sin worker T03-05/06, commit, publicación ni GO S04. Base main e116767 limpia;
T03-02/03 ya publicadas. Conservar migraciones, appender y snapshots históricos.

## Contratos y supuestos antes de código

Fuente: contracts.md, ADR-0008, workflows.openapi.json, workflow-v1.json y
workflow-events-v2.schema.json. Sin cambio de wire, DDL ni permisos DB.
Auditor explícito lee todo el lab single-tenant; operator solo su recurso.
Admin/approver no heredan lectura/cancelación; múltiples grants suman permisos.
Revocación confirmada antes de la consulta de autorización deniega. Durante una
operación concurrente rige la última consulta de autorización, sin promesa de
revocación retroactiva. Tras esperar el workflow lock se reconsultan los grants.

GET usa una consulta SQL para snapshot y referencias de evidence, evitando mezclar
versiones entre consultas READ COMMITTED. Proyección pública cerrada; sin payload
de evidence, ownership, audit interno ni idempotency. Sin conditional GET.
Los límites/duplicados preceden auth; rol precede parsing/existencia; visibilidad
precede CAS y terminales. Faltante/oculto: mismo NOT_FOUND sin ETag.

## Matriz RBAC

| Principal local activo | GET propio | GET ajeno | Cancel propio | Cancel ajeno |
|---|---|---|---|---|
| operator | 200 | 404 | CAS | 404 |
| auditor | 200 | 200 | 403 | 403 |
| admin / approver | 403 | 403 | 403 | 403 |
| revocado / deshabilitado | 403 | 403 | 403 | 403 |

## Invariantes transaccionales

Una sesión del PostgresUow existente: workflow lock → jobs ordenados por id →
audit stream del appender v2. Comprobar recurso/version bajo lock y repetir
autorización tras la espera. UPDATE CAS con versión esperada; reloj PG fija
cancel_requested_at una sola vez. Estado seguro: CANCELLED/version+1; jobs
READY/LEASED a DEAD, owner/lease NULL y fence+1. DONE/DEAD intactos.
Estado ambiguo: conservar estado, intención/version/audit una vez e invalidar
trabajo pendiente; no reenvío, reconciliación ni liberación de cuarentena.
Timestamp existente se conserva. Appender/constraint/commit fallido revierte todo.
202 solo tras COMMIT; CANCELLED o intención previa con ETag actual no escribe.
SUCCEEDED/FAILED actual: TERMINAL_WORKFLOW; obsoleto primero VERSION_CONFLICT.
Overflow bigint falla cerrado 503; no wrap ni incremento ficticio.

## Given / When / Then y trazabilidad

REQ-WF-01/02/03 → AC03-03/06/09 → T03-04 → adapter/use case/HTTP →
tests unit/contract/integration → artifacts/session-03/access-cancel.

| Given | When | Then / prueba requerida |
|---|---|---|
| operator creador / auditor | GET | schema exacto, PG confirmado y ETag ligado a versión |
| operator ajeno / UUID inexistente | GET/cancel | 404 idéntico, sin metadatos; roles no heredados |
| grants revocados / principal disabled / JWT inválido | acceso | 403/401 con IdP/PG reales |
| header inválido/duplicado/body/query | acceso | 422 sin escritura |
| estado seguro y ETag actual | cancel | estado+jobs+evento v2 atómicos; incidente OPEN |
| dos / veinte peticiones versión igual | cancel concurrente | un 202, restantes 409, un evento |
| versión modificada / job bloqueado | cancel espera | reevalúa CAS; jobs y fences coherentes |
| auditoría bloqueada / error / timeout / COMMIT rechazado | cancel | sin 202 prematuro ni cambios parciales |
| crash antes/después de COMMIT HTTP | retry | estado durable verificable, actual 202 sin escritura |
| EXECUTING/VERIFYING/UNKNOWN preparado en DB efímera | cancel | intención única, estado/evidencia preservados |
| CANCELLED / terminal y ETag viejo | retry | 409 de versión antes de terminal |

Guard SQL impide resurrección de CANCELLED. La validación del resultado tardío
contra owner/fence/lease/version pertenece al worker real T03-05/06: no se acredita
AC03-06 completo mediante estos tests de almacenamiento/cancelación.
