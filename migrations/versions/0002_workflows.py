"""T03-02: durable local workflow storage and versioned closed audit boundary."""

from pathlib import Path

from alembic import op

revision = "0002_workflows"
down_revision = "0001_platform"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for filename in ("0002_workflows.sql", "0002_workflow_functions.sql"):
        source = (Path(__file__).parents[1] / "sql" / filename).read_text(encoding="utf-8")
        op.get_bind().exec_driver_sql(source, execution_options={"no_parameters": True})


def downgrade() -> None:
    raise RuntimeError("Destructive downgrade prohibited; use forward migrations")
