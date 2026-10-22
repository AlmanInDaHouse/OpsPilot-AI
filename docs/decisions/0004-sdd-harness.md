# ADR-0004 — SDD portable y harness pequeño

Estado: aceptado para sesión 01, 2026-10-22. Contexto: `specify`/OpenSpec no están
instalados; Python y Git sí. Dos repositorios vecinos pertenecen a otro producto.

Decisión: repositorio OpsPilot separado, sin tocar CopilotDrive; constitución,
spec/plan/tasks/checklist y trazabilidad versionadas. Validadores Python stdlib y CI
documental. Spec Kit 1.2.3 se ha inspeccionado en origen y declara integración Codex;
no instalado ni probado aquí. Incorporación opcional en copia temporal con revisión
del diff; nunca `init` remoto con overwrite sobre trabajo existente.

Alternativa instalación global añade dependencias/handlers antes de necesitarlos;
solo AGENTS sin verificaciones no detecta inconsistencias. Se acepta que gates S01
comprueban estructura, no semántica ni cumplimiento de runtime. Revisión humana y
tests negativos siguen siendo necesarios. Detalles en [SDD](../engineering/SDD.md).
