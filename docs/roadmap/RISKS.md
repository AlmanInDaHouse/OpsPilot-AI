# Registro de riesgos y decisiones abiertas

Estado: evaluación de diseño, no incidentes de producción. Autor = responsable técnico.
Prioridad crítica implica NO-GO en hito indicado si no se resuelve. Alternativas no
autorizan cambios externos ni reejecución de operaciones ambiguas.

| ID / prioridad | Riesgo, impacto y alternativas | Mitigación / dueño / gate |
|---|---|---|
| R01 / crítica | Motor propio introduce carreras/pérdida; Temporal reduce código a cambio de servicio extra | Flujo lineal, suite crash/fence/PG; autor S03, NO-GO S04 si falla |
| R02 / crítica | Efecto remoto ambiguo y duplicados tras caída | Intent único, operation_id durable externo, UNKNOWN/cuarentena; autor S05/S06 |
| R03 / alta | Docker daemon no disponible; integración S02 no ejecutable ahora | Iniciar entorno al solicitar S02 o Linux CI; autor antes T02-04; no sustituir por fake |
| R04 / alta | IdP de lab/provisión y grants aún no construidos | Keycloak recomendado, config repetible y negativos; IdP corporativo alternativa; autor T02-02 |
| R05 / alta | Hash audit local no resiste DB admin; canonicalización incorrecta rompe integridad | SQL canonicalizer con golden bytes, roles; ancla externa S08; autor T02-04/S08 |
| R06 / crítica | Privilegios/red WireGuard contaminan host o verifier comparte fallo | VM dedicada, cliente separado y servicio con credencial mínima; autor S06; no privileged general |
| R07 / alta | Proveedor LLM/región/retención/coste sin elegir | Un adapter, revisión de datos/contrato y budget antes de enviar; autor + privacidad S04 |
| R08 / alta | ACL RAG/caches revelan documentos internos | ACL previo ranking y revocación, tests negativos; autor S04 |
| R09 / alta | Ocho sesiones no bastan con UI/ingestión amplias | Un vertical, un formato, una mutación; reducir pantallas antes de seguridad; autor revisión S03 y S06 |
| R10 / alta | Host/PG SPOF; SLO/RPO solo hipótesis | Backup externo+WAL/restore real; HA futura por ADR; autor S08; no anunciar disponibilidad medida |
| R11 / alta | Ámbito legal/tenant desconocido | Single-tenant, sintéticos, evaluación caso/rol/contratos; autor + privacidad antes piloto externo |
| R12 / media | Spec Kit no instalado, compatibilidad solo declarada | SDD stdlib usable; opcional scratch pin 1.2.3 sin overwrite; autor cuando aporte valor |
| R13 / media | Mermaid no renderizado y checks no prueban semántica | Revisión humana; render toolchain fijada S02; autor antes publicar diagramas |
| R14 / alta | Worker antiguo puede ejecutar después de revoke/cancel tras envío | Revalidar bajo locks antes dispatch; efecto ya enviado se reconcilia, no se promete revocación física; autor S05 |

Decisiones de aislamiento/entrega/autorización están fijadas en ADR. IdP/proveedor/lab
son elecciones provisionales con gates explícitos; no se necesita inventar requisitos
de cliente para completar S01. Validación de uso empresarial queda fuera de esta entrega.
