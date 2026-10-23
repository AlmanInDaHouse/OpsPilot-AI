# S02 — remediación de seguridad (2026-10-23)

Petición del autor: resolver NO-GO sin excepciones, sin S03 ni publicación.
Baseline: HEAD f165a47b29c22474750be145e5a4caeabd0dc367, main y origin/main
coincidentes; árbol limpio antes de editar. No trabajo ajeno modificado.

Alcance: REQ-PLAT-01/02 y REQ-HAR-01 → T02-01/05/07/08 →
TEST-02-SUPPLY/AUTH/AUDIT/MIGRATE/CONTRACT/ARCH. Se conserva el contrato HTTP.
Dependencias: Docker Linux local disponible, Python/uv del lock, PG/Keycloak reales,
registro oficial y avisos actuales de los proveedores. Sin credenciales externas.

Supuestos previos a implementación: una versión anunciada no demuestra disponibilidad
del binario ni corrección del trust store; un digest nuevo exige inventario y scan.
Un JDK alternativo debe estar mantenido y soportado por Keycloak; no basta con que
el scanner deje de reconocer el paquete. No se modifica CA/JVM sin procedencia y
corrección verificables. Los resultados históricos se conservan como históricos.

CI posterior al push: harness PASS; quality Windows/Ubuntu PASS; integración
funcional 50 PASS; PostgreSQL fresco FAIL en psql; recovery/scan omitidos por ese
fallo. Investigar la carrera de arranque antes de cambiar la prueba. El fallo no
demuestra por sí solo defecto del servidor PG. La CI remota seguirá fallida hasta
una ejecución real posterior; esta petición no autoriza push ni dispatch remoto.

Resultados de investigación, pruebas y decisión: ver el informe de remediación
en docs/roadmap/SESSION_02_SECURITY_REMEDIATION.md al cerrar este trabajo.

Resultado: derivada Alpine/Temurin implementada según ADR-0007, inputs fijados;
176 tests Windows y Linux PASS, PG fresco/recovery/scans finales PASS. Original y
candidato Debian fallidos se conservan. No edición manual de certificados. La
compatibilidad se limita al laboratorio linux/amd64 probado. NO-GO S03 por CI
remota pendiente de este árbol; sin publicación, S03 ni aceptación implícita.
