# Investigación y fuentes primarias

Consultadas 2026-10-22. Fuentes de diseño, no evidencia de ejecución local. Versiones
inmutables cuando posible; páginas vivas se deben volver a revisar antes de fijar locks.

| Fuente | Hallazgo utilizado / límite |
|---|---|
| [Spec Kit release v1.2.3](https://github.com/github/spec-kit/releases/tag/v1.2.3) | Última release resuelta durante inspección; no instalada |
| [pyproject v1.2.3](https://github.com/github/spec-kit/blob/v1.2.3/pyproject.toml) | specify-cli 1.2.3, Python >=3.11 y dependencias inspeccionadas sin ejecutarlas |
| [Codex integration v1.2.3](https://github.com/github/spec-kit/blob/v1.2.3/docs/integrations/codex.md) | Clave `codex`, skills en `.agents/skills`, soporte declarado por upstream; integración local no probada |
| [Spec Kit metodología](https://github.com/github/spec-kit) | Constitution/spec/plan/tasks/implement/converge; clarificación/checklist/análisis según workflow |
| [Instalación](https://github.github.io/spec-kit/installation.html) | Incorporar versión fijada en entorno aislado; no ejecutar en esta sesión |
| [PostgreSQL 18 SELECT](https://www.postgresql.org/docs/18/sql-select.html) | SKIP LOCKED útil para consumidores de cola; no es consistencia general ni garantiza efectos únicos |
| [Temporal SDKs](https://docs.temporal.io/encyclopedia/architecture/temporal-sdks) | Alternativa para ejecución durable; reconsiderar si motor acotado no supera gates |
| [OWASP LLM Top 10 2025](https://genai.owasp.org/llm-top-10/) | Catálogo de riesgos para threat model, no acreditación |
| [NIST AI RMF 1.0](https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-ai-rmf-10) | Marco voluntario de gestión de riesgos |
| [ISO/IEC 42001](https://www.iso.org/standard/42001) | Sistema de gestión organizacional, no checklist de código |
| [RGPD texto oficial](https://eur-lex.europa.eu/eli/reg/2016/679/oj) | Referencia jurídica; acceso web automatizado limitado por challenge, no se afirma revisión íntegra del texto en esta sesión |
| [Comisión: AI Act](https://digital-strategy.ec.europa.eu/en/policies/regulatory-framework-ai) | Aplicabilidad y calendario actualizado; clasificación depende finalidad/rol |
| [Comisión: navigating AI Act](https://digital-strategy.ec.europa.eu/en/faqs/navigating-ai-act) | Plazos diferenciados; verificar modificaciones consolidadas antes de uso real |
| [ENS BOE](https://www.boe.es/buscar/act.php?id=BOE-A-2022-7191) | Ámbito RD 311/2022; solo cuando corresponda al servicio/contrato |

La compatibilidad real local de Spec Kit no se ha validado: no hay CLI/skills instaladas,
por lo que no se ejecutaron comandos `speckit-*`. No se presupone que documentación
upstream equivalga a un entorno Codex configurado o una toolchain probada.
