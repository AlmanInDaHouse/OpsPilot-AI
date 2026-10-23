# S03 — arranque autorizado y alcance de T03-01

2026-10-23, Europe/Madrid. Petición del autor: «empieza la sesion 03».
Autoriza iniciar S03 localmente. No acredita por sí sola revisión humana del
diff/riesgos S02 ni aprobación de los contratos todavía no escritos.

## Inspección y dependencias

- Git inicial limpio en main, HEAD 3b91f58; base técnica S02 660f7d3.
- GO técnico documentado en SESSION_02_CLOSURE; aceptación humana pendiente.
- Python 3.13.14, uv y Docker disponibles. `check` inicial PASS.
- Primer `test`: 162 PASS, 2 FAIL y 48 ERROR; PG/IdP estaban detenidos.
  No se altera el gate. Se arrancan solo los tres contenedores existentes del lab
  opspilot-s02, conservando volumen, imágenes y credenciales, y se repite la suite.

## Tarea seleccionada y supuestos

REQ-WF-01/02 y guardas de REQ-WF-03; T03-01: preparar el contrato revisable de
intake, lecturas, cancelación, eventos, snapshot y permisos. Es la primera tarea
acotada; T03-02 depende de ella. Sin nueva dependencia ni cambios al runtime S02.
Los contratos nuevos son especificación ejecutable mediante validadores y tests,
no endpoints ni migraciones implementados. Los tests no prueban durabilidad S03.

Se conservan todos los registros de idempotencia durante S03; no hay limpieza
automática ni política de borrado aceptada. Solo datos sintéticos. La evidencia
local omite texto libre: conserva referencias/versiones y hashes, nunca contenido
arbitrario del ticket. No demuestra diagnóstico ni resolución.

La revisión humana previa a código se exige en SESSION_03_SPEC, sección Entrada
y exclusiones. Se prepara primero el paquete concreto de contratos y decisiones
para esa revisión. No se marca aceptación humana, T03-01 completa ni GO S04 por
decisión del asistente. T03-02..08 permanecen pendientes hasta cerrar esa entrada.
