# OpsPilot AI: mapa de trabajo

Lee [README](README.md), [handoff](docs/roadmap/HANDOFF.md),
[constitución](docs/engineering/CONSTITUTION.md) y la especificación del hito activo.
S02 tiene GO técnico para 660f7d3. El autor aprobó cierre/riesgos S02, T03-01 y
ADR-0008; T03-02 implementa persistencia/appender v2 y T03-03 añade intake atómico.
T03-04 implementa [acceso/cancelación CAS](docs/roadmap/SESSION_03_ACCESS_CANCEL_REVIEW.md);
T03-05 añade [worker local](docs/roadmap/SESSION_03_WORKER_REVIEW.md);
T03-06 añade [recovery/retry local](docs/roadmap/SESSION_03_RECOVERY_REVIEW.md).
Consultar sus gates; T03-07/08 y aceptación global S03 siguen pendientes.
Leer [revisión de intake](docs/roadmap/SESSION_03_INTAKE_REVIEW.md) y sus gates.
Consultar revisión y handoff para gates y limitaciones; sin GO S04.

- Producto y exclusiones: [PRD](docs/product/PRD.md), [alcance](docs/product/SCOPE.md).
- Diseño objetivo: [arquitectura](docs/architecture/ARCHITECTURE.md), [ADR](docs/decisions/README.md).
- Contratos: [API](docs/architecture/API_CONTRACTS.md), `contracts/`.
- Seguridad: [amenazas](docs/security/THREAT_MODEL.md), [controles](docs/security/CONTROL_MATRIX.md).
- Proceso: [harness](docs/engineering/HARNESS.md), [gates](docs/engineering/QUALITY_GATES.md).
- Hito activo: [sesión 03](docs/roadmap/SESSION_03_SPEC.md), [tareas](specs/003-workflows/tasks.md),
  [contratos para revisión](specs/003-workflows/contracts.md).

Antes de editar: inspeccionar Git, seleccionar requisito y tarea acotada, comprobar
dependencias y registrar supuestos. No sobrescribir trabajo ajeno. No push, merge,
release, despliegue ni infraestructura externa sin instrucción explícita.
Sin comandos arbitrarios en herramientas; permisos y éxito nunca los decide el LLM.
Mocks/fakes solo en tests. Denegación por defecto, secretos fuera del repositorio.

Verificación: `python scripts/dev.py check` y `python scripts/dev.py test` (incluye
PG/IdP reales). `test --suite local` excluye explícitamente integración; no es el gate
completo. Operación exclusivamente local en [runbook](docs/engineering/PLATFORM_RUNBOOK.md).
No convertir gates pendientes en aprobados. Al terminar, revisar seguridad, contratos,
tests y documentación; actualizar handoff y evidencias con resultados reales.
`EXISTENTE`, `PROPUESTO`, `IMPLEMENTADO`, `PROBADO`, `VALIDADO` son estados distintos.
