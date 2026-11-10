"""Keep durable transaction replacement history with the original nonce."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "20261110_replacements"
down_revision = "20261110_event_cursor"
branch_labels = depends_on = None


def upgrade():
    op.add_column(
        "community_chain_operations",
        sa.Column(
            "previous_transactions",
            JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.alter_column(
        "community_chain_operations", "previous_transactions", server_default=None
    )


def downgrade():
    op.drop_column("community_chain_operations", "previous_transactions")
