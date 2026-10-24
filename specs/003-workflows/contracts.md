# T03-01 — contrato concreto para revisión

Estado: APROBADO PARA IMPLEMENTACIÓN por el autor el 2026-10-23 tras revisión de
cierre/riesgos S02 y ADR-0008: «Apruebo tras revisión; continuar T03-02».
[Arranque histórico](start.md) y [alcance de persistencia](persistence.md).
T03-02 implementa esquema/appender/lector; [T03-03](intake.md) implementa intake.
T03-04 implementa [lecturas/cancelación](access-cancel.md); T03-05 implementa
[worker local](worker.md). Recovery/retry integral pendiente T03-06.

## API y orden de validación

[OpenAPI S03](../../contracts/workflows.openapi.json) es independiente del contrato
S02: sus cuatro GET se preservan; T03-02 amplía solo el schema de lectura audit a
unión v1/v2. El OpenAPI de dominio contiene intake implementado y tres operaciones
de lectura/cancelación implementadas por T03-04.
No hay endpoint de ejecución, permisos, herramientas, cierre ni set_state.

Todas las respuestas: Cache-Control: no-store, X-Content-Type-Options: nosniff y
X-Request-ID generado por servidor. Error: solo code y request_id UUID, sin eco de
input ni versión/identidad ajena. 401 añade WWW-Authenticate: Bearer. Cada status
solo admite su code correspondiente. 409 usa los códigos definidos por operación.
422 incluye Content-Type distinto de application/json en intake; charset UTF-8
opcional. Cuerpo máximo real 16 KiB y plazo HTTP 10 s, también en streaming.
Rechazar claves JSON duplicadas, BOM, NaN/Infinity, NUL, UTF-8 inválido y surrogates
aislados. Longitud en puntos de código Unicode; sin trim ni normalización Unicode.
GET y cancel sin body; ninguna ruta S03 admite query parameters. Authorization,
Idempotency-Key e If-Match duplicados son 422; no se concatenan.

Orden: límites de transporte/headers duplicados; token; principal/grants locales
habilitados; input; visibilidad; CAS/replay; commit. PG/IdP necesarios ausentes ⇒
503. No consultar existencia antes de autorizar rol. Operator no creador e ID
inexistente reciben el mismo 404 NOT_FOUND. Auditor con grant explícito lee todo
el lab; no crea ni cancela. Admin/approver sin otro grant reciben 403. Múltiples
roles conceden solo los permisos expresos de cada grant; no hay herencia.

## Idempotencia y bytes canónicos

Scope UNIQUE: principal_id local estable + ruta literal /v1/incidents + UUID
normalizado lowercase. No incluye token, texto, issuer suelto ni proceso. Body
validado solo title/description obligatorios, sin defaults, floats ni coerción.
Algoritmo request-hash-v1: SHA-256 del JSON UTF-8 con ensure_ascii=False,
sort_keys=True, separadores coma/dos puntos sin espacios y allow_nan=False:

```json
{"body":{"description":"Laboratorio sintético","title":"VPN de prueba"},"route":"/v1/incidents","schema_version":1}
```

Revalidar identidad/grants antes de comparar. Misma clave/hash: 202 y los dos IDs
originales, sin escritura/evento nuevos; solo cambia correlación HTTP, fuera del
body persistido. Otro hash: 409 IDEMPOTENCY_CONFLICT sin datos anteriores. Revoke
impide replay; token renovado del mismo principal conserva scope. Otros sujetos
no colisionan. S03 conserva todos los registros: mínimo 7 días, nunca reciclar clave
activa y sin limpieza automática. Privacidad pendiente antes de datos reales.

Transacción única: incident OPEN/version 1, workflow QUEUED/version 1/definición 1,
step inicial, job READY, incident.created y respuesta. UNIQUE resuelve carreras;
perdedor relee tras rollback de su transacción. Sin locks en memoria ni 202 antes
de commit. Commit incierto: 503; retry con la misma clave consulta el resultado PG.

## ETag y cancelación

Tag fuerte exacto: `"wf-<UUID lowercase>-v<entero decimal positivo>"`. If-Match admite
una sola etiqueta así, sin W/, wildcard, lista, espacios ni ceros iniciales. Máximo
9223372036854775807; exceso 422. Schema limita forma/longitud; parser futuro comprueba
límite numérico (implementado en WorkflowTag.parse). UUID de otra entidad con formato válido: 409 VERSION_CONFLICT,
después de visibilidad. GET workflow 200 y cancel 202 incluyen ETag de su versión.
Sin conditional GET S03; intake sin ETag porque el workflow puede haber avanzado.

Lock workflow → jobs; comprobar versión antes de terminales. Tag obsoleto: 409
VERSION_CONFLICT incluso si CANCELLED. SUCCEEDED/FAILED con tag actual: 409
TERMINAL_WORKFLOW. CANCELLED con tag actual: 202 misma versión/fecha, sin escritura.
En estados seguros de workflow-step-v1: intención, transición CANCELLED, incremento
de versión/fence e invalidación de jobs con audit atómico. Fecha PG asignada una
vez y nunca borrada. Incident permanece OPEN; no se promete rollback físico.

EXECUTING/VERIFYING/OUTCOME_UNKNOWN, inaccesibles mediante el paso S03, conservan
estado; se persisten intención/versión/evento una vez. Intención ya registrada y
tag actual: 202 sin otra mutación. Sin transición ilegal, retry ni reenvío de efectos
ambiguos, incluso si deadline agotado. Cancel no expone una vía de activar esos estados.

## Paso, evidencia, errores y definición

[Paso local](../../contracts/workflow-step-v1.json): leer ticket PG, validar
OPEN/version 1/relaciones, producir [snapshot de intake](../../contracts/incident-snapshot-v1.schema.json)
y pausar NEEDS_OPERATOR/LOCAL_SNAPSHOT_RECORDED. No resuelve ticket. title_hash y
description_hash: SHA-256 de cada string UTF-8 exacto; content_hash: SHA-256 del
snapshot canónico completo. Evidence: UUID, observed_at PG, collector local-intake-v1,
source_ref incident:UUID:vN, kind INCIDENT_SNAPSHOT_V1, independence_role
INTAKE_SNAPSHOT. Sin texto libre, tokens, issuer/sub ni razonamiento. No es prueba
independiente. UNIQUE(workflow,step_key,kind), contenido inmutable.

snapshot_hash de evento es distinto: hash del [estado posterior](../../contracts/workflow-snapshot-v1.schema.json)
guardado inmutable junto al evento en el mismo UoW. Se propone columna privada
audit_events.state_snapshot nullable: NULL en v1, objeto cerrado en eventos v2 de
workflow; no se añade al envelope público. Appender v2 lo valida contra workflow,
calcula snapshot_hash y conserva el objeto en su INSERT append-only. Su dueño
recibe SELECT de workflows para esa comprobación y SELECT(id,workflow_id) de
evidence para ligar referencias; sin texto de incidents ni payload de evidence.
Canonicalización S02 preservada;
timestamps UTC con seis decimales y Z. DB asigna identidad de evento/seq/tiempo/hash
y valida actor permitido. El contenido de intake no se copia al ledger.

Claim SKIP LOCKED bloquea solo job. Mutación conjunta: workflow → job → audit;
revalidar owner/fence/lease/version con reloj DB. Sin locks durante trabajo externo.
Heartbeat 15 s, lease 60 s; no revivir lease vencida. Poll 2 s + jitter U(0,1 s).
Tres intentos; backoff U(0,min(30,2^attempt) s). Transitorio local: RETRY_WAIT,
resume_state INVESTIGATING y available_at persistidos. Reclaim no reinicia plazos.
Permanente/schema/invariante: NEEDS_OPERATOR/PERMANENT_LOCAL_FAILURE sin retry.
Intentos agotados: NEEDS_OPERATOR/RETRY_EXHAUSTED. Deadline 300 s desde intake y
presupuesto activo 300000 ms persistidos por reloj DB. Agotamiento: QUEUED → FAILED;
INVESTIGATING/RETRY_WAIT → NEEDS_OPERATOR, reason DEADLINE_EXHAUSTED. Sin coste LLM.

Definición desconocida: no ejecutar v1 ni inventar QUEUED→NEEDS_OPERATOR, ausente
del grafo. Bajo locks invalidar job a DEAD, incrementar versión, conservar estado y
resume_state, registrar workflow.blocked/UNSUPPORTED_DEFINITION con snapshot. Es
retención operable; cancelación segura permitida con versión actual. Sin auto-upgrade
ni reanudación sin decisión humana. Conservar definition_version desconocida.

## Appender, migración y privilegios propuestos

[ADR-0008](../../docs/decisions/0008-workflow-contract-boundary.md) y
[eventos v2](../../contracts/workflow-events-v2.schema.json). Migración incremental;
no editar 0001. audit_append v1 solo identidad S02; nuevo audit_append_v2 con cuatro
tipos cerrados, validación de instancia/arista/reason/actor/size. Tabla con checks
correlacionados v1/v2. Ampliar DTO/lector a unión versionada antes del primer v2,
preservando lectura/hash de eventos históricos. No appender JSON arbitrario.

[Matriz](../../contracts/workflow-policy-v1.json): worker con login PG dedicado,
CONNECT solo lab, USAGE public, sin CREATE/TEMP/rol heredado, OIDC ni credenciales
de API/provisión/DDL. App/worker sin escritura audit directa. App inserta intake e
idempotency; worker lee incidents y modifica solo workflows/jobs/steps/evidence.
Evidence e idempotency sin UPDATE/DELETE. Sin DDL/TRUNCATE/bypass RLS/SET ROLE owner.
La matriz define grants por columna instalados y comprobados en T03-02.
Crear rol mediante bootstrap explícito, no API ni migración con superuser.
N-1 debe preservar datos/eventos S02 y probar constraints, índice parcial y grants.

Sin servicio/framework/dependencia nuevos. Dos procesos reales, 100 jobs y crash/
fence/cancel/retry siguen siendo gates T03-02..07. Pruebas de este paquete validan
schemas/golden/negativos; no SQL, auth HTTP, locks, commit ni recuperación S03.
