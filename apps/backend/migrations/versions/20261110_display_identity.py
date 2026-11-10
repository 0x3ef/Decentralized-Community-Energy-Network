"""Persist existing UI labels without changing physical meter UUID identity."""

from alembic import op
import sqlalchemy as sa

revision = "20261110_display_identity"
down_revision = "20261110_chain_ops"
branch_labels = depends_on = None


def upgrade():
    op.add_column(
        "homes",
        sa.Column("name", sa.String(100), nullable=False, server_default="Home"),
    )
    op.execute("UPDATE homes SET name=left(address,100)")
    op.alter_column("homes", "name", server_default=None)
    op.add_column("devices", sa.Column("device_code", sa.String(100), nullable=True))
    op.create_unique_constraint("uq_devices_device_code", "devices", ["device_code"])


def downgrade():
    op.drop_constraint("uq_devices_device_code", "devices", type_="unique")
    op.drop_column("devices", "device_code")
    op.drop_column("homes", "name")
