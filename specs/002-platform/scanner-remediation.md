# S02 — remediación del scanner CI

2026-10-23. REQ-HAR-01 / REQ-PLAT-01 → T02-07/08 → AC02-08.
Base publicada b221037; preservar documentación local y closure-b221037 históricos.
No S03, commit, push, dispatch remoto ni cambios en contratos o imágenes.

## Diagnóstico y supuestos anteriores al cambio

Ubuntu WSL2, host UID/GID 1000:1000, scanner fijado UID/GID 10001:10001:
bind mounts 0755 propiedad de 1000 impiden crear archivos en salida y caché.
Reproducido en esta sesión con exit 1 y Permission denied en ambas rutas.
Confirma el defecto POSIX; stderr remoto de Trivy ausente impide atribuir con
certeza el run 39888916474. Descargas/timeout son fallos distintos.
Docker Desktop Linux está disponible; Python/uv fijados, lab existente detenido.

## Cambio acotado y aceptación

- scripts/scan_images.py: staging temporal exclusivo, archivo tar solo lectura,
  salida y caché separadas, usuario efectivo no root en Linux; UID 10001 en
  Windows sujeto a preflight real. Nunca montar artifacts/local ni socket.
- Probe fijo con identidad, owner/modo, lectura real y escrituras reales; comprobar
  aislamiento. No inferir permisos solo de bits POSIX en Docker Desktop.
- Errores normalizados, returncode original, logs privados únicos y hashes;
  publicación limitada a campos permitidos, sin copiar líneas arbitrarias del log.
- JSON ausente/corrupto/incompleto, runtime/timeout e identidad incorrecta bloquean.
  HIGH/CRITICAL fallan; comparar inspect, config del tar e ImageID del informe.
- Workflow: conservar fallos y subir solo evidencia nueva saneada ligada a revisión
  y árbol; nunca todo artifacts/local ni snapshots históricos como evidencia actual.
- tests/unit/test_image_scan_gate.py y probe Docker real: negativos de permisos,
  runtime, timeout, JSON, CVE, identidad y contención. Fakes solo en unit tests.

Ejecutar harness/check y suites completas Windows/Linux con PG/IdP reales, fresh PG,
recovery y tres scans. Evidencias nuevas bajo artifacts/session-02/scanner-remediation;
logs ignorados bajo artifacts/local. Manifest con HEAD y hashes del árbol sin
confundir cambios sin commit con el SHA publicado. NO-GO hasta CI remota del nuevo
commit satisfactoria; no se autoriza publicarlo en esta petición.

## Resultados y diferencias verificadas

Informe: [remediación](../../docs/roadmap/SESSION_02_SCANNER_REMEDIATION.md).
Docker Desktop containerd devuelve índice OCI: se verifica cada digest hasta el
config y su igualdad con Trivy; Docker clásico conserva comparación directa.
TMPDIR usa cache/tmp: la DB real excedió el tmpfs de 256 MiB del primer intento.
Los intentos fallidos se conservan. Probes 4 Windows/8 Ubuntu PASS; suites completas
212 por OS con 50 integraciones reales; PG fresco/recovery PASS. Ver acceptance
nuevo para los scans finales, integridad, quality gates y NO-GO explícito.
