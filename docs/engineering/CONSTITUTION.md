# Constitución de ingeniería v1

Estado: PROPUESTO como política del proyecto; verificaciones S01 IMPLEMENTADAS.
Cambios por ADR y revisión de seguridad; una excepción no puede conceder autoridad al modelo.

| Principio | Invariante y evidencia exigida |
|---|---|
| P1 Security by design | Identidad != permiso; deny-default; secretos y red mínimos; negativos CT-01/06 |
| P2 Durable execution | Estado/jobs transaccionales, recuperación de crashes, fencing; crash suite PG real |
| P3 Deterministic control | Modelo no concede permisos/aprueba/ejecuta shell/declara éxito; adversarial suite |
| P4 Contract-first | API/event/tool/state schema y guardas antes de código; contract diff/review |
| P5 Observability by design | IDs/eventos/trazas correlacionados sin secretos; auditoría completa y redaction |
| P6 No overengineering | Dependencia requiere necesidad, alternativa y ADR; sin servicios por moda |
| P7 Failure first-class | Errores clasificados, UNKNOWN y pausa operable; sin éxito inferido |
| P8 Verifiable engineering | Completado requiere pruebas ejecutadas y evidencia; no confundir build con DoD |
| P9 Spec-driven delivery | Requisito→spec→diseño→tarea→código→test→evidencia antes de implementar |
| P10 No fake production | Estados EXISTENTE/PROPUESTO/IMPLEMENTADO/PROBADO/VALIDADO separados; fakes solo tests |

Una sesión termina coherente, con handoff versionado y riesgos abiertos con dueño.
No se elimina persistencia, seguridad, audit, recuperación ni tests para respetar calendario.
No se instala globalmente por comodidad ni se ejecuta fuente remota sin inspección.
La revisión externa simulada es autocrítica del mismo asistente, no auditoría independiente.
