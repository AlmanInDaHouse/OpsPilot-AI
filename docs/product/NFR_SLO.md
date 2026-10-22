# NFR y SLO — hipótesis, no medidas

Estado: PROPUESTO. Carga inicial: 20 usuarios, 10 workflows activos, 2 workers,
1 acción mutante simultánea por recurso. Host Linux 4 vCPU/8 GiB, SSD, PostgreSQL
local persistente; VPN en host/VM separado. Proveedor LLM externo con cuotas propias.
No hay HA; 99,5 % es objetivo posterior condicionado a operación y restauración.

| ID | Objetivo provisional | Indicador, ventana y validación |
|---|---|---|
| NFR-01 | Disponibilidad API 99,5 %/30 días | Sondas autenticadas cada minuto; errores/timeouts cuentan, incluir mantenimiento; medir S07/S08 |
| NFR-02 | API propia p95 <300 ms; p99 <1 s | 10 req/s, 30 min, excluye IdP remoto/LLM y health; instrumentar servidor y cliente; S08 |
| NFR-03 | Diagnóstico p95 <90 s; workflow automático <180 s | 100 casos, separar tiempo activo, cola y espera humana; LLM timeout 30 s/llamada; S04/S08 |
| NFR-04 | 0 transacciones confirmadas perdidas ante crash de proceso | Kill API/worker con volumen PG intacto, 100 ciclos; no implica tolerar pérdida de disco; S03 |
| NFR-05 | RPO <=15 min, RTO <=60 min ante pérdida host | Backups base + WAL fuera del host, restore cronometrado y verificaciones; S08; sin este sistema no se afirma RPO |
| NFR-06 | 0 invocaciones sin autorización en suite adversaria | 100 % casos críticos de CONTROL_MATRIX, acceso revocado, replay y carrera; S02/S05 |
| NFR-07 | Reclamar trabajo seguro en <=90 s tras crash | Lease 60 s, poll 2 s, reconciliación; acciones desconocidas se bloquean, no repiten; S03 |
| NFR-08 | 10 workflows/2 workers sin duplicar efectos | 100 workflows concurrentes más fallos; latencia de cola p95 <5 s para pasos listos; S03/S08 |
| NFR-09 | 100 % transiciones/acciones con evento atómico | Reconciliar DB: estado, version y seq; export diario de hashes anclado fuera DB; S03/S08 |
| NFR-10 | RAG recall@5 >=0,85 con ACL correcta 100 % | >=50 preguntas etiquetadas por autor, separar train/golden; medir bootstrap CI, casos ACL negativos; S04 |
| NFR-11 | >=0,95 afirmaciones sustentadas; 0 falsos cierres en golden | Revisión humana de citas por afirmación y test negativo VPN; reportar tamaño/intervalos; S04/S06 |
| NFR-12 | <=1 EUR/ejecución de diagnóstico, sin espera humana | Tarifa versionada, input/output/embedding + retries; medir p95 y gasto real; gate antes S04 |
| NFR-13 | <=12 000 input + 4 000 output tokens acumulados/workflow | Contador persistido/reserva pesimista, 6 llamadas máximo, 10 herramientas, 5 min tiempo activo; S04/S05 |
| NFR-14 | 100 % pasos con IDs; >=99 % spans exportados en carga nominal | audit exhaustivo, trazas muestreadas aparte, prueba caída collector, sin secretos; S07 |

Los límites de presupuesto son duros; objetivos de latencia son blandos. Límite
de output por llamada 1 000 tokens; reservar antes de llamar y liquidar después.
Usage desconocido consume toda reserva y bloquea si no cabe otra llamada. Esperas
humanas caducan a 15 min sin consumir presupuesto de tiempo activo. Ajustar objetivos
solo mediante ADR con carga, muestras y coste publicados; no relajar controles críticos.
