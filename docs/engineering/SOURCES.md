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

## Fuentes y verificación S02 — 2026-10-23

| Fuente primaria | Uso y límite |
|---|---|
| [PyPI JSON](https://pypi.org/pypi/fastapi/json) | Releases consultadas por paquete; versiones instaladas/licencia metadata y lock hash en artifacts/session-02/environment.json; no implica auditoría legal |
| [Imagen oficial PostgreSQL](https://hub.docker.com/_/postgres) | PG18 monta /var/lib/postgresql; digest verificado por registry y ejecución real 18.6 |
| [Keycloak 26.8.1](https://www.keycloak.org/2026/10/keycloak-2681-released) | Versión estable seleccionada; integración PKCE real no equivale a scan limpio de OS/JVM |
| [Contenedores Keycloak](https://www.keycloak.org/server/containers) | Realm import, exec de entrypoint y separación de lab/producción |
| [PyJWT API](https://pyjwt.readthedocs.io/en/latest/api.html) | API de verificación; política de cache/algoritmos/claims implementada explícitamente y probada |
| [Trivy releases](https://github.com/aquasecurity/trivy/releases/tag/v0.76.1) | Scanner fijado por digest, sin socket ni credenciales montadas; DB y raw hash en evidencia |
| [Alpine v3.24](https://pkgs.alpinelinux.org/packages?branch=v3.24) | apk policy verificó libcrypto3/libssl3 3.5.9-r0 y libuuid 2.42.3-r1; versión exacta en Dockerfile y rescan PASS |
| [Red Hat CA](https://access.redhat.com/solutions/7149312) | Boletín primario de trust store; paquete afectado en Keycloak, no se declara mitigación implementada |
| [Red Hat CVE-2026-91415](https://access.redhat.com/security/cve/CVE-2026-91415) | Referencia del proveedor JVM; acceso web automatizado limitado, hallazgo local Trivy conserva status affected sin FixedVersion |

Scans locales y pruebas son evidencias separadas de estas referencias. Dependencias
dev en venv, sin instalación global. Spec Kit continúa sin instalarse: SDD existente
es suficiente y no se duplica. No se ejecutó código del proveedor de modelos ni VPN.
