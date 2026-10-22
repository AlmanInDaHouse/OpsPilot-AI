# OpsPilot AI: mapa de trabajo

Lee [README](README.md), [handoff](docs/roadmap/HANDOFF.md),
[constitución](docs/engineering/CONSTITUTION.md) y la especificación del hito activo.
Esta entrega contiene SOLO sesión 01. No iniciar sesión 02 sin una nueva petición.

- Producto y exclusiones: [PRD](docs/product/PRD.md), [alcance](docs/product/SCOPE.md).
- Diseño objetivo: [arquitectura](docs/architecture/ARCHITECTURE.md), [ADR](docs/decisions/README.md).
- Contratos: [API](docs/architecture/API_CONTRACTS.md), `contracts/`.
- Seguridad: [amenazas](docs/security/THREAT_MODEL.md), [controles](docs/security/CONTROL_MATRIX.md).
- Proceso: [harness](docs/engineering/HARNESS.md), [gates](docs/engineering/QUALITY_GATES.md).
- Siguiente hito: [sesión 02](docs/roadmap/SESSION_02_SPEC.md), [tareas](specs/002-platform/tasks.md).

Antes de editar: inspeccionar Git, seleccionar requisito y tarea acotada, comprobar
dependencias y registrar supuestos. No sobrescribir trabajo ajeno. No push, merge,
release, despliegue ni infraestructura externa sin instrucción explícita.
Sin comandos arbitrarios en herramientas; permisos y éxito nunca los decide el LLM.
Mocks/fakes solo en tests. Denegación por defecto, secretos fuera del repositorio.

Verificación disponible: `python scripts/dev.py check` y `python scripts/dev.py test`.
No convertir gates pendientes en aprobados. Al terminar, revisar seguridad, contratos,
tests y documentación; actualizar handoff y evidencias con resultados reales.
`EXISTENTE`, `PROPUESTO`, `IMPLEMENTADO`, `PROBADO`, `VALIDADO` son estados distintos.
