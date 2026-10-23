# 003-workflows — plan propuesto

Estado: entrada humana satisfecha; T03-01 aprobada y T03-02 implementada/probada
localmente; [intake T03-03](intake.md) implementado. Sin worker ejecutable.
[Spec](spec.md), [contratos](contracts.md) y [persistencia](persistence.md).
T03-04..08 continúan pendientes.

1. Aprobar entrada humana y cerrar contrato OpenAPI/evento/snapshot/errores y
   matriz RBAC. Reutilizar S02; ninguna autoridad derivada de claims del IdP.
2. Diseñar migración N-1, invariantes SQL y appender versionado; comprobar orden de
   locks, grants de API/worker e idempotencia antes de repositorios/handlers.
3. Implementar intake/UoW idempotente y lecturas/cancelación con contratos negativos.
4. Implementar job store, worker de paso local real, lease/fence/CAS y pausa honesta.
5. Añadir retry/deadline/reclaim/version compatibility; probar carreras y caídas reales.
6. Ejecutar regresión S02 y AC03, CI del SHA final y revisión humana; actualizar
   trazabilidad, riesgos, evidencias y handoff. No GO S04 por build o tests parciales.

Carpetas de producto futuras: src/opspilot/incidents, workflows, adapters/postgres,
entrypoints; migración incremental y tests contract/integration/architecture. No se
crean en T03-01. Sin nuevas dependencias salvo necesidad y decisión revisadas.
