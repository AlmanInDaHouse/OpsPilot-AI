# Registro de decisiones

ADR-0001..0005 recogen el diseño provisional; ADR-0006 cierra la plataforma S02
implementada y ADR-0007 su remediación local. Aceptación según revisión y gates.
Cambiar una decisión exige ADR nuevo y análisis de contratos/tests afectados.

| ADR | Decisión |
|---|---|
| [0001](0001-modular-monolith.md) | Monolito modular y single-tenant |
| [0002](0002-durable-postgres.md) | Motor lineal PG, at-least-once y UNKNOWN |
| [0003](0003-governed-runtime.md) | LLM sin autoridad y execution plane restringido |
| [0004](0004-sdd-harness.md) | SDD portable sin instalar Spec Kit |
| [0005](0005-platform-stack.md) | Stack, identidad y operación mínima |
| [0006](0006-platform-boundaries.md) | Cierre de contratos e identidad/audit S02 |
| [0007](0007-keycloak-maintained-runtime.md) | Derivada mantenida del IdP y aceptación completa de S02 |
| [0008](0008-workflow-contract-boundary.md) | PROPUESTO: contratos S03, appender v2 y worker con permisos mínimos |
