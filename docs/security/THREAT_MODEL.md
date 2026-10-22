# Threat model por componentes y límites

Estado: PROPUESTO, controles NO implementados. Activos: secretos, credenciales de lab,
documentos, integridad de acciones/aprobaciones, identidad, disponibilidad y audit.
Adversarios: usuario autenticado malicioso, documento/tool comprometido, proveedor,
dependencia maliciosa y administrador con privilegios DB/host. Límites en [C4](../architecture/C4.md).
Prioridades P0 bloquean cualquier piloto; P1 bloquean RC salvo excepción motivada del autor.

| ID / prioridad | Componente, cruce y ataque | Control concreto / prueba requerida |
|---|---|---|
| TH-01 / P0 | Ticket/documento→context→LLM, prompt injection (LLM01) | Datos delimitados, ACL, salida estricta y ninguna autoridad de ejecución; adversario pide restart/exfiltración y no hay envío |
| TH-02 / P0 | Tool→modelo, output injection/confused deputy | Resultados redacted con procedencia, sin HTML/comandos; policy usa identidad iniciadora y actor actual, jamás texto de tool |
| TH-03 / P0 | Modelo→runner, exceso de agencia/tool abuse (LLM05/06) | Catálogo fijo, schema/semántica, resource allowlist, sin shell/URL libre, budgets y egress; rechazar tool desconocida y args extra |
| TH-04 / P0 | Browser→API, escalada de privilegio/transición no autorizada | JWT RS256 issuer/aud, permisos locales frescos; no endpoint set_state; token adulterado y operador leyendo audit denegados |
| TH-05 / P0 | UI→approval→dispatch, replay y TOCTOU | Snapshot immutable, hash+version+nonce, TTL DB, tercero, revalidar al enviar bajo locks; carrera revoke/expiry/replay |
| TH-06 / P0 | PG→runner→VPN, duplicado tras crash | Intent UNIQUE y operation_id, fencing local, UNKNOWN y cuarentena; matar proceso después de efecto antes de persistir, ningún reenvío |
| TH-07 / P0 | RAG/LLM→internet, secretos y fuga (LLM02/07) | ACL antes de ranking, minimizar contexto, sin secretos en prompts/sistema, red allowlist; canary secret no aparece en requests/logs |
| TH-08 / P1 | Ingestion→embeddings, poisoning/vector leakage (LLM04/08) | Ingestión aprobada, hash/version, revocar ACL/caché, dataset etiquetado; documento sin permiso nunca recuperado ni citado |
| TH-09 / P0 | Tool/modelo→informe, misinformation (LLM09) | Citas verificables, diagnóstico provisional, verifier independiente y cierre humano; restart con VPN aún rota no resuelve ticket |
| TH-10 / P1 | API/LLM→budget, consumo ilimitado (LLM10) | Límites persistidos/reservas atómicas, timeout/429, body/rate limits, cuotas por deploy; carreras no exceden budget |
| TH-11 / P1 | Registry/CI→build, supply chain (LLM03) | Lock hash, imágenes digest, revisión origen/licencia, SCA/secret scan, SBOM, acciones CI SHA; dependencia vulnerable bloquea gate |
| TH-12 / P0 | App/admin→PG audit, tampering | Roles sin UPDATE/DELETE, append function, hashes+seq y ancla externa S08; delete/reorder/modificación detectable; admin total sigue residual |
| TH-13 / P0 | Host→execution plane, credencial/socket expuesto | Sin mount host, Docker socket ni privilegio global; runner role y red restringidos; intentar lectura de documentos y escritura fuera catálogo falla |
| TH-14 / P1 | IdP/JWKS→API, SSRF/key confusion | Issuer/JWKS fijos, `kid` refresh limitado, no jku/x5u, alg allowlist; token HS/none/URL atacante no provoca fetch |
| TH-15 / P0 | Restore→runner, acciones repetidas desde backup | Intake/mutación pausados, reconciliar intents con sistema real y renovar aprobación; restore no produce efectos automáticamente |
| TH-16 / P1 | UI/logs/traces, XSS y privacidad | Escapar texto, CSP, tokens memoria, no cuerpos/logging de secretos, redaction tests y retención; payload hostil no ejecuta script |

OWASP LLM Top 10 2025 es referencia de amenazas, no certificación. Riesgos específicos
de agentes añadidos: identidad delegada ambigua, tool chaining que cruza privilegios,
persistencia de memoria envenenada, dependencia humana excesiva de diagnósticos y
agotamiento de aprobación. Primer vertical usa un agente acotado sin memoria entre
tickets, sin delegación autónoma y con pantalla de evidencia/riesgo antes de aprobar.
Un humano puede aprobar mal: UI debe presentar recurso, acción, evidencia, impacto y TTL.

Abuso interno DB/host, vulnerabilidad kernel del lab y proveedor LLM malicioso no quedan
eliminados por el diseño. Aislamiento, minimización y anclas reducen impacto; aceptar
residuales requiere responsable y alcance del piloto. Fuentes: [catálogo](../engineering/SOURCES.md).
