"""Durable signed transactions and distributed nonce coordination."""

from alembic import op
import sqlalchemy as sa

revision = "20261110_chain_ops"
down_revision = "20261110_community"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "community_chain_operations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "outbox_id",
            sa.Uuid(),
            sa.ForeignKey("outbox_events.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("chain_id", sa.Integer(), nullable=False),
        sa.Column("sender", sa.String(42), nullable=False),
        sa.Column("nonce", sa.Integer(), nullable=False),
        sa.Column("transaction_hash", sa.String(66), nullable=False, unique=True),
        sa.Column("raw_transaction", sa.String(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("block_hash", sa.String(66)),
        sa.UniqueConstraint("chain_id", "sender", "nonce"),
    )


def downgrade():
    op.drop_table("community_chain_operations")
