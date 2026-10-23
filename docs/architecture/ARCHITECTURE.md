# Arquitectura objetivo

Estado: arquitectura objetivo versionada. S02 implementa shared/identity/audit,
adapters PG/OIDC y API; hitos posteriores siguen PROPUESTOS. Evidencia y límites
en [revisión S02](../roadmap/SESSION_02_REVIEW.md); no hay validación empresarial.
Decisiones: [ADR](../decisions/README.md). Requisitos: [PRD](../product/PRD.md).

## Selección crítica del stack

| Área | Selección | Alternativa y coste evitado / asumido |
|---|---|---|
| UI | React + TypeScript, Vite, cliente OpenAPI | SSR/Next no aporta al panel interno inicial; API y auth se testean antes de UI |
| API | Python 3.13, FastAPI, Pydantic 2 | Django facilita admin pero no justifica cambiar; Go reduce overhead, añade fricción AI; validación nunca sustituye autorización |
| Datos | PostgreSQL 18, SQLAlchemy 2, psycopg 3, Alembic | SQLite no reproduce locks/concurrencia; base vectorial separada duplica operación |
| RAG | pgvector, activado en S04 | Full-text de PG como baseline; comparar antes de índice ANN; versión exacta fijada con imagen compatible |
| Jobs | Motor lineal Python + PG, leases y fencing | Temporal reduce carga distribuida; se reconsidera si no supera crash suite S03; no construir framework general |
| Modelos | Puerto propio pequeño y un adapter HTTP | SDK opcional si aporta contratos/usage; sin framework multiagente ni proveedor hardcoded |
| Infra | Docker Compose para laboratorio + Linux CI | VM/container host endurecido para piloto; no Kubernetes; Compose no ofrece HA |
| Telemetría | OpenTelemetry, JSON logs, Prometheus-compatible | Sin stack completo inicial; collector/exporter S07; auditoría transaccional desde S02 |
| Identidad | OIDC/OAuth2, Keycloak de laboratorio | IdP corporativo configurable; no construir servidor de identidad ni contraseñas |

Versiones mayores son familias objetivo; S02 debe resolver versiones estables exactas,
lock con hashes e imágenes por digest después de inspección de fuentes oficiales.
No se presentan como combinaciones instaladas ni probadas. `requirements` flotantes
y `latest` quedan prohibidos en entregas ejecutables.

## Monolito modular y direcciones permitidas

Un repositorio, un artefacto backend y una base. API/worker de investigación comparten
release; runner de herramientas es proceso de execution plane separado sin LLM ni
credenciales de usuario, con red y credencial mínima. Solo S05/S06 requiere runner.
No necesita broker ni API pública propia: consume intents por interfaz restringida.

| Módulo futuro | Responsabilidad | Dependencias permitidas (puertos públicos) |
|---|---|---|
| shared | IDs, reloj, errores, contratos de eventos | stdlib; sin servicios ni ORM |
| identity | Verificar token, mapear sujeto `(issuer,sub)`, roles locales | shared |
| incidents | Tickets, cierre por evidencia y decisión humana | shared, identity |
| workflows | Estado, jobs, recuperación, presupuesto | shared; puertos hacia AI/policy/tools/audit |
| knowledge | Documentos, ACL, chunks, embeddings | shared, identity |
| ai | Gateway, context builder, output validation | shared; knowledge vía puerto |
| governance | Políticas versionadas, propuestas y aprobaciones | shared, identity |
| tools | Registry, intent, invocación, reconciliación y verificación | shared, governance vía puerto |
| audit | Eventos de seguridad y negocio, consulta autorizada | shared |
| adapters | PG, HTTP IdP/LLM, telemetría y runner lab | implementa puertos anteriores |
| entrypoints | FastAPI, worker, runner; composition root | casos de uso y adapters |

Dentro de cada módulo: `domain` → `shared`; `application` → domain/puertos;
`adapters` → application/domain. Nunca domain→FastAPI/SQLAlchemy/HTTP. Ningún módulo
accede a tablas ajenas salvo UoW transaccional explícita; repositorios aportan operaciones
al mismo UoW, no conexiones independientes. Sin import dinámico de herramientas.
Puertos síncronos Python tipados, DTO inmutables; eventos persistidos para pasos
asíncronos. No llamadas de red en transacciones DB.

## Control plane, execution plane y comunicaciones

Control plane: API, identidad, tickets, planificación, aprobaciones, metadatos y audit.
Investigation worker lee documentos autorizados y propone, sin credenciales VPN.
Execution plane: runner solo permite IDs de recurso del catálogo; secretos y endpoints
resueltos en adapter local. Modelo no recibe secretos, URLs arbitrarias ni comandos.
Runner reclama intent con token/lease y acceso DB de mínimo privilegio a procedimientos
acotados, no a documentos ni políticas editables. El aislamiento de procesos por sí
solo no es barrera: exige roles PG, red egress allowlisted y revisión S05/S06.

HTTP de UI→API, API→JWKS/discovery; worker→gateway LLM y PG. PG→jobs mediante polling
durable; NOTIFY opcional solo despierta, nunca sustituye cola. Runner→servicio lab
por HTTPS autenticado con credencial de alcance fijo; verifier usa otra identidad y
cliente/red de prueba. Herramienta de reinicio encapsulada en servicio de laboratorio
real, con operación ID durable; su contrato se valida en S06 antes de habilitar escritura.

## Persistencia, despliegue y evolución

[Modelo de datos](DATA_MODEL.md), [motor](WORKFLOW_ENGINE.md) y [contratos](API_CONTRACTS.md)
son las fuentes normativas. PG coordina estado/jobs/audit en una transacción. Outbox
solo para entregar fuera de esa transacción; no copiar jobs innecesariamente.
Lectura de estado HTTP; notificaciones/SSE se difieren si comprometen el vertical.

Configuración tipada al arrancar: entorno, issuer/audience, DSN por rol, referencias
a secretos, timeouts, presupuestos y resource catalog version. Config inválida impide
arranque; no defaults permisivos. `.env.example` sin secretos en S02. Secretos por
archivos montados con permisos mínimos en lab y gestor empresarial en despliegue real;
rotación/expiración documentadas. No claves en prompts, eventos, Git o frontend.

Versionar API `/v1`, schema de evento `1`, tool/version, policy/version, prompt/version,
workflow definition/version y migración. Runs quedan ligados a definición; worker
compatible debe procesar versiones N/N-1 o pausar intake y drenar antes de upgrade.
Contrato incompatible exige nueva versión; nunca reinterpretar un intent aprobado.

Despliegue propuesto: host dedicado, reverse proxy TLS, API sin privilegios, volúmenes
PG cifrados por host, redes separadas, runner sin Docker socket. Publicar solo proxy;
PG y métricas internas. Migrador one-shot con rol DDL; API/worker no lo tienen.
Expand/contract: aplicar migración aditiva, desplegar release compatible, backfill,
retirar columnas solo tras ventana de compatibilidad. Rollback de aplicación únicamente
si schema compatible; sin downgrade destructivo automático. Pausar mutaciones si duda.

Backups base + WAL cifrados fuera host, claves recuperables y restore en host nuevo;
restaurar no debe ejecutar intents previos: intake detenido, inventario de efectos,
reconciliación de IN_FLIGHT/UNKNOWN y aprobación renovada antes de habilitar runner.
Ensayo en S08; hoy recuperación es diseño, no capacidad comprobada.

## Tenancy y límites

Single-tenant significa DB, credenciales, realm y red por organización. ACL dentro
de la organización sigue siendo obligatoria. No agregar `tenant_id` como promesa de
aislamiento. Multitenancy compartido exigiría ADR, RLS forzada con rol no-bypass,
índices/foreign keys tenant-scoped, ACL/queues/caches separados y pruebas de fuga.

PG/host es SPOF. Escalar workers se limita por pool, cola, lock de recurso, cuota LLM
y capacidad de VPN. Medir antes de sharding/broker. Si p95 cola >5 s a carga pactada,
locks dominan o el motor exige DAG/versionado complejo, comparar Temporal mediante
spike y migración por puertos. No prometer HA ni escalabilidad horizontal ilimitada.
