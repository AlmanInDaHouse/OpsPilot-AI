FROM ghcr.io/astral-sh/uv:0.11.13@sha256:841c8e6fe30a8b07b4478d12d0c608cba6de66102d29d65d1cc423af86051563 AS uv
FROM python:3.15.0-alpine3.24@sha256:2699b90f4d562a22e2dd076c82f964032f64814204bff36d271a54ba4cc2c7e2 AS python
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
