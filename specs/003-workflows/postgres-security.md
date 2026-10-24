# S03 — hotfix PostgreSQL / Brotli

2026-10-24, Europe/Madrid. Petición explícita del autor: resolver el bloqueo de
seguridad previo a T03-05, sin implementar worker ni publicar cambios.

## Requisito, tarea y dependencias

REQ-PLAT-01/02 y REQ-HAR-01 → regresión AC03-10 → hotfix de imagen previo a
T03-05. T03-01..04 y ADR-0008 preservados; AC03-06 continúa parcial API/SQL.
Git inicial main/e116767 con cambios locales T03-04; hashes y estado inicial en
artifacts/session-03/postgres-security/baseline.json. Sin reset/stash/clean.

## Evidencia previa y supuestos comprobados

Informe bruto Trivy histórico contrastado por SHA-256: CVE-2026-111497 HIGH,
brotli-libs 1.2.0-r1, fixed 1.2.1-r0, imagen local a88335c32e20. Inspección
real: PostgreSQL 18.6, Alpine 3.24.3, UID/GID 70, repositorios main/community
de v3.24 exclusivamente. libcurl requiere brotli-libs. APK oficial y simulación
resuelven únicamente esa actualización; no hace falta otra distribución ni ADR.

## Cambio acotado

Conservar base oficial por digest; instalar brotli-libs=1.2.1-r0 con firmas APK
durante build antes de USER postgres. Conservar eliminación de gosu. Sin cambios
de dominio, contratos, migraciones, Compose, permisos, secretos, redes o volúmenes.
La fijación falla si el distribuidor retira la versión; no admite fallback silencioso.

## Aceptación y evidencias

Reconstrucción normal y sin caché, inventarios antes/después, hashes de APK y
bibliotecas, repositorios e identidades OCI/config ligados a Trivy final completo.
Tres scans actuales sin HIGH/CRITICAL, PG fresco sin root, comparación íntegra de
tablas del lab, recovery, suites completas Windows/Linux sin skips y checks reales.
Pruebas de migración N-1/rollback, identidad/audit v1/v2, intake/idempotencia,
RBAC/revoke, CAS e invalidación/fence usan las bases efímeras de la suite existente.
No pruebas destructivas sobre el volumen permanente; conservar snapshots previos.

GO técnico LOCAL T03-05 solo si todos esos gates pasan con evidencia consistente.
S03 abierta, CI del árbol sin publicar pendiente; sin GO S04/producción. Fuente de
resultados: [revisión](../../docs/roadmap/SESSION_03_POSTGRES_SECURITY_REVIEW.md) y
artifacts/session-03/postgres-security. No commit/push/merge/release/deploy.
