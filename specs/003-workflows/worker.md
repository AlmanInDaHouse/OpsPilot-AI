# T03-05 — worker durable local

Estado inicial: main, HEAD/origin/main 6a873ec, árbol limpio. Petición explícita
2026-10-24 autoriza exclusivamente implementación local T03-05, sin publicación.
REQ-WF-01/02 → AC03-04/05/06/09 parciales → T03-05. Dependencias T03-02/03/04 y
hotfix PG presentes. Baseline real ejecutado antes de producto; resultados en
artifacts/session-03/worker. No alterar 0001/0002 ni contratos aprobados.

## Diseño y supuestos previos

Entrypoint independiente, puertos de aplicación y repositorio PostgreSQL sobre
PostgresUow. Cuatro commits: claim, inicio auditado, renovaciones y resultado
auditado. Claim bloquea exclusivamente job con SKIP LOCKED y termina antes de
adquirir workflow. Mutaciones conjuntas: workflow → job → step → audit.
El cálculo del snapshot transcurre fuera de transacción y sin locks SQL.

Lease 60 s, heartbeat 15 s y poll 2 s + U(0,1 s); PostgreSQL decide vigencia.
Owner UUID aleatorio por claim, fence creciente. Resultado verifica ownership,
lease, estado, versión, definición, cancelación y relaciones; repite la guarda
temporal al final después de audit. Un fallo revierte evidence/step/workflow/job/audit.
Incidents OPEN/version 1 es el único contrato instalado. Texto UTF-8 exacto,
snapshot cerrado y canónico; evidencia inmutable, sin diagnóstico ni resolución.

Definición desconocida se retiene con workflow.blocked/UNSUPPORTED_DEFINITION,
job DEAD y fence invalidado, usando contrato existente. Deadline vencido al inicio
usa salida auditada contratada; durante resultado/heartbeat se rechaza por seguridad.
Estos son guardas mínimas, no política completa de deadline/presupuesto T03-06.
Error permanente del snapshot tras inicio válido pausa NEEDS_OPERATOR con
PERMANENT_LOCAL_FAILURE y step FAILED/job DEAD/audit atómicos. Invariantes que
impiden una transición segura se retienen sin retry especulativo. Error SQL o
commit incierto detiene el proceso con diagnóstico cerrado; releer DB antes de
decidir recuperación. No cambiar automáticamente LEASED a READY.

## Verificación exigida

PG18 real y rol worker, dos procesos, 100 jobs; exclusividad, expiración/heartbeat,
fence/version obsoletos, cancelación en fronteras y locks observables. Rollback por
fallos reales de appender/DB/commit. Schema/golden bytes, hashes, privilegios y logs
saneados; regresión Windows/Linux, harness/check, fresh/recovery/scans nuevos.
Resultados y límites reales en [revisión](../../docs/roadmap/SESSION_03_WORKER_REVIEW.md).

T03-06 queda pendiente: reclaim general, retry/backoff, presupuesto/deadline completo,
compatibilidad/reanudación de definiciones y kill points adversariales exhaustivos.
AC03-04/05/06 no se cierran globalmente; sin GO S04/producción ni CI del árbol local.
