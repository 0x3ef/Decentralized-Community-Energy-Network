"""Native ETH deployments are separate from historical ERC20 payment assets."""

from alembic import op
import sqlalchemy as sa

revision = "20261110_native_vault"
down_revision = "20261110_governance"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "community_native_deployments",
        sa.Column(
            "community_id",
            sa.Uuid(),
            sa.ForeignKey("energy_communities.id"),
            primary_key=True,
        ),
        sa.Column("chain_id", sa.Integer(), nullable=False),
        sa.Column("sun_address", sa.String(42), nullable=False),
        sa.Column("settlement_address", sa.String(42), unique=True, nullable=False),
        sa.Column("vault_address", sa.String(42), unique=True, nullable=False),
    )


def downgrade():
    op.drop_table("community_native_deployments")
