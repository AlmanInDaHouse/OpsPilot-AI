# Contratos y versionado

Estado: PROPUESTO, no hay endpoints desplegados. Contrato máquina S02:
[platform.openapi.json](../../contracts/platform.openapi.json). Dominio futuro abajo.
Schemas JSON son contratos objetivo; comprobar JSON/refs no equivale a validación
de instancias ni conformidad OpenAPI completa (gate con librería real S02).

## Plataforma sesión 02

| Método/ruta | Semántica / auth |
|---|---|
| GET /health/live | 200 `{status:ok}` si proceso vivo, sin dependencias; público solo red interna |
| GET /health/ready | 200 mismo cuerpo si DB SELECT 1, schema Alembic exacto y JWKS válido en caché; 503 genérico en otro caso |
| GET /v1/me | 200 principal_id+roles locales; 401 token inválido; 403 principal deshabilitado/no provisionado; 503 DB/JWKS necesarios ausentes |
| GET /v1/audit-events | auditor/admin, stream_id requerido UUID, after_seq>=0 y limit 1..100; orden seq ascendente, next_after_seq=último o cursor entrante si vacío |

Error cerrado `{code,request_id}`; no traceback, claims, cuerpo original o secretos.
`request_id` UUID generado por servidor; traceparent W3C se valida, nunca se usa como
identidad. 401 añade WWW-Authenticate. Límites de cuerpo 16 KiB (rutas S02 sin body),
timeout API 10 s, health timeout DB 1 s; proxy 100 req/min por principal y límite IP
anónimo 30/min, con 429 genérico a especificar antes de publicar fuera del laboratorio.
No CORS comodín. Readiness sin credenciales accesible solo a health network, no internet.

OIDC: backend verifica access token JWT asimétrico, issuer/aud exactos, exp/nbf/iat
con skew <=30 s, algoritmo allowlist RS256 y `kid` desde JWKS de issuer preconfigurado.
Nunca ID token para API, `jku`/`x5u` del token ni discovery de URL del usuario. JWKS
cache TTL 5 min, refresh controlado por kid desconocido (una vez/30 s), caducado y
sin red falla cerrado. No aceptar alg none/HS256. Sesión 02 provisión explícita de
principal+roles por script local privilegiado; sin rol JIT ni confiar en role claims.
Cambios de grants/deshabilitación se consultan por petición y antes de dispatch,
y generan authorization.granted/revoked o identity.disabled con audit atómico.
No hay jerarquía implícita: admin configura pero no hereda operator/approver. El control
técnico de tercero compara principal_id con proponente; garantizar personas distintas
requiere además provisión gobernada que impida cuentas duplicadas del mismo humano.
Token revocado en IdP puede vivir hasta exp: TTL access token <=5 min, deny local
inmediato; documentar esta ventana. UI futura usa Authorization Code + PKCE S256,
tokens en memoria y CSP; no localStorage ni flujos password/implicit.

## Dominio futuro (no endpoints de sesión 02)

S03 definirá OpenAPI exacto antes de implementar: POST /v1/incidents devuelve 202
con incident_id/workflow_id tras commit atómico; `Idempotency-Key` UUID scoped por
sujeto+ruta, misma clave/hash devuelve respuesta original, cuerpo distinto 409.
GET /v1/incidents/{id} y GET /v1/workflows/{id}: operador autorizado/auditor lectura,
existencia no visible devuelve 404. POST /v1/workflows/{id}/cancel: CAS If-Match version,
202 significa solicitud registrada, no efecto revertido; versión obsoleta 409.
S05 especificará POST /v1/proposals/{id}/decision con approval nonce y snapshot hash;
nonce/token de UI no concede permiso por sí solo; 409 replay, 410 vencido y audit.
S06 cierre por operador con evidence_id de verificación independiente; sin evidencia
válida 409. Ninguna API expone SQL, shell, endpoint tool genérico ni set_state.

## Eventos y propuestas

[event-v1.schema.json](../../contracts/event-v1.schema.json): envelope de auditoría
estricto, event_id, stream_id/seq, tiempo UTC, actor_id nullable para sistema, trace_id,
reason_code/aggregate_id/aggregate_version/evidence_ids. Las transiciones exigen
from/to/definition_version y snapshot_hash; eventos de intent/tool exigen operation_id;
propuesta/aprobación exigen proposal_hash. Solo refs/hashes redacted; snapshot de cada
versión se conserva inmutable en workflow_steps/evidence en S03 para reconstrucción.
El schema restringe campos; el motor además verifica que la arista y guarda sean válidas.
Antes de emitir nuevos payloads hay que versionar contrato y añadir pruebas de instancia;
no emitir estructuras arbitrarias. Campos from/to deben coincidir con workflow-v1.

[proposal-v1.schema.json](../../contracts/proposal-v1.schema.json): snapshot para un
único recurso lab y tres tools sin argumentos libres. Backend asigna workflow/version,
policy y TTL, valida recomendación de modelo contra catálogo y construye snapshot;
el modelo no inventa esos valores. Hash SHA-256 de JSON canónico con sort_keys y
separadores compactos UTF-8, sin floats; incluir todos los campos y identity del
proponente (metadato persistido). Algoritmo versionado `proposal-hash-v1`.
Test golden bytes en S05. Schema de plan/diagnóstico exacto se añade antes S04.

Invocación interna: `operation_id`, `intent_id`, tool_id/version, resource_id,
args_hash y fence; secretos se resuelven fuera del payload. Resultado:
SUCCEEDED/FAILED/UNKNOWN + evidence_id + observed_at + error_code clasificado.
Consulta `reconcile(operation_id)` devuelve CONFIRMED_SUCCESS/CONFIRMED_FAILURE/
CONFIRMED_NOT_EXECUTED/INDETERMINATE; no convierte UNKNOWN en retry automáticamente.
