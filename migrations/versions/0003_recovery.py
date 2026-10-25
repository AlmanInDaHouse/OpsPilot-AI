"""T03-06: durable per-job active accounting; no new runtime grants."""

from pathlib import Path

from alembic import op

revision = "0003_recovery"
down_revision = "0002_workflows"
branch_labels = None
depends_on = None


def upgrade() -> None:
    source = (Path(__file__).parents[1] / "sql/0003_recovery.sql").read_text(encoding="utf-8")
    op.get_bind().exec_driver_sql(source, execution_options={"no_parameters": True})


def downgrade() -> None:
    raise RuntimeError("Destructive downgrade prohibited; use forward migrations")
