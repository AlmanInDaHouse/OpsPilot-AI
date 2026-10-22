# 001-vpn — especificación del vertical objetivo

Estado: PROPUESTO. Feature de producto transversal S03–S08, no implementación S01.
S02 es prerrequisito separado. Motivo de negocio e historias en [PRD](../../docs/product/PRD.md).

## Historia y precondiciones

Como operador quiero investigar una incidencia VPN, consultar documentación que puedo
leer y proponer una actuación sustentada. Como aprobador distinto quiero autorizar
una acción concreta viendo impacto/evidencia. Como auditor quiero reconstruir el run.
Precondiciones: identidad y permisos locales válidos, PG migrado, corpus aprobado con
ACL, LLM autorizado, catálogo/policy versionados y lab aislado con servicio y cliente
independiente. Secretos preprovisionados fuera del contexto del agente.

## Flujo principal y contratos

Crear ticket y workflow atómicos; investigar con RAG ACL y lecturas registradas;
validar diagnóstico/propuesta; policy determinista; aprobación mutante de tercero;
intent durable; ejecución allowlisted; probe VPN independiente; informe con evidencia;
operador confirma cierre. Contratos y guardas: [API](../../docs/architecture/API_CONTRACTS.md),
[motor](../../docs/architecture/WORKFLOW_ENGINE.md), [runtime](../../docs/architecture/AGENT_RUNTIME.md),
[datos](../../docs/architecture/DATA_MODEL.md). APIs exactas por hito se cierran antes
de código, no se deducen de texto libre. Definición de workflow lineal versionada.

## Alternativas y fallos

No permiso→denegar; evidencia insuficiente→NEEDS_OPERATOR; proveedor caído→retry
acotado; aprobación caducada/revocada→no dispatch; resultado mutante ambiguo→UNKNOWN
y cuarentena; cancela durante ejecución→reconciliar efecto; verificación negativa→
workflow FAILED/ticket OPEN; informe no afirma éxito. Recuperación no renueva budget.

## Requisitos, aceptación y pruebas

| ID | Given / When / Then resumido | Test y sesión |
|---|---|---|
| REQ-WF-01 | Mismo sujeto/key/body, dos requests: un ticket/run/job/evento y misma respuesta; cuerpo distinto 409 | TEST-03-ATOMIC, S03 |
| REQ-WF-02 | Dos workers/crash/lease vencido: uno confirma paso por fence válido y otro no puede sobreescribir | TEST-03-CRASH, S03 |
| REQ-WF-03 | Timeout tras efecto: UNKNOWN y cero reenvíos automáticos; reconciliación con operation_id | TEST-05-UNKNOWN, S03/S05/S06 |
| REQ-AI-01 | Contexto permitido: JSON estricto, citas comprobables y budget reservado; sin evidencia se abstiene | TEST-04-EVAL/BUDGET, S04 |
| REQ-RAG-01 | Documento sin permiso/revocado: no aparece en chunks/contexto/citas ni cache | TEST-04-ACL/INJECT, S04 |
| REQ-POL-01 | Modelo recomienda acción no permitida: DENY con razón y ningún adapter invocado | TEST-05-POLICY, S05 |
| REQ-APR-01 | Aprobación ajena vigente: una consumición; cambio hash/nonce/revoke/TTL concurrente no permite replay | TEST-05-APPROVAL, S05 |
| REQ-TOOL-01 | Tool desconocida/URL/comando/args extra: rechazo anterior a red | TEST-05-POLICY, S05 |
| REQ-LAB-01 | VPN caída real: restart autorizado del único recurso, service ledger muestra operación única | TEST-06-LAB, S06 |
| REQ-VER-01 | Restart exitoso pero túnel roto: no cierre; túnel+tráfico independiente correctos: evidencia habilita cierre humano | TEST-06-VERIFY, S06 |
| REQ-OPS-01 | Operador ve propuesta, approval TTL, UNKNOWN y evidencia sin token/secretos; correlación de eventos/trazas | TEST-07-OPS/PRIVACY, S07 |
| REQ-REL-01 | Pérdida host y restore: RPO/RTO medidos, intake pausado y ninguna mutación automática | TEST-08-RESTORE/LOAD/E2E, S08 |

## NFR, seguridad, tareas y evidencia

Aplican [NFR-01..14](../../docs/product/NFR_SLO.md) y
[CT-01..12](../../docs/security/CONTROL_MATRIX.md). Riesgos y gates en
[roadmap](../../docs/roadmap/ROADMAP_8_SESSIONS.md) y [RISKS](../../docs/roadmap/RISKS.md).
Cada sesión descompone tareas acotadas antes de código siguiendo plantilla de
spec/plan/tasks/checklist S02; esta feature no autoriza ejecutar ocho sesiones ahora.

Evidencia requerida: ID de requisito/test, commit o hash de árbol, tool/model/prompt/
dataset/lock, comando, resultado y fallos, logs redacted, referencias de aprobación,
operation ledger, probe cliente y reporte de restauración. Estado por requisito en
[traceability](../traceability.json); rutas de código/tests son previstas, no existentes.
DoD: aceptación ejecutada, revisión seguridad/spec, documentación y handoff; no
VALIDADO hasta revisión del autor en el entorno y alcance definidos.
