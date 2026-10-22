# Alcance inicial y supuestos

Estado: PROPUESTO; nada de producto IMPLEMENTADO en sesión 01.

## Vertical comprometido

Una organización por despliegue, un realm OIDC, un laboratorio VPN WireGuard,
un proveedor LLM y un formato documental inicial (Markdown UTF-8 aprobado por operador).
Un workflow lineal versionado, sin motor genérico de DAG, con una propuesta mutante
por ejecución. Lecturas: estado de servicio y prueba de conectividad. Única mutación:
reiniciar el servicio VPN allowlisted del laboratorio tras aprobación humana ajena.
Una verificación independiente abre un túnel real y prueba acceso a recurso interno.
No gestionar claves VPN ni usuarios desde el agente.

La selección WireGuard es provisional hasta spike de sesión 06: servicio Linux
aislado sin Docker socket accesible al producto; claves preaprovisionadas fuera de
Git. Si requiere privilegios del kernel, usar VM/red dedicadas, no contenedor
privilegiado en host de uso general. Puede reducirse el panel/ingestión, nunca
eliminar idempotencia, autorización, pruebas o restauración para encajar ocho hitos.

## Fuera de alcance

Multitenancy compartido, Kubernetes, Kafka/Redis, plugins dinámicos de terceros,
shell/SSH arbitrario, acciones en infraestructura corporativa, autoaprobación,
multiagente autónomo, OCR/PDF, sincronización con ITSM y certificación.
Frontend se construye en sesión 07; OpenAPI permite tests HTTP previos.

## Supuestos con gate

| Supuesto | Recomendación y alternativa | Responsable / vencimiento |
|---|---|---|
| Organización sin IdP elegido | Keycloak en laboratorio; IdP corporativo luego por OIDC | Autor, antes T02-02 |
| Docker Desktop apagado | Arranque manual por autor cuando se pida sesión 02; WSL2 o Linux CI alternativo | Autor, antes integración S02 |
| Proveedor y presupuesto desconocidos | Adapter HTTP de un proveedor, región/retención aprobadas antes de enviar datos | Autor, S04 |
| Servicio VPN aún inexistente | WireGuard real en VM aislada; spike de privilegios/red | Autor, S06 |
| Requisitos legales del cliente desconocidos | Datos sintéticos de laboratorio; revisión del caso/roles antes de cliente real | Autor + responsable privacidad, antes uso externo |

## Vocabulario verificable

EXISTENTE: observado antes del cambio. PROPUESTO: decisión o contrato aún no construido.
IMPLEMENTADO: existe código/configuración. PROBADO: se ejecutó un test concreto con
evidencia identificada. VALIDADO: responsable aceptó resultados en entorno y alcance
definidos. Un test del harness PROBADO no convierte runtime PROPUESTO en operativo.
