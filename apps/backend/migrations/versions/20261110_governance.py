"""Fail closed: legacy communities require review; proposals grant no authority."""

from alembic import op
import sqlalchemy as sa

revision = "20261110_governance"
down_revision = "20261110_battery_power"
branch_labels = depends_on = None


def upgrade():
    op.add_column(
        "energy_communities",
        sa.Column(
            "status", sa.String(20), nullable=False, server_default="UNDER_REVIEW"
        ),
    )
    op.add_column(
        "energy_communities",
        sa.Column("proposer_id", sa.Uuid(), sa.ForeignKey("users.uid")),
    )
    for name, length, default in [
        ("boundary_description", 1000, ""),
        ("topology", 50, "SIMULATED_GRID_CONNECTED"),
        ("policy_hash", 66, ""),
        ("boundary_hash", 66, ""),
    ]:
        op.add_column(
            "energy_communities",
            sa.Column(name, sa.String(length), nullable=False, server_default=default),
        )
    op.add_column(
        "energy_communities",
        sa.Column(
            "interval_seconds", sa.Integer(), nullable=False, server_default="900"
        ),
    )
    op.add_column("energy_communities", sa.Column("registry_address", sa.String(42)))
    op.add_column(
        "energy_communities", sa.Column("governance_transaction", sa.String(66))
    )
    op.drop_constraint("ck_membership", "community_memberships", type_="check")
    op.create_check_constraint(
        "ck_membership",
        "community_memberships",
        "role IN ('member','operator') AND status IN ('PENDING','APPROVED','ACTIVE','SUSPENDED','REVOKED')",
    )
    op.create_check_constraint(
        "ck_community_lifecycle",
        "energy_communities",
        "status IN ('DRAFT','PROPOSED','UNDER_REVIEW','APPROVED','ACTIVE','SUSPENDED','REJECTED','ARCHIVED') AND interval_seconds > 0",
    )


def downgrade():
    raise RuntimeError(
        "Governance downgrade requires explicit review of pending/revoked memberships; no silent privilege restoration"
    )
