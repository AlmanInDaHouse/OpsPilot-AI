"""S02 identity and durable audit, with least privilege at the database boundary."""

from pathlib import Path

from alembic import op

revision = "0001_platform"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    sql = (Path(__file__).parents[1] / "sql" / "0001_platform.sql").read_text(encoding="utf-8")
    op.get_bind().exec_driver_sql(sql, execution_options={"no_parameters": True})


def downgrade() -> None:
    raise RuntimeError("Destructive downgrade prohibited; use forward migrations")
