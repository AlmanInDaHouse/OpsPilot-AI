# ADR-0005 — stack y plataforma inicial

Estado: aceptado para diseño, 2026-10-22. Python 3.13 + FastAPI/Pydantic 2, PostgreSQL 18,
SQLAlchemy 2/psycopg 3/Alembic, React/TypeScript en S07, OIDC con Keycloak de laboratorio,
Compose y Linux CI, OpenTelemetry progresivo. Versiones exactas/locks/digests en S02.

Contexto: contratos HTTP/JSON, ecosistema Python AI y una base para datos/vector/jobs.
Alternativas Django, Go, SQLite, vector DB separada y Kubernetes analizadas en arquitectura.
Se eligen dependencias por función, no por popularidad; sin Redis/Kafka/agent framework.

OIDC autentica, grants locales autorizan; no confiar en roles emitidos por modelo o
claims sin mapeo. Single host limita disponibilidad; backup externo y restore probado
antes de RC. Costes: mantener ACL/grants/versiones y upgrade de PG/pgvector; dependencia
externa del IdP/LLM. Keycloak no es IdP corporativo elegido ni servicio desplegado.
Validación: Linux y Windows/WSL CI S02, golden RAG S04, restore/carga S08.
