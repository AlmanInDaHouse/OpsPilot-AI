# ADR-0003 — autoridad determinista y herramientas cerradas

Estado: aceptado para diseño, 2026-10-22. Contexto: documentos y modelo son no fiables;
el producto operará sobre servicios reales y los prompts no ofrecen aislamiento.

Decisión: modelo recomienda; policy y orquestador autorizan; humano tercero aprueba
snapshot; runner aislado ejecuta un catálogo sin shell; verifier independiente prueba
resultado. Acciones mutantes siempre con aprobación en el primer vertical.

Alternativa agent framework con plugins abiertos acelera demos pero amplía exfiltración,
confused deputy y permisos. Un proceso sin aislamiento simplifica desarrollo pero
expone credenciales al worker AI. Se acepta coste de roles DB/red y servicio de lab
con operation_id para que el control sea verificable. Mocks solo dentro de tests.
Validación: injection/schema/ACL S04, carreras y replay S05, operación real S06.
