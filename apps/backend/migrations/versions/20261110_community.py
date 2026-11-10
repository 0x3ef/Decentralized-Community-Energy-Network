"""Add community boundaries, reservations, retirements and simulated payments.

Revision ID: 20261110_community
Revises: 6da8fac7d51a
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "20261110_community"
down_revision = "6da8fac7d51a"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "energy_communities",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("sun_per_kwh", sa.Numeric(24, 8), nullable=False),
        sa.Column("loss_factor", sa.Numeric(12, 8), nullable=False),
        sa.Column("temporal_policy", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "sun_per_kwh > 0 AND loss_factor >= 0 AND loss_factor < 1",
            name="ck_community_policy",
        ),
    )
    op.create_table(
        "community_memberships",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "community_id",
            sa.Uuid(),
            sa.ForeignKey("energy_communities.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.uid"), nullable=False, index=True
        ),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.UniqueConstraint("community_id", "user_id"),
        sa.CheckConstraint(
            "role IN ('member','operator') AND status IN ('ACTIVE','SUSPENDED')",
            name="ck_membership",
        ),
    )
    op.create_table(
        "community_nodes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "community_id",
            sa.Uuid(),
            sa.ForeignKey("energy_communities.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "home_id", sa.Uuid(), sa.ForeignKey("homes.id"), unique=True, nullable=False
        ),
        sa.Column("authorized", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "meter_authorizations",
        sa.Column(
            "device_id", sa.Uuid(), sa.ForeignKey("devices.id"), primary_key=True
        ),
        sa.Column(
            "node_id",
            sa.Uuid(),
            sa.ForeignKey("community_nodes.id"),
            index=True,
            nullable=False,
        ),
        sa.Column("credential_hash", sa.String(64), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "community_energy_allocations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "community_id",
            sa.Uuid(),
            sa.ForeignKey("energy_communities.id"),
            index=True,
            nullable=False,
        ),
        sa.Column(
            "injection_interval_id",
            sa.Uuid(),
            sa.ForeignKey("energy_intervals.id"),
            index=True,
            nullable=False,
        ),
        sa.Column(
            "withdrawal_interval_id",
            sa.Uuid(),
            sa.ForeignKey("energy_intervals.id"),
            index=True,
            nullable=False,
        ),
        sa.Column("energy_wh", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("energy_wh > 0", name="ck_allocation_energy"),
    )
    op.create_table(
        "compensation_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("idempotency_key", sa.String(128), unique=True, nullable=False),
        sa.Column(
            "community_id",
            sa.Uuid(),
            sa.ForeignKey("energy_communities.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.uid"), nullable=False, index=True
        ),
        sa.Column(
            "allocation_id",
            sa.Uuid(),
            sa.ForeignKey("community_energy_allocations.id"),
            unique=True,
            nullable=False,
        ),
        sa.Column("energy_wh", sa.Integer(), nullable=False),
        sa.Column("token_units", sa.Numeric(78, 0), nullable=False),
        sa.Column("wallet", sa.String(42), nullable=False),
        sa.Column("evidence_hash", sa.String(66), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("transaction_hash", sa.String(66), unique=True),
        sa.Column("block_hash", sa.String(66)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "energy_wh > 0 AND token_units > 0", name="ck_compensation_positive"
        ),
        sa.CheckConstraint(
            "status IN ('RESERVED','AUTHORIZED','SUBMITTED','CONFIRMED','FAILED','RECONCILIATION')",
            name="ck_compensation_status",
        ),
    )
    op.create_table(
        "community_energy_ledger",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "community_id",
            sa.Uuid(),
            sa.ForeignKey("energy_communities.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("operation", sa.String(40), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("energy_wh", sa.Integer(), nullable=False),
        sa.Column("reference", sa.String(128), unique=True, nullable=False),
        sa.Column("blockchain_hash", sa.String(66)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.execute(
        "CREATE FUNCTION reject_energy_ledger_mutation() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'energy ledger is append-only; append a reversal'; END $$"
    )
    op.execute(
        "CREATE TRIGGER energy_ledger_immutable BEFORE UPDATE OR DELETE ON community_energy_ledger FOR EACH ROW EXECUTE FUNCTION reject_energy_ledger_mutation()"
    )
    op.create_table(
        "settlement_obligations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "community_id",
            sa.Uuid(),
            sa.ForeignKey("energy_communities.id"),
            index=True,
            nullable=False,
        ),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("buyer", sa.String(42), nullable=False),
        sa.Column("seller", sa.String(42), nullable=False),
        sa.Column("sun_units", sa.Numeric(78, 0), nullable=False),
        sa.Column("payment_units", sa.Numeric(78, 0), nullable=False),
        sa.Column("payment_asset", sa.String(40), nullable=False),
        sa.Column("transaction_hash", sa.String(66), nullable=False),
        sa.Column("log_index", sa.Integer(), nullable=False),
        sa.Column("block_hash", sa.String(66), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.UniqueConstraint("transaction_hash", "log_index"),
        sa.CheckConstraint(
            "sun_units > 0 AND payment_units > 0", name="ck_obligation_positive"
        ),
    )
    op.create_table(
        "community_chain_deployments",
        sa.Column(
            "community_id",
            sa.Uuid(),
            sa.ForeignKey("energy_communities.id"),
            primary_key=True,
        ),
        sa.Column("chain_id", sa.Integer(), nullable=False),
        sa.Column("sun_address", sa.String(42), unique=True, nullable=False),
        sa.Column("payment_address", sa.String(42), nullable=False),
        sa.Column("marketplace_address", sa.String(42), unique=True, nullable=False),
        sa.Column("compensation_address", sa.String(42), unique=True, nullable=False),
    )


def downgrade():
    for table in (
        "community_chain_deployments",
        "settlement_obligations",
        "community_energy_ledger",
        "compensation_requests",
        "community_energy_allocations",
        "meter_authorizations",
        "community_nodes",
        "community_memberships",
        "energy_communities",
    ):
        op.drop_table(table)
    op.execute("DROP FUNCTION reject_energy_ledger_mutation()")
