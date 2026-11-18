"""Preserve lost local-chain history separately from active settlement projections."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261112_local_recovery"
down_revision = "20261111_chain_identity"
branch_labels = depends_on = None


def upgrade():
    op.add_column(
        "community_native_deployments",
        sa.Column("accounting_start", sa.DateTime(timezone=True)),
    )
    for table in ("native_settlement_batches", "native_wallet_transactions"):
        op.add_column(
            table,
            sa.Column(
                "archived", sa.Boolean(), nullable=False, server_default=sa.false()
            ),
        )
    table = "native_wallet_transactions"
    op.add_column(
        table,
        sa.Column("chain_genesis", sa.String(66), nullable=False, server_default=""),
    )
    for constraint in sa.inspect(op.get_bind()).get_unique_constraints(table):
        if set(constraint["column_names"]) == {"chain_id", "transaction_hash"}:
            op.drop_constraint(constraint["name"], table, type_="unique")
    op.create_unique_constraint(
        "uq_native_wallet_network_tx",
        table,
        ["chain_id", "chain_genesis", "transaction_hash"],
    )
    op.create_table(
        "local_chain_recoveries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "community_id",
            sa.Uuid(),
            sa.ForeignKey("energy_communities.id"),
            nullable=False,
        ),
        sa.Column("new_genesis", sa.String(66), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column(
            "details",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("community_id", "new_genesis"),
    )


def downgrade():
    # Refuse to discard the audit history or collapse transactions from different chains.
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT count(*) FROM local_chain_recoveries")).scalar():
        raise RuntimeError(
            "Recovery history exists; downgrade would discard retained records"
        )
    op.drop_table("local_chain_recoveries")
    op.drop_constraint(
        "uq_native_wallet_network_tx", "native_wallet_transactions", type_="unique"
    )
    op.create_unique_constraint(
        "uq_native_wallet_chain_tx",
        "native_wallet_transactions",
        ["chain_id", "transaction_hash"],
    )
    op.drop_column("native_wallet_transactions", "chain_genesis")
    for table in ("native_settlement_batches", "native_wallet_transactions"):
        op.drop_column(table, "archived")
    op.drop_column("community_native_deployments", "accounting_start")
