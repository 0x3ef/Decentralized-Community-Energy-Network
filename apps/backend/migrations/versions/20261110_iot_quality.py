"""Add commissioned sources, simulation consent and durable telemetry quality audit."""

from alembic import op
import sqlalchemy as sa

revision = "20261110_iot_quality"
down_revision = "20261110_native_pipeline"
branch_labels = depends_on = None


def upgrade():
    for field in ("cumulative_charge_wh", "cumulative_discharge_wh", "capacity_wh"):
        op.add_column("battery", sa.Column(field, sa.BigInteger()))
    op.add_column("telemetry_messages", sa.Column("message_id", sa.Uuid()))
    op.create_unique_constraint(
        "uq_telemetry_device_message", "telemetry_messages", ["device_id", "message_id"]
    )
    op.add_column(
        "devices",
        sa.Column(
            "telemetry_source", sa.String(20), nullable=False, server_default="PHYSICAL"
        ),
    )
    op.add_column("devices", sa.Column("counter_modulus_wh", sa.BigInteger()))
    op.add_column(
        "energy_communities",
        sa.Column(
            "allow_simulated_telemetry",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_table(
        "telemetry_assessments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("fingerprint", sa.String(64), nullable=False, unique=True),
        sa.Column("device_id", sa.Uuid(), sa.ForeignKey("devices.id")),
        sa.Column("claimed_device_id", sa.String(100), nullable=False),
        sa.Column("sequence_number", sa.BigInteger()),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("state", sa.String(30), nullable=False),
        sa.Column("reason", sa.String(300), nullable=False),
        sa.Column("occurrences", sa.Integer(), nullable=False),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_telemetry_assessments_device_id", "telemetry_assessments", ["device_id"]
    )
    op.create_index(
        "ix_telemetry_assessments_state", "telemetry_assessments", ["state"]
    )


def downgrade():
    raise RuntimeError(
        "Telemetry evidence must be archived explicitly; no automatic audit deletion"
    )
