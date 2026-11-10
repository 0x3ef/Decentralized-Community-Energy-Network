"""Expose household load separately from signed net grid power."""

from alembic import op
import sqlalchemy as sa

revision = "20261110_load_power"
down_revision = "20261110_iot_quality"
branch_labels = depends_on = None


def upgrade():
    op.add_column("smart_meter", sa.Column("consumption_power_w", sa.Numeric(12, 3)))


def downgrade():
    op.drop_column("smart_meter", "consumption_power_w")
