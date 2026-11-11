"""Bind signed nonce journals to a chain genesis; quarantine legacy unknown origin."""

import sqlalchemy as sa
from alembic import op

revision = "20261111_chain_identity"
down_revision = "20261110_load_power"
branch_labels = depends_on = None
TABLE = "community_chain_operations"


def upgrade():
    op.add_column(
        TABLE,
        sa.Column("chain_genesis", sa.String(66), nullable=False, server_default=""),
    )
    inspector = sa.inspect(op.get_bind())
    for constraint in inspector.get_unique_constraints(TABLE):
        if set(constraint["column_names"]) == {"chain_id", "sender", "nonce"}:
            op.drop_constraint(constraint["name"], TABLE, type_="unique")
    op.create_unique_constraint(
        "uq_chain_operation_network_nonce",
        TABLE,
        ["chain_id", "chain_genesis", "sender", "nonce"],
    )


def downgrade():
    # Downgrade intentionally fails if nonce reuse across distinct local chains
    # would discard journal identity. Never delete financial history to force it.
    op.drop_constraint("uq_chain_operation_network_nonce", TABLE, type_="unique")
    op.create_unique_constraint(
        "community_chain_operations_chain_id_sender_nonce_key",
        TABLE,
        ["chain_id", "sender", "nonce"],
    )
    op.drop_column(TABLE, "chain_genesis")
