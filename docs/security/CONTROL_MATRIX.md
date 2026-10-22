# Matriz de controles y aplicabilidad

Todos los controles técnicos de producto están PROPUESTOS. Evidencias futuras bajo
`artifacts/local/`, con resumen redacted versionado y hash de resultados. Ninguna
fila acredita compliance. Autor = responsable técnico hasta asignación empresarial.

| Control | Amenazas / requisito | Implementación prevista | Test/gate y evidencia | Dueño/hito |
|---|---|---|---|---|
| CT-01 | TH-04/14, REQ-PLAT-01 | JWT estricto y grants locales | TEST-02-AUTH: iss/aud/exp/nbf/alg/kid y roles negativos, integración IdP real | Autor S02 |
| CT-02 | TH-12, REQ-PLAT-02 | Appender audit atómico y rol restringido | TEST-02-AUDIT: rollback, UPDATE/DELETE denegados, hash bytes | Autor S02; ancla S08 |
| CT-03 | TH-06, REQ-WF-02/03 | Leases/fences/intent UNKNOWN | TEST-03-CRASH + TEST-05-UNKNOWN: carreras y crash en cada frontera | Autor S03/S05 |
| CT-04 | TH-01/02/07/08, REQ-RAG-01 | ACL+minimización+procedencia | TEST-04-ACL/INJECT: permisos revocados, poisoning, canary y tool output | Autor S04 |
| CT-05 | TH-03/09, REQ-AI-01 | Schema estricto y evidencia por afirmación | TEST-04-EVAL: golden/citas/abstención y presupuesto | Autor S04 |
| CT-06 | TH-03/04/13, REQ-POL-01/TOOL-01 | Gateway default-deny, catálogo y roles/red | TEST-05-POLICY: bypass/args/credencial/red denegados | Autor S05 |
| CT-07 | TH-05, REQ-APR-01 | Hash/nonce/TTL/tercero/revalidación | TEST-05-APPROVAL: revoke/expiry/replay/dispatch concurrentes | Autor S05 |
| CT-08 | TH-09, REQ-VER-01 | Cliente VPN con identidad independiente | TEST-06-VERIFY: restart exitoso con acceso aún roto no cierra | Autor S06 |
| CT-09 | TH-10, REQ-AI-01 | Reservas de budget y límites API | TEST-04-BUDGET y TEST-08-LOAD: concurrencia y exhaustion | Autor S04/S08 |
| CT-10 | TH-11, REQ-REL-01 | Lock/digest/SCA/secrets/SBOM | TEST-02-SUPPLY: lock frozen y scans, bloqueo findings críticos | Autor S02/S08 |
| CT-11 | TH-15, REQ-REL-01 | Backups externos y restore pausado | TEST-08-RESTORE: RPO/RTO y cero mutaciones automáticas | Autor S08 |
| CT-12 | TH-16, REQ-OPS-01 | Logs redacted, CSP, no token persistente | TEST-07-PRIVACY: payload canary y XSS | Autor S07 |

## Aplicabilidad regulatoria: evaluación preliminar

| Referencia | Cómo se usa y qué falta |
|---|---|
| NIST AI RMF | Buenas prácticas voluntarias: Govern (roles/riesgos), Map (uso/impacto), Measure (evals), Manage (gates/incident response). No certifica el producto |
| ISO/IEC 42001:2023 | Referencia a sistema de gestión organizacional de IA; políticas, inventario, revisión, mejora y auditoría. Documentar software no certifica organización; norma completa y evaluación externa pendientes |
| RGPD | Aplicable si se tratan datos personales: ticket/IP/identificador pueden serlo. Responsable/encargado, base jurídica, minimización, contratos proveedor, transferencias/retención y derechos deben definirse antes de datos reales. EIPD según riesgo, no afirmada obligatoria universalmente |
| Reglamento UE IA | Clasificar por finalidad prevista, rol proveedor/desplegador y uso concreto. Este laboratorio IT no demuestra categoría de alto riesgo; uso como componente de seguridad de infraestructura crítica podría cambiarla. Documentar transparencia/supervisión y revisar texto vigente antes de piloto |
| ENS (RD 311/2022) | Evaluar si servicio está en ámbito del sector público español o proveedor sujeto por contrato; categorizar sistema y medidas solo entonces. No es requisito universal de plataforma IT privada ni certificación adquirida |

Consulta: 2026-10-22. La Comisión comunica aplicación general desde 02-08-2026 y
calendarios distintos para alto riesgo (02-12-2027/02-08-2028); no se usa un calendario
histórico como sustituto de revisar normativa consolidada y rol contractual. Fuentes
primarias enlazadas en [SOURCES](../engineering/SOURCES.md). Jurisdicción, finalidad y
contratos desconocidos: responsable privacidad/legal con autor debe cerrar evaluación
antes de uso empresarial. Laboratorio solo con datos sintéticos y sin envío de secretos.

No existen todavía medidas operativas, evaluación de conformidad ni certificaciones.
