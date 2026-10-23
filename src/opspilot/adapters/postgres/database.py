"""Bounded PostgreSQL sessions and explicit UoW. No auto-migration."""

from types import TracebackType
from typing import Self

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from opspilot.adapters.postgres.models import SCHEMA_VERSION
from opspilot.shared.errors import DependencyUnavailable
from opspilot.shared.uow import UnitOfWork


def make_engine(dsn: str, timeout_ms: int = 5000) -> Engine:
    return create_engine(
        dsn,
        pool_size=5,
        max_overflow=5,
        pool_timeout=min(5, max(1, timeout_ms / 1000)),
        pool_pre_ping=True,
        hide_parameters=True,
        connect_args={
            "connect_timeout": 2,
            "options": f"-c statement_timeout={timeout_ms} -c lock_timeout={timeout_ms} -c timezone=UTC",
        },
    )


def database_ready(engine: Engine) -> bool:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            return connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalars().all() == [SCHEMA_VERSION]
    except SQLAlchemyError:
        return False


class PostgresUow(UnitOfWork):
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions
        self.session: Session

    def __enter__(self) -> Self:
        self.session = self._sessions()
        self.session.begin()
        return self

    def commit(self) -> None:
        self.session.commit()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        try:
            self.session.rollback()
        finally:
            self.session.close()


def require_database(engine: Engine) -> None:
    if not database_ready(engine):
        raise DependencyUnavailable()
