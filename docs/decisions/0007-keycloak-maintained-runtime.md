# ADR-0007 — runtime mantenido para Keycloak de laboratorio

Estado: aceptado para implementación y pruebas locales S02, 2026-10-23.
No es autorización S03, release ni despliegue. REQ-PLAT-01/02, T02-01/05/07/08.

Contexto: Keycloak oficial 26.8.1 conserva su digest vulnerable; 26.8.2 no existe.
Los repositorios públicos UBI9 ofrecen las mismas versiones afectadas de CA/JVM.
La derivada Debian 12 ensayada introduce otros altos/críticos sin parche y se rechaza.
Azul anuncia una actualización, pero los canales públicos consultados no la sirven.

Decisión: conservar exclusivamente /opt/keycloak del digest oficial y construir una
derivada local con Alpine 3.24.3 por digest, ca-certificates 20261020-r0 y Eclipse
Temurin 21.0.13+9 para musl, archivo oficial fijado por SHA-256. Fijar versiones
directas de paquetes. No copiar JVM/RPM antiguos, editar certificados, excluir CVE,
quitar metadatos de paquetes ni cambiar políticas de validación TLS.
La base y los paquetes usan los repositorios firmados de Alpine; el archivo Temurin
se contrasta con el digest de la release oficial y su metadata del proveedor.

Keycloak soporta OpenJDK 21 y Linux; Alpine/musl no es su imagen oficial UBI ni una
certificación del proveedor. La compatibilidad de esta derivada requiere PKCE/OIDC,
RBAC, PG real, auditoría y restart, con los mismos límites, UID 1000 y capabilities.
La receta se limita explícitamente a linux/amd64; no anunciar otras arquitecturas.
El tag local identifica el build; los manifiestos registran config/OCI digest exactos.

CA del sistema y Java son almacenes distintos. La corrección del paquete Alpine
no basta para Java. El archivo Temurin inspeccionado excluye las cuatro raíces del
inventario del incidente; verificar el archivo musl final también. Mantener positivos
de confianza y negativos de las 14 cadenas públicas. El original también rechaza
esas cadenas en este entorno: esos negativos solos no demuestran una explotación
ni son prueba diferencial de remediación. Inventario, procedencia y avisos complementan
el scanner, que puede no identificar CVE de un JRE distribuido como archivo.

Alternativas: esperar un rebuild oficial UBI es la opción preferida cuando exista;
Temurin en Debian estable exige resolver sus otros CVE; Debian sid no se incorpora
a runtime estable; no usar nightly, mezclar RPM entre distribuciones ni aplicar
blocklists de otro proveedor a mano. Cambiar a un JDK soportado no sustituye las pruebas.

Coste: el autor mantiene esta derivada, parches y hashes; revisar cada actualización
del IdP/JVM/CA y volver a la imagen oficial cuando supere los mismos gates.
Aceptación exige scan final de todas las imágenes, suite Windows/Linux, recovery,
PG fresco y CI remota de la revisión final. Ningún PASS local puede emitir GO global.
Resultados efectivos en SESSION_02_SECURITY_REMEDIATION y artifacts/session-02/remediation.
