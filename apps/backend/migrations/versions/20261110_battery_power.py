"""Track battery power integration baselines separately from energy counters."""

from alembic import op
import sqlalchemy as sa

revision = "20261110_battery_power"
down_revision = "20261110_replacements"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "energy_power_snapshots",
        sa.Column(
            "device_id", sa.Uuid(), sa.ForeignKey("devices.id"), primary_key=True
        ),
        sa.Column("channel", sa.String(30), primary_key=True),
        sa.Column("power_w", sa.Numeric(18, 6), nullable=False),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("power_w >= 0", name="ck_energy_power_nonnegative"),
    )


def downgrade():
    op.drop_table("energy_power_snapshots")
