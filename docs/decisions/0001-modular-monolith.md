# ADR-0001 — monolito modular, una organización por despliegue

Estado: aceptado para diseño, 2026-10-22. Contexto: vertical IT pequeño en ocho hitos,
sin equipo de operación distribuida ni requisito demostrado de SaaS compartido.

Decisión: un artefacto backend con API y workers separados; DB y realm por organización.
Frontend separado en mismo repositorio. Puertos tipados y UoW explícito delimitan módulos.

Alternativas: microservicios agregan red, versionado y transacciones distribuidas;
multitenancy compartido reduce coste por cliente pero exige aislamiento RLS/ACL probado.
Coste aceptado: despliegue por cliente y PG/host como SPOF; no es HA. Módulos se pueden
extraer si evidencia de escala/ownership lo exige, preservando puertos y contratos.
Revisar ante segundo cliente con hosting compartido o equipos independientes.
Validación requerida: tests de imports/capas S02, ACL S04 y carga S08.
