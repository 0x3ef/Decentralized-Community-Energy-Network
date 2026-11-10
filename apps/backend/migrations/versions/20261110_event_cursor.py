"""Persist confirmed community blockchain event synchronization cursors."""

from alembic import op
import sqlalchemy as sa

revision = "20261110_event_cursor"
down_revision = "20261110_display_identity"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "community_chain_sync_state",
        sa.Column(
            "community_id",
            sa.Uuid(),
            sa.ForeignKey("energy_communities.id"),
            primary_key=True,
        ),
        sa.Column("block_number", sa.Integer(), nullable=False),
        sa.Column("block_hash", sa.String(66)),
    )


def downgrade():
    op.drop_table("community_chain_sync_state")
