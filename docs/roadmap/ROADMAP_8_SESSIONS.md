# Roadmap de exactamente ocho sesiones

Estado: PROPUESTO salvo artefactos documentales/harness S01. Son hitos de aceptación,
no garantía de duración. Si no cabe, reducir UI, ingestión y número de herramientas;
nunca seguridad, persistencia, audit o recuperación. Gates críticos fallidos detienen avance.

## Sesión 01 — arquitectura y engineering harness

1. Objetivo: base revisable y verificable sin lógica de negocio.
2. Alcance: reconocimiento, PRD/SCOPE/NFR, ADR, amenazas, contratos y SDD.
3. Especificaciones: REQ-HAR-01; paquete documental y plantilla de features.
4. Dependencias: Python/Git; fuentes primarias y repositorios existentes inspeccionados.
5. Componentes: documentos, contratos objetivo, validador y tests del harness.
6. Cambios: repositorio independiente, CI documental y handoff S02.
7. Tests: TEST-01-HARNESS, check de enlaces/refs/estados/trazas/roadmap.
8. Security gates: no secretos, instalaciones remotas, operaciones externas ni mezcla CopilotDrive.
9. Quality gates: scripts check/test ejecutados; revisión crítica y riesgos registrados.
10. Evidencias: SESSION_01_REVIEW y resumen del harness con hash de entradas.
11. Riesgos: densidad documental, compatibilidad no probada y diseño de motor propio.
12. GO / NO-GO: GO S02 si base coherente y checks pasan; no implica GO de despliegue.

## Sesión 02 — fundamentos reales de plataforma

1. Objetivo: API autenticada, autorización y PG/migraciones/audit reales.
2. Alcance: health/me/audit, IdP de lab, roles, UoW y CI; sin tickets/workflows/LLM.
3. Especificaciones: REQ-PLAT-01/02, SESSION_02_SPEC y specs/002-platform.
4. Dependencias: S01 revisada, Docker/WSL2 o CI Linux accesible, selección IdP/provisión.
5. Componentes: paquetes shared/identity/audit/adapters/entrypoints y migraciones.
6. Cambios: pyproject+lock, Compose PG18+IdP, contenedor sin root y roles mínimos.
7. Tests: TEST-02-AUTH/AUDIT/CONTRACT/MIGRATE/ARCH/SUPPLY sobre PG e IdP reales.
8. Security gates: JWT/roles fail-closed, sin secretos/log bodies, app sin DDL/UPDATE audit.
9. Quality gates: format/lint/types/unit/contracts/architecture/SCA/security e integración Linux.
10. Evidencias: comandos, lock/digests, OpenAPI parity, reportes CI y SQL roles/migración.
11. Riesgos: Docker apagado, versión exacta dependencies, JWKS/revocación y configuración IdP.
12. GO / NO-GO: GO S03 solo si auth/audit/transacciones/migraciones reales pasan; fake no sustituye IdP/PG.

## Sesión 03 — orquestador durable lineal

1. Objetivo: ticket/workflow/jobs persistentes y recuperación sin pérdidas locales.
2. Alcance: intake idempotente, estados, CAS, leases/fences, retry/cancel y eventos.
3. Especificaciones: REQ-WF-01/02/03; refinar contratos HTTP y snapshot de eventos antes de código.
4. Dependencias: S02 GO, rol worker y migraciones nuevas; reglas de versiones del motor.
5. Componentes: incidents/workflows, PG job store, coordinator, retry/recovery, budget skeleton durable.
6. Cambios: tablas de estado/jobs/evidence/idempotency, workers reales sin LLM/tool mutante.
7. Tests: TEST-03-ATOMIC/CRASH con procesos y PG reales; no simular durabilidad en memoria.
8. Security gates: transiciones autorizadas, actor de sistema, audit atómico y cancel CAS.
9. Quality gates: suite S02 más multiworker/crash/version compatibility; migraciones N-1.
10. Evidencias: kill points, 100 jobs, ownership/fence y ledger antes/después de crash.
11. Riesgos: motor propio subestimado, locks, reloj y jobs atascados; spike Temporal si falla.
12. GO / NO-GO: GO S04 solo con invariantes crash/recovery probadas; si falla no continuar a IA.

## Sesión 04 — AI Gateway y RAG autorizada

1. Objetivo: diagnóstico provisional sustentado con contexto permitido y presupuesto.
2. Alcance: un adapter proveedor, corpus Markdown aprobado, ACL, embeddings y outputs estrictos.
3. Especificaciones: REQ-AI-01/RAG-01, schemas diagnóstico/contexto y golden dataset versionados.
4. Dependencias: S03 GO, proveedor/región/retención/coste aprobados, pgvector compatible fijado.
5. Componentes: ai/knowledge, Model Gateway/Context Builder/validation y budget reservations.
6. Cambios: embeddings+ACL, errores proveedor, métricas usage y referencia por afirmación.
7. Tests: TEST-04-ACL/INJECT/EVAL/BUDGET, >=50 preguntas, proveedor real en smoke/eval autorizado.
8. Security gates: injection no concede autoridad, canary secreto, ACL antes de ranking y egress.
9. Quality gates: schema/contract/ACL, recall/grounding reportados y límites de coste respetados.
10. Evidencias: dataset hash, modelo/prompt/embedding, citas, falsos positivos, coste y negativos.
11. Riesgos: rate limits, fuga por chunks/caches y muestra insuficiente; no fine-tuning prematuro.
12. GO / NO-GO: GO S05 si negativos ACL/injection/budget pasan y calidad medida es aceptada; sin acciones aún.

## Sesión 05 — ejecución gobernada

1. Objetivo: policy, registro cerrado, aprobación humana y intents seguros.
2. Alcance: ALLOW/DENY/REQUIRE_APPROVAL, snapshots, nonce/TTL y runner/reconciler sin activar mutación lab aún.
3. Especificaciones: REQ-POL-01/APR-01/TOOL-01/WF-03, contratos adapter/golden hash.
4. Dependencias: S04 GO, catálogo y política inicial versionados; usuarios operador/aprobador distintos.
5. Componentes: governance/tools, Tool Invocation Gateway, intent/resource lock, runner roles y outbox si destino externo.
6. Cambios: migraciones propuestas/approval/intent, egress/roles separados, preparación de adapter real.
7. Tests: TEST-05-POLICY/APPROVAL/UNKNOWN, adversarial/race; fakes solo tests unit, no tool falso en producto.
8. Security gates: replay/autoaprobación/args libres/role revoked negados; UNKNOWN nunca se reenvía automáticamente.
9. Quality gates: todos previos más locks/concurrencia/privilegios y contrato de reconciliación.
10. Evidencias: matriz policy y carreras reproducidas; runner sin permisos fuera catálogo.
11. Riesgos: TOCTOU remoto y límites de fencing, dependencia de idempotencia del servicio lab.
12. GO / NO-GO: GO S06 solo con gobernanza/UNKNOWN probadas; aún no se afirma operación IT real.

## Sesión 06 — integración IT real y verificación

1. Objetivo: completar vertical VPN con efectos reales acotados y prueba independiente.
2. Alcance: WireGuard en lab aislado, restart allowlisted tras aprobación, cliente/túnel y recurso interno.
3. Especificaciones: REQ-LAB-01/VER-01; spec exacta topología/credenciales/reconciler antes de tocar lab.
4. Dependencias: S05 GO, spike red/kernel seguro, lab explícitamente provisionado sin infraestructura externa.
5. Componentes: adapter de servicio real con operation_id durable, probe cliente y evidencia de verificación.
6. Cambios: runbook de fallo/restauración, catálogo activo lab-vpn-01 y conectividad real.
7. Tests: TEST-06-LAB/VERIFY, pérdida respuesta tras efecto, reinicio que no resuelve acceso y recuperación.
8. Security gates: credenciales separadas y mínimas, sin socket/privilegiado del host, cero efecto fuera lab.
9. Quality gates: E2E HTTP real, invariantes S03/S05 contra servicio real, sin fixtures de producto.
10. Evidencias: túnel/tráfico observado, operation ledger, aprobación, trazas y fallo negativo reproducible.
11. Riesgos: privilegios WireGuard y aislamiento cliente, falso positivo por probar solo puerto/servicio.
12. GO / NO-GO: GO S07 si acceso VPN probado independientemente; no basta exit code de restart.

## Sesión 07 — frontend, observabilidad y operación

1. Objetivo: operación humana usable con estados, evidencia y diagnósticos de fallos.
2. Alcance: panel React/TypeScript, PKCE, aprobación visible y logs/métricas/trazas correlacionados.
3. Especificaciones: REQ-OPS-01, UI contract y runbooks de alertas/roles/retención antes de implementación.
4. Dependencias: S06 GO, API estable y modelo de permisos; collector sin acceso a secretos.
5. Componentes: UI/cliente OpenAPI, OTel y paneles/alertas mínimos, herramientas de soporte.
6. Cambios: UX de UNKNOWN/NEEDS_OPERATOR, contexto de aprobación y estado ticket separado del run.
7. Tests: TEST-07-OPS/PRIVACY, teclado/contraste, XSS, token lifetime, collector caído y correlación.
8. Security gates: no localStorage de token, CSP/CORS exactos, scopes UI sin autoridad implícita.
9. Quality gates: lint/tsc/unit/frontend E2E, backend previo y redaction de logs/eventos.
10. Evidencias: capturas revisadas, flujo aprobación/rechazo/vencimiento, trace IDs y alertas reproducidas.
11. Riesgos: UI consume tiempo del hardening; limitar pantallas antes de recortar controles.
12. GO / NO-GO: GO S08 si operador distingue propuesta/ejecución/verificación/cierre y errores son operables.

## Sesión 08 — hardening y release candidate

1. Objetivo: RC de laboratorio reproducible con límites operativos y evidencia completa.
2. Alcance: E2E, crash/carga, seguridad, restore, SBOM, backup/ancla audit y preparación de despliegue.
3. Especificaciones: REQ-REL-01, NFR-01..14, controles CT-01..12 y cierre de riesgos críticos.
4. Dependencias: S07 GO, entorno aislado y datos sintéticos, ventanas para pruebas de caída.
5. Componentes: scripts de operación/backup/restore, imágenes firmadas si herramienta acordada y release manifest.
6. Cambios: documentación final, runbooks incidentes/rollback y RC candidato; no publicar sin autorización posterior.
7. Tests: TEST-08-LOAD/RESTORE/E2E más regresión completa y revisión de seguridad/IA.
8. Security gates: cero bypass críticos, secretos/CVE explotables corregidos, ancla externa verificable y restore sin reenvío.
9. Quality gates: todos aplicables; NFR medidos o desviaciones con dueño, sin declarar SLO cumplidos no observados.
10. Evidencias: reportes crudos redacted/hash, lock/digests/SBOM, restore cronometrado y matriz aceptación.
11. Riesgos: disponibilidad no demostrable con campaña corta, revisión legal/contexto empresarial pendientes.
12. GO / NO-GO: GO RC solo para alcance de lab probado; despliegue empresarial/certificación requieren validación adicional. No push/release/deploy automático.
