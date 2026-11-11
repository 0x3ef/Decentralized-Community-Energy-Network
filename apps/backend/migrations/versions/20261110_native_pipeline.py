"""Persist immutable native interval accounting, obligations and chain projections."""

from alembic import op

revision = "20261110_native_pipeline"
down_revision = "20261110_native_vault"
branch_labels = depends_on = None


def upgrade():
    op.execute(
        """
CREATE TABLE native_indexed_events (
    id UUID NOT NULL, 
    community_id UUID NOT NULL, 
    chain_id INTEGER NOT NULL, 
    address VARCHAR(42) NOT NULL, 
    transaction_hash VARCHAR(66) NOT NULL, 
    log_index INTEGER NOT NULL, 
    block_number BIGINT NOT NULL, 
    block_hash VARCHAR(66) NOT NULL, 
    event_name VARCHAR(60) NOT NULL, 
    payload JSONB NOT NULL, 
    canonical BOOLEAN NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (chain_id, transaction_hash, log_index, block_hash), 
    FOREIGN KEY(community_id) REFERENCES energy_communities (id)
)
        """
    )
    op.execute(
        "CREATE INDEX ix_native_indexed_events_community_id ON native_indexed_events (community_id)"
    )
    op.execute(
        "CREATE INDEX ix_native_indexed_events_transaction_hash ON native_indexed_events (transaction_hash)"
    )
    op.execute(
        """
CREATE TABLE native_settlement_policies (
    id UUID NOT NULL, 
    community_id UUID NOT NULL, 
    policy_hash VARCHAR(66) NOT NULL, 
    price_wei_per_kwh NUMERIC(78, 0) NOT NULL, 
    interval_seconds INTEGER NOT NULL, 
    rules JSONB NOT NULL, 
    governance_reference VARCHAR(66) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (community_id, policy_hash), 
    CONSTRAINT ck_native_policy CHECK (price_wei_per_kwh > 0 AND interval_seconds > 0), 
    FOREIGN KEY(community_id) REFERENCES energy_communities (id)
)
        """
    )
    op.execute(
        "CREATE INDEX ix_native_settlement_policies_community_id ON native_settlement_policies (community_id)"
    )
    op.execute(
        """
CREATE TABLE native_sync_cursors (
    community_id UUID NOT NULL, 
    block_number BIGINT NOT NULL, 
    block_hash VARCHAR(66), 
    PRIMARY KEY (community_id), 
    FOREIGN KEY(community_id) REFERENCES energy_communities (id)
)
        """
    )
    op.execute(
        """
CREATE TABLE native_wallet_transactions (
    id UUID NOT NULL, 
    community_id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    chain_id INTEGER NOT NULL, 
    transaction_hash VARCHAR(66) NOT NULL, 
    action VARCHAR(40) NOT NULL, 
    status VARCHAR(30) NOT NULL, 
    block_hash VARCHAR(66), 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (chain_id, transaction_hash), 
    FOREIGN KEY(community_id) REFERENCES energy_communities (id), 
    FOREIGN KEY(user_id) REFERENCES users (uid)
)
        """
    )
    op.execute(
        "CREATE INDEX ix_native_wallet_transactions_community_id ON native_wallet_transactions (community_id)"
    )
    op.execute(
        "CREATE INDEX ix_native_wallet_transactions_user_id ON native_wallet_transactions (user_id)"
    )
    op.execute(
        """
CREATE TABLE native_settlement_batches (
    id UUID NOT NULL, 
    community_id UUID NOT NULL, 
    policy_id UUID NOT NULL, 
    interval_start TIMESTAMP WITH TIME ZONE NOT NULL, 
    interval_end TIMESTAMP WITH TIME ZONE NOT NULL, 
    chain_batch_id VARCHAR(66) NOT NULL, 
    root VARCHAR(66) NOT NULL, 
    injection_wh BIGINT NOT NULL, 
    consumption_wh BIGINT NOT NULL, 
    allocated_wh BIGINT NOT NULL, 
    total_due_wei NUMERIC(78, 0) NOT NULL, 
    evidence JSONB NOT NULL, 
    status VARCHAR(30) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (community_id, interval_start, interval_end), 
    CONSTRAINT ck_native_batch_energy CHECK (interval_end > interval_start AND injection_wh >= allocated_wh AND consumption_wh >= allocated_wh AND allocated_wh >= 0), 
    CONSTRAINT ck_native_batch_status CHECK (status IN ('PREPARED','SUBMITTED','CHALLENGEABLE','FINALIZED','REJECTED','SUPERSEDED','RECONCILIATION_REQUIRED')), 
    FOREIGN KEY(community_id) REFERENCES energy_communities (id), 
    FOREIGN KEY(policy_id) REFERENCES native_settlement_policies (id), 
    UNIQUE (chain_batch_id)
)
        """
    )
    op.execute(
        "CREATE INDEX ix_native_settlement_batches_community_id ON native_settlement_batches (community_id)"
    )
    op.execute(
        "CREATE INDEX ix_native_settlement_batches_status ON native_settlement_batches (status)"
    )
    op.execute(
        """
CREATE TABLE native_interval_allocations (
    id UUID NOT NULL, 
    batch_id UUID NOT NULL, 
    producer_id UUID NOT NULL, 
    consumer_id UUID NOT NULL, 
    producer_node_id UUID NOT NULL, 
    consumer_node_id UUID NOT NULL, 
    injection_interval_id UUID NOT NULL, 
    consumption_interval_id UUID NOT NULL, 
    producer_wallet VARCHAR(42) NOT NULL, 
    consumer_wallet VARCHAR(42) NOT NULL, 
    chain_allocation_id VARCHAR(66) NOT NULL, 
    energy_wh BIGINT NOT NULL, 
    consumer_cap_wh BIGINT NOT NULL, 
    due_wei NUMERIC(78, 0) NOT NULL, 
    proof JSONB NOT NULL, 
    funding_status VARCHAR(30) NOT NULL, 
    status VARCHAR(30) NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (batch_id, producer_node_id, consumer_node_id), 
    CONSTRAINT ck_native_allocation CHECK (energy_wh > 0 AND due_wei > 0 AND consumer_cap_wh >= energy_wh), 
    FOREIGN KEY(batch_id) REFERENCES native_settlement_batches (id), 
    FOREIGN KEY(producer_id) REFERENCES users (uid), 
    FOREIGN KEY(consumer_id) REFERENCES users (uid), 
    FOREIGN KEY(producer_node_id) REFERENCES community_nodes (id), 
    FOREIGN KEY(consumer_node_id) REFERENCES community_nodes (id), 
    FOREIGN KEY(injection_interval_id) REFERENCES energy_intervals (id), 
    FOREIGN KEY(consumption_interval_id) REFERENCES energy_intervals (id), 
    UNIQUE (chain_allocation_id)
)
        """
    )
    op.execute(
        "CREATE INDEX ix_native_interval_allocations_batch_id ON native_interval_allocations (batch_id)"
    )
    op.execute(
        "CREATE INDEX ix_native_interval_allocations_consumer_id ON native_interval_allocations (consumer_id)"
    )
    op.execute(
        "CREATE INDEX ix_native_interval_allocations_producer_id ON native_interval_allocations (producer_id)"
    )
    op.execute(
        "CREATE INDEX ix_native_interval_allocations_status ON native_interval_allocations (status)"
    )
    op.execute(
        """
CREATE TABLE native_settlement_claims (
    id UUID NOT NULL, 
    batch_id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    node_id UUID NOT NULL, 
    meter_id UUID NOT NULL, 
    interval_id UUID NOT NULL, 
    energy_credit_id UUID, 
    kind INTEGER NOT NULL, 
    chain_claim_id VARCHAR(66) NOT NULL, 
    wallet VARCHAR(42) NOT NULL, 
    energy_wh BIGINT NOT NULL, 
    proof JSONB NOT NULL, 
    status VARCHAR(30) NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (batch_id, kind, node_id), 
    CONSTRAINT ck_native_claim CHECK (energy_wh > 0 AND kind IN (0,1)), 
    FOREIGN KEY(batch_id) REFERENCES native_settlement_batches (id), 
    FOREIGN KEY(user_id) REFERENCES users (uid), 
    FOREIGN KEY(node_id) REFERENCES community_nodes (id), 
    FOREIGN KEY(meter_id) REFERENCES devices (id), 
    FOREIGN KEY(interval_id) REFERENCES energy_intervals (id), 
    UNIQUE (energy_credit_id), 
    FOREIGN KEY(energy_credit_id) REFERENCES energy_credits (id), 
    UNIQUE (chain_claim_id)
)
        """
    )
    op.execute(
        "CREATE INDEX ix_native_settlement_claims_batch_id ON native_settlement_claims (batch_id)"
    )
    op.execute(
        "CREATE INDEX ix_native_settlement_claims_user_id ON native_settlement_claims (user_id)"
    )


def downgrade():
    raise RuntimeError(
        "Native settlement accounting must be archived explicitly; automatic financial history deletion is forbidden"
    )
