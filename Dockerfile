FROM ghcr.io/astral-sh/uv:0.13.5@sha256:32a7bb39b496babbd997b0a39a4d66c126bdaf5661b302bf6f06abda8deca6ff AS uv
FROM python:3.13.14-alpine3.24@sha256:399babc8b49529dabfd9c922f2b5eea81d611e4512e3ed250d75bd2e7683f4b0 AS python
RUN apk add --no-cache libcrypto3=3.5.9-r0 libssl3=3.5.9-r0 libuuid=2.42.3-r1
FROM python AS base
COPY --from=uv /uv /uvx /usr/local/bin/
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml uv.lock ./

FROM base AS build
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-editable

FROM python AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
RUN addgroup -g 10001 -S opspilot && adduser -u 10001 -S -D -H -G opspilot opspilot
COPY contracts ./contracts
USER 10001:10001
CMD ["/app/.venv/bin/uvicorn", "opspilot.entrypoints.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--no-server-header", "--timeout-keep-alive", "5"]

FROM base AS test
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-install-project
RUN apk add --no-cache git=2.54.0-r0 && addgroup -g 10001 -S opspilot && adduser -u 10001 -S -D -H -G opspilot opspilot
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen
ENV UV_CACHE_DIR=/tmp/uv-cache
USER 10001:10001
CMD ["/app/.venv/bin/python", "-m", "pytest", "-m", "not integration", "-q"]
