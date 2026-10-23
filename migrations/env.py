"""Explicit migrator credentials supplied by file; no URL in Alembic output."""

import os
import re
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

from opspilot.adapters.postgres.models import Base

dsn = Path(os.environ["OPSPILOT_MIGRATION_DSN_FILE"]).read_text(encoding="utf-8").strip()
target = make_url(dsn)
if (
    target.drivername != "postgresql+psycopg"
    or target.username != "opspilot_migrator"
    or target.host not in {"127.0.0.1", "postgres"}
    or target.port not in {59432, 5432}
    or target.query
    or not re.fullmatch(r"opspilot_(lab|test_[0-9a-f]{32})", target.database or "")
):
    raise ValueError("S02 migrations require the dedicated, explicitly configured lab database")
engine = create_engine(dsn, hide_parameters=True)
with engine.connect() as connection:
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()
engine.dispose()
