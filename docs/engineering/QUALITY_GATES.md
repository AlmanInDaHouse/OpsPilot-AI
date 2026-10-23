# Puertas de calidad por fase

Estado: gates S02 implementados; evidencia y veredicto en SESSION_02_REVIEW.
La columna S01 se conserva como historial. Los gates futuros son obligatorios
en su fase; no son checks verdes ni skips equivalentes a éxito en sesión 01.

| Gate | Disponible S01 | Obligatorio desde / ejecución prevista |
|---|---|---|
| Formatting | JSON parseable, Markdown fences/enlaces, whitespace/EOF; sin formatter completo | S02 Ruff format, Markdownlint, prettier si UI S07 |
| Lint | No disponible para producto | S02 Ruff Python; S07 ESLint TypeScript |
| Type checking | No disponible | S02 mypy estricto en backend; S07 tsc --noEmit |
| Unit tests | unittest harness | S02 casos de uso/policy sin infraestructura |
| Integration tests | No disponible | S02 PG18+IdP real, migración/UoW; S03 multiworker; S06 VPN real |
| Contract tests | JSON/$ref/seguridad de rutas, limitado | S02 OpenAPI validator+JSON Schema instances+HTTP parity, sin endpoints de negocio |
| Architecture tests | Coherencia documental/estados, limitada | S02 imports/ciclos/infra, con fixtures negativos |
| Security scanning | No scanner ejecutado | S02 Bandit + secret scan sobre árbol/historial, findings críticos bloquean |
| Dependency scanning | Sin dependencias externas del harness | S02 pip-audit/OSV equivalente, imagen CVE y acciones SHA; no red disponible implica gate pendiente |
| Docs/spec consistency | Implementado scripts/check_repository.py | Todos los hitos; revisión humana de contradicciones y contract diff |
| AI evaluation | No aplica a S01/S02; producto no tiene IA | S04 golden, ACL, injection, grounding, budget; repetir al cambiar modelo/prompt/dataset |
| E2E / resiliencia / restore | No disponible | S06 VPN y falso cierre; S08 crash/carga/backups/seguridad completa |

CI S01: `.github/workflows/harness.yml`, Python 3.13 Linux/Windows, pasos check/test,
permiso contents:read, acciones fijadas por SHA. Archivo implementado; ejecución
remota no realizada (sin push). No cobertura ficticia ni jobs de producto vacíos.

En S02 crear CI con lock frozen, format/lint/types/unit/contracts/arquitectura/security
y job integration Linux real. Fallo, timeout, servicio inaccesible o test crítico
omitido ⇒ NO-GO. Findings críticos/altos explotables requieren corrección; excepciones
menores necesitan dueño, justificación y fecha, nunca desactivar una suite completa.
Coverage orientativo >=85 % líneas del backend y 100 % ramas críticas de autorización/
estados/approval/UNKNOWN por escenarios, sin sustituir con métrica de porcentaje.

Publicar resultados fallidos además de aprobados, redacted. CI no usa secretos de
producción ni corre código de PR no confiable con credenciales. Dependabot/equivalente
se añade cuando existan dependencias, revisando actualizaciones y ejecutando suites.

## Scanner CI S02

[Spec de remediación](../../specs/002-platform/scanner-remediation.md): preflight
Docker real no privilegiado antes del lab, suite Linux completa, PG fresco,
recovery y tres scans separados. Un scan fallido mantiene exit distinto de cero;
manifest y upload always conservan únicamente evidencia saneada del run actual.
Snapshots versionados anteriores no se suben como evidencia nueva. No publicar
artifacts/local ni logs íntegros. HEAD y hash de inputs distinguen el árbol sin
commit del build publicado. Una verificación local nunca concede GO para S03.
