"""FastAPI composition root; routes call use cases through explicit ports."""

import asyncio
import json
import logging
import re
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Annotated, Any
from uuid import UUID, uuid4

import httpx
from fastapi import Depends, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import sessionmaker
from starlette.exceptions import HTTPException

from opspilot.adapters.oidc.verifier import OidcVerifier
from opspilot.adapters.postgres.audit import PostgresAuditReader
from opspilot.adapters.postgres.database import database_ready, make_engine, require_database
from opspilot.adapters.postgres.identity import PostgresPrincipals
from opspilot.audit.application.ports import AuditReader
from opspilot.entrypoints.api.dto import AuditPage, Error, Health, Me
from opspilot.entrypoints.settings import Settings
from opspilot.identity.application.authenticate import PrincipalReader, TokenVerifier, authenticate
from opspilot.identity.domain.principal import Principal
from opspilot.shared.errors import DependencyUnavailable, Forbidden, Unauthenticated

LOGGER = logging.getLogger("opspilot.requests")
SECURITY = HTTPBearer(auto_error=False, scheme_name="bearerAuth", bearerFormat="JWT")


def platform_api(
    verifier: TokenVerifier,
    principals: PrincipalReader,
    audit: AuditReader,
    ready: Callable[[], bool],
    schema_valid: Callable[[], None],
    lifespan: Any = None,
) -> FastAPI:
    app = FastAPI(
        title="OpsPilot platform",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    class CheckedPrincipals:
        def find(self, identity: Any) -> Principal | None:
            schema_valid()
            return principals.find(identity)

    checked_principals = CheckedPrincipals()
    protected_errors: dict[int | str, dict[str, Any]] = {
        code: {"model": Error} for code in (401, 403, 503)
    }

    def error(request: Request, code: str, status: int) -> JSONResponse:
        request.state.outcome = code
        return JSONResponse(
            {"code": code, "request_id": request.state.request_id},
            status_code=status,
            headers={"WWW-Authenticate": "Bearer"} if status == 401 else {},
        )

    @app.middleware("http")
    async def correlation(request: Request, call_next: Any) -> Any:
        started = time.monotonic()
        request.state.request_id = str(uuid4())
        parent = request.headers.get("traceparent", "")
        match = re.fullmatch(r"00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})", parent)
        request.state.trace_id = (
            match[1] if match and int(match[1], 16) and int(match[2], 16) else uuid4().hex
        )
        request.state.actor_id = None
        request.state.outcome = "OK"
        try:
            async with asyncio.timeout(10):
                # Bound actual bytes and elapsed time, including slow body streams.
                total = 0
                async for chunk in request.stream():
                    total += len(chunk)
                    if total > 16384:
                        break
                if total > 16384 or len(request.headers.getlist("authorization")) > 1:
                    response = error(request, "INVALID_REQUEST", 422)
                else:
                    response = await call_next(request)
        except Exception:
            # Dependency exceptions are mapped below; unknown failures never reflect input.
            response = error(request, "DEPENDENCY_UNAVAILABLE", 503)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        route = request.scope.get("route")
        LOGGER.info(
            json.dumps(
                {
                    "action": "http.request",
                    "request_id": request.state.request_id,
                    "trace_id": request.state.trace_id,
                    "actor_id": request.state.actor_id,
                    "route": getattr(route, "path", "unmatched"),
                    "method": request.method,
                    "result": request.state.outcome,
                    "status": response.status_code,
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "duration_ms": round((time.monotonic() - started) * 1000),
                }
            )
        )
        return response

    @app.exception_handler(Unauthenticated)
    async def unauthenticated(request: Request, exc: Unauthenticated) -> JSONResponse:
        return error(request, "UNAUTHENTICATED", 401)

    @app.exception_handler(Forbidden)
    async def forbidden(request: Request, exc: Forbidden) -> JSONResponse:
        return error(request, "FORBIDDEN", 403)

    @app.exception_handler(DependencyUnavailable)
    async def unavailable(request: Request, exc: DependencyUnavailable) -> JSONResponse:
        return error(request, "DEPENDENCY_UNAVAILABLE", 503)

    @app.exception_handler(RequestValidationError)
    async def invalid(request: Request, exc: RequestValidationError) -> JSONResponse:
        return error(request, "INVALID_REQUEST", 422)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        return error(request, "INVALID_REQUEST", exc.status_code)

    def actor(
        request: Request,
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(SECURITY)],
    ) -> Principal:
        if credentials is None:
            raise Unauthenticated()
        # Verify JWT before requiring DB, then check exact schema and fresh local identity.
        principal = authenticate(credentials.credentials, verifier, checked_principals)
        request.state.actor_id = str(principal.id)
        return principal

    @app.get("/health/live", operation_id="liveness", response_model=Health)
    def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get(
        "/health/ready",
        operation_id="readiness",
        response_model=Health,
        responses={503: {"model": Error}},
    )
    def readiness() -> dict[str, str]:
        if not ready():
            raise DependencyUnavailable()
        return {"status": "ok"}

    @app.get("/v1/me", operation_id="getMe", response_model=Me, responses=protected_errors)
    def me(principal: Annotated[Principal, Depends(actor)]) -> dict[str, Any]:
        return {"principal_id": str(principal.id), "roles": sorted(principal.roles)}

    @app.get(
        "/v1/audit-events",
        operation_id="listAuditEvents",
        response_model=AuditPage,
        responses={**protected_errors, 422: {"model": Error}},
    )
    def events(
        principal: Annotated[Principal, Depends(actor)],
        stream_id: UUID,
        after_seq: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
    ) -> dict[str, Any]:
        principal.require_audit_read()
        page = audit.list_events(stream_id, after_seq, limit)
        return {"items": page.items, "next_after_seq": page.next_after_seq}

    return app


def create_app() -> FastAPI:
    settings = Settings()  # type: ignore[call-arg]
    engine = make_engine(settings.database_dsn.get_secret_value(), settings.db_timeout_ms)
    sessions = sessionmaker(engine)
    client = httpx.Client(
        timeout=settings.http_timeout_seconds, trust_env=False, follow_redirects=False
    )
    verifier = OidcVerifier(
        settings.oidc_issuer,
        settings.oidc_audience,
        settings.oidc_jwks_url,
        client,
        settings.jwks_ttl_seconds,
        settings.jwks_refresh_seconds,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        LOGGER.addHandler(handler)
        LOGGER.setLevel(logging.INFO)
        try:
            yield
        finally:
            LOGGER.removeHandler(handler)
            engine.dispose()
            client.close()

    return platform_api(
        verifier,
        PostgresPrincipals(sessions),
        PostgresAuditReader(sessions),
        lambda: database_ready(engine) and verifier.ready(),
        lambda: require_database(engine),
        lifespan,
    )
