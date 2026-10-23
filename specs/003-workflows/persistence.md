# T03-02 — persistencia y auditoría versionada

2026-10-23. El autor confirma: «Apruebo tras revisión; continuar T03-02», en
respuesta explícita a aceptación del cierre/riesgos S02, contratos T03-01 y ADR-0008.
Entrada humana satisfecha para este alcance local; no valida S03 ni producción.
Se preserva el árbol T03-01 sin commit de HEAD 3b91f58 y sus evidencias históricas.

## Tarea y dependencias

REQ-WF-01/02, guardas REQ-WF-03 y regresión REQ-PLAT-02. T03-01 aprobada para
implementar; T03-02: migración 0002, constraints/índices, rol worker, appender v2 y
lectura mixta v1/v2. Sin intake, cancelación HTTP ni worker ejecutable todavía.
Pruebas PG18/Keycloak reales, migración vacía y N-1 con datos S02, sin mocks de DB.

## Decisiones de almacenamiento

Seis tablas del paquete: incidents, workflows, workflow_steps, jobs, api_idempotency
y evidence. UUID/FK, timestamps PG, defaults acotados y constraints. Incidents solo
OPEN en esta fase. Workflows conserva estados normativos para compatibilidad y
definition_version desconocida para retención segura. Sin tablas S05 ni coste LLM.
creator_id en workflows se liga mediante FK compuesta a incidents: permite al
appender contrastar actor sin conceder lectura de texto de incident al audit_owner.
Detalle mínimo de implementación: audit_owner también recibe SELECT(id,workflow_id)
de evidence, exclusivamente esas dos columnas, para rechazar referencias inexistentes
o de otro workflow en LOCAL_SNAPSHOT_RECORDED. Sin lectura de payload ni texto.
La matriz se concreta con ese grant y se prueba su límite por columna.
FK compuestas ligan job/step/evidence/idempotency al mismo workflow/incidente.

Un workflow activo por incident y un job activo por workflow/kind mediante índices
parciales. Evidence inmutable para runtime, snapshot cerrado y hash contrastado en
servidor. Idempotency inmutable y sin limpieza; response_body liga los IDs con FKs.
La expiración/lease se almacena; las carreras y recovery se implementan después.

audit_events añade state_snapshot privado y checks correlacionados tipo/versión.
audit_append v1 y 0001 no se editan. audit_append_v2 conserva canonicalización/hash,
valida payload/estado/version/actor de API o sistema y calcula/verifica snapshot.
SECURITY DEFINER, owner no-login y search_path fijo. Contrato público de audit admite
unión discriminada v1/v2, sin exponer state_snapshot/hash/lease ni cambiar sus rutas.

Bootstrap genera contraseña/DSN worker ignorados, sin rotar existentes; crea login
sin superuser/DDL/herencia/bypass y CONNECT solo lab. Migración otorga grants por
tabla/columna de la matriz, no crea roles globales ni solicita superuser. Fixtures
crean bases efímeras propias y conceden CONNECT worker explícito. Sin servicio
worker ni mounts de sus credenciales en API. Sin nuevas dependencias/imágenes base.

## Verificación y límites

Registrar resultados reales al terminar en revisión/evidencia T03-02. Mantener
pruebas S02 y contratos T03-01. No AC03-01..07 completos ni GO S04 por esta migración.
Los controles de owner/fence/CAS de job store y crash suite siguen T03-03..06.
No commit/push/merge/release/despliegue ni infraestructura externa autorizados.
