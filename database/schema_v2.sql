BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 0001_backend_baseline

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE audit_events (
    id UUID NOT NULL, 
    actor_type VARCHAR(30) NOT NULL, 
    actor_id UUID, 
    event_type VARCHAR(100) NOT NULL, 
    entity_type VARCHAR(100) NOT NULL, 
    entity_id UUID, 
    metadata JSON, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id)
);

CREATE TABLE blockchain_transactions (
    id UUID NOT NULL, 
    idempotency_key VARCHAR(128) NOT NULL, 
    chain_id BIGINT NOT NULL, 
    contract_address VARCHAR(42) NOT NULL, 
    transaction_hash VARCHAR(66), 
    sender VARCHAR(42) NOT NULL, 
    recipient VARCHAR(42), 
    operation_type VARCHAR(50) NOT NULL, 
    entity_type VARCHAR(50), 
    entity_id UUID, 
    nonce BIGINT, 
    status VARCHAR(20) NOT NULL, 
    block_number BIGINT, 
    gas_used BIGINT, 
    failure_reason TEXT, 
    retry_count INTEGER NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    confirmed_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (id), 
    UNIQUE (transaction_hash)
);

CREATE UNIQUE INDEX ix_blockchain_transactions_idempotency_key ON blockchain_transactions (idempotency_key);

CREATE TABLE outbox_events (
    id UUID NOT NULL, 
    event_type VARCHAR(100) NOT NULL, 
    aggregate_type VARCHAR(50) NOT NULL, 
    aggregate_id UUID NOT NULL, 
    payload JSON NOT NULL, 
    status VARCHAR(20) NOT NULL, 
    attempts INTEGER NOT NULL, 
    available_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    processed_at TIMESTAMP WITH TIME ZONE, 
    last_error TEXT, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id)
);

CREATE INDEX ix_outbox_events_status ON outbox_events (status);

CREATE TABLE users (
    id UUID NOT NULL, 
    email VARCHAR(255) NOT NULL, 
    password_hash VARCHAR, 
    full_name VARCHAR(150) NOT NULL, 
    status VARCHAR(20) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (email)
);

CREATE TABLE homes (
    id UUID NOT NULL, 
    owner_id UUID NOT NULL, 
    name VARCHAR(100) NOT NULL, 
    address VARCHAR, 
    city VARCHAR(100), 
    country VARCHAR(100) NOT NULL, 
    latitude NUMERIC(10, 7), 
    longitude NUMERIC(10, 7), 
    timezone VARCHAR(60) NOT NULL, 
    installed_capacity_w INTEGER NOT NULL, 
    has_battery BOOLEAN NOT NULL, 
    status VARCHAR(20) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(owner_id) REFERENCES users (id)
);

CREATE INDEX ix_homes_owner_id ON homes (owner_id);

CREATE TABLE orders (
    id UUID NOT NULL, 
    seller_id UUID NOT NULL, 
    order_type VARCHAR(10) NOT NULL, 
    token_amount NUMERIC(38, 18) NOT NULL, 
    price_per_token NUMERIC(38, 18) NOT NULL, 
    remaining_amount NUMERIC(38, 18) NOT NULL, 
    status VARCHAR(20) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_order_type CHECK (order_type IN ('sell','buy')), 
    CONSTRAINT ck_order_amount CHECK (token_amount > 0), 
    CONSTRAINT ck_order_price CHECK (price_per_token > 0), 
    CONSTRAINT ck_order_remaining CHECK (remaining_amount >= 0), 
    FOREIGN KEY(seller_id) REFERENCES users (id)
);

CREATE TABLE refresh_tokens (
    id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    token_hash VARCHAR(128) NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    revoked_at TIMESTAMP WITH TIME ZONE, 
    replaced_by_id UUID, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE UNIQUE INDEX ix_refresh_tokens_token_hash ON refresh_tokens (token_hash);

CREATE INDEX ix_refresh_tokens_user_id ON refresh_tokens (user_id);

CREATE TABLE password_reset_tokens (
    id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    token_hash VARCHAR(128) NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    used_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE UNIQUE INDEX ix_password_reset_tokens_token_hash ON password_reset_tokens (token_hash);

CREATE INDEX ix_password_reset_tokens_user_id ON password_reset_tokens (user_id);

CREATE TABLE wallet_nonces (
    id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    address VARCHAR(42) NOT NULL, 
    nonce VARCHAR(128) NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    used_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE UNIQUE INDEX ix_wallet_nonces_nonce ON wallet_nonces (nonce);

CREATE INDEX ix_wallet_nonces_user_id ON wallet_nonces (user_id);

CREATE INDEX ix_wallet_nonces_address ON wallet_nonces (address);

CREATE TABLE user_roles (
    user_id UUID NOT NULL, 
    role VARCHAR(30) NOT NULL, 
    PRIMARY KEY (user_id, role), 
    FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE TABLE blockchain_events (
    id UUID NOT NULL, 
    transaction_id UUID, 
    chain_id BIGINT NOT NULL, 
    contract_address VARCHAR(42) NOT NULL, 
    event_name VARCHAR(100) NOT NULL, 
    block_number BIGINT NOT NULL, 
    log_index BIGINT NOT NULL, 
    payload JSON NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(transaction_id) REFERENCES blockchain_transactions (id)
);

CREATE TABLE wallets (
    id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    address VARCHAR(42) NOT NULL, 
    chain_id BIGINT NOT NULL, 
    is_verified BOOLEAN NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id), 
    UNIQUE (address)
);

CREATE INDEX ix_wallets_user_id ON wallets (user_id);

CREATE TABLE devices (
    id UUID NOT NULL, 
    home_id UUID NOT NULL, 
    device_code VARCHAR(100) NOT NULL, 
    device_type VARCHAR(30) NOT NULL, 
    manufacturer VARCHAR(100), 
    model VARCHAR(100), 
    firmware_version VARCHAR(50), 
    serial_number VARCHAR(100), 
    mqtt_client_id VARCHAR(150), 
    installation_date DATE, 
    status VARCHAR(20) NOT NULL, 
    last_seen_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(home_id) REFERENCES homes (id), 
    UNIQUE (mqtt_client_id)
);

CREATE INDEX ix_devices_home_id ON devices (home_id);

CREATE INDEX ix_devices_device_type ON devices (device_type);

CREATE UNIQUE INDEX ix_devices_device_code ON devices (device_code);

CREATE TABLE energy_intervals (
    id UUID NOT NULL, 
    home_id UUID NOT NULL, 
    interval_start TIMESTAMP WITH TIME ZONE NOT NULL, 
    interval_end TIMESTAMP WITH TIME ZONE NOT NULL, 
    generation_wh BIGINT NOT NULL, 
    consumption_wh BIGINT NOT NULL, 
    grid_import_wh BIGINT NOT NULL, 
    grid_export_wh BIGINT NOT NULL, 
    battery_charge_wh BIGINT NOT NULL, 
    battery_discharge_wh BIGINT NOT NULL, 
    eligible_export_wh BIGINT NOT NULL, 
    calculation_version VARCHAR(30) NOT NULL, 
    quality_status VARCHAR(20) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_energy_interval UNIQUE (home_id, interval_start, interval_end), 
    CONSTRAINT ck_energy_interval_order CHECK (interval_end > interval_start), 
    CONSTRAINT ck_energy_eligible_export CHECK (eligible_export_wh <= grid_export_wh), 
    FOREIGN KEY(home_id) REFERENCES homes (id)
);

CREATE INDEX ix_energy_intervals_home_id ON energy_intervals (home_id);

CREATE TABLE trades (
    id UUID NOT NULL, 
    order_id UUID NOT NULL, 
    buyer_id UUID NOT NULL, 
    seller_id UUID NOT NULL, 
    token_amount NUMERIC(38, 18) NOT NULL, 
    execution_price NUMERIC(38, 18) NOT NULL, 
    transaction_hash VARCHAR(66), 
    status VARCHAR(20) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(order_id) REFERENCES orders (id), 
    FOREIGN KEY(buyer_id) REFERENCES users (id), 
    FOREIGN KEY(seller_id) REFERENCES users (id), 
    UNIQUE (transaction_hash)
);

CREATE TABLE redemptions (
    id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    wallet_id UUID NOT NULL, 
    token_amount NUMERIC(38, 18) NOT NULL, 
    compensation_amount NUMERIC(38, 18), 
    compensation_currency VARCHAR(10), 
    transaction_hash VARCHAR(66), 
    status VARCHAR(20) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    completed_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id), 
    FOREIGN KEY(wallet_id) REFERENCES wallets (id), 
    UNIQUE (transaction_hash)
);

CREATE TABLE home_members (
    home_id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    role VARCHAR(20) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (home_id, user_id), 
    FOREIGN KEY(home_id) REFERENCES homes (id), 
    FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE TABLE energy_credits (
    id UUID NOT NULL, 
    interval_id UUID NOT NULL, 
    owner_id UUID NOT NULL, 
    energy_wh BIGINT NOT NULL, 
    token_amount NUMERIC(38, 18) NOT NULL, 
    status VARCHAR(20) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_credit_energy CHECK (energy_wh > 0), 
    CONSTRAINT ck_credit_amount CHECK (token_amount > 0), 
    UNIQUE (interval_id), 
    FOREIGN KEY(interval_id) REFERENCES energy_intervals (id), 
    FOREIGN KEY(owner_id) REFERENCES users (id)
);

CREATE TABLE telemetry_messages (
    id UUID NOT NULL, 
    device_id UUID NOT NULL, 
    sequence_number BIGINT NOT NULL, 
    schema_version VARCHAR(20) NOT NULL, 
    measured_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    received_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    mqtt_topic TEXT, 
    payload JSONB NOT NULL, 
    quality_status VARCHAR(20) NOT NULL, 
    validation_errors JSONB, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_telemetry_device_seq UNIQUE (device_id, sequence_number), 
    FOREIGN KEY(device_id) REFERENCES devices (id)
);

CREATE INDEX ix_telemetry_messages_measured_at ON telemetry_messages (measured_at);

CREATE INDEX ix_telemetry_messages_device_id ON telemetry_messages (device_id);

CREATE TABLE device_credentials (
    id UUID NOT NULL, 
    device_id UUID NOT NULL, 
    credential_hash VARCHAR(128) NOT NULL, 
    active BOOLEAN NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(device_id) REFERENCES devices (id), 
    UNIQUE (credential_hash)
);

CREATE INDEX ix_device_credentials_device_id ON device_credentials (device_id);

CREATE TABLE device_counter_snapshots (
    device_id UUID NOT NULL, 
    counter_name VARCHAR(80) NOT NULL, 
    counter_value_wh BIGINT NOT NULL, 
    measured_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (device_id, counter_name), 
    FOREIGN KEY(device_id) REFERENCES devices (id)
);

CREATE TABLE energy_interval_revisions (
    id UUID NOT NULL, 
    interval_id UUID NOT NULL, 
    calculation_version VARCHAR(30) NOT NULL, 
    values JSON NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(interval_id) REFERENCES energy_intervals (id)
);

CREATE INDEX ix_energy_interval_revisions_interval_id ON energy_interval_revisions (interval_id);

CREATE TABLE redemption_settlements (
    id UUID NOT NULL, 
    redemption_id UUID NOT NULL, 
    external_reference VARCHAR(128), 
    amount NUMERIC(38, 18) NOT NULL, 
    currency VARCHAR(10) NOT NULL, 
    status VARCHAR(20) NOT NULL, 
    evidence JSON, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    completed_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (id), 
    UNIQUE (redemption_id), 
    FOREIGN KEY(redemption_id) REFERENCES redemptions (id), 
    UNIQUE (external_reference)
);

CREATE TABLE token_issuances (
    id UUID NOT NULL, 
    credit_id UUID NOT NULL, 
    wallet_id UUID NOT NULL, 
    chain_id BIGINT NOT NULL, 
    transaction_hash VARCHAR(66), 
    block_number BIGINT, 
    token_amount NUMERIC(38, 18) NOT NULL, 
    status VARCHAR(20) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    confirmed_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (id), 
    UNIQUE (credit_id), 
    FOREIGN KEY(credit_id) REFERENCES energy_credits (id), 
    FOREIGN KEY(wallet_id) REFERENCES wallets (id), 
    UNIQUE (transaction_hash)
);

CREATE TABLE smart_meter_readings (
    id UUID NOT NULL, 
    telemetry_id UUID NOT NULL, 
    voltage_v NUMERIC(10, 3), 
    current_a NUMERIC(10, 3), 
    frequency_hz NUMERIC(8, 3), 
    active_power_w NUMERIC(12, 3), 
    power_factor NUMERIC(5, 4), 
    grid_import_power_w NUMERIC(12, 3), 
    grid_export_power_w NUMERIC(12, 3), 
    cumulative_consumption_wh BIGINT, 
    cumulative_import_wh BIGINT, 
    cumulative_export_wh BIGINT, 
    PRIMARY KEY (id), 
    UNIQUE (telemetry_id), 
    FOREIGN KEY(telemetry_id) REFERENCES telemetry_messages (id) ON DELETE CASCADE
);

CREATE TABLE inverter_readings (
    id UUID NOT NULL, 
    telemetry_id UUID NOT NULL, 
    dc_power_w NUMERIC(12, 3), 
    ac_power_w NUMERIC(12, 3), 
    daily_energy_wh BIGINT, 
    lifetime_energy_wh BIGINT, 
    temperature_c NUMERIC(8, 3), 
    efficiency_pct NUMERIC(6, 3), 
    operating_state VARCHAR(30), 
    alarm_code VARCHAR(100), 
    PRIMARY KEY (id), 
    UNIQUE (telemetry_id), 
    FOREIGN KEY(telemetry_id) REFERENCES telemetry_messages (id) ON DELETE CASCADE
);

CREATE TABLE weather_readings (
    id UUID NOT NULL, 
    telemetry_id UUID NOT NULL, 
    irradiance_w_m2 NUMERIC(10, 3), 
    ambient_temperature_c NUMERIC(8, 3), 
    panel_temperature_c NUMERIC(8, 3), 
    humidity_pct NUMERIC(6, 3), 
    wind_speed_m_s NUMERIC(8, 3), 
    PRIMARY KEY (id), 
    UNIQUE (telemetry_id), 
    FOREIGN KEY(telemetry_id) REFERENCES telemetry_messages (id) ON DELETE CASCADE
);

CREATE TABLE battery_readings (
    id UUID NOT NULL, 
    telemetry_id UUID NOT NULL, 
    state_of_charge_pct NUMERIC(6, 3), 
    voltage_v NUMERIC(10, 3), 
    current_a NUMERIC(10, 3), 
    charge_power_w NUMERIC(12, 3), 
    discharge_power_w NUMERIC(12, 3), 
    temperature_c NUMERIC(8, 3), 
    available_energy_wh BIGINT, 
    operating_state VARCHAR(30), 
    PRIMARY KEY (id), 
    UNIQUE (telemetry_id), 
    FOREIGN KEY(telemetry_id) REFERENCES telemetry_messages (id) ON DELETE CASCADE
);

CREATE TABLE energy_interval_sources (
    id UUID NOT NULL, 
    interval_id UUID NOT NULL, 
    telemetry_id UUID NOT NULL, 
    measurement_role VARCHAR(30) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_interval_sources UNIQUE (interval_id, telemetry_id, measurement_role), 
    CONSTRAINT ck_interval_sources_role CHECK (measurement_role IN ('generation','consumption','grid_exchange','battery','weather','validation')), 
    FOREIGN KEY(interval_id) REFERENCES energy_intervals (id), 
    FOREIGN KEY(telemetry_id) REFERENCES telemetry_messages (id)
);

CREATE INDEX ix_energy_interval_sources_interval_id ON energy_interval_sources (interval_id);

CREATE TABLE credit_approvals (
    id UUID NOT NULL, 
    credit_id UUID NOT NULL, 
    approver_id UUID NOT NULL, 
    status VARCHAR(20) NOT NULL, 
    note TEXT, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (credit_id), 
    FOREIGN KEY(credit_id) REFERENCES energy_credits (id), 
    FOREIGN KEY(approver_id) REFERENCES users (id)
);

INSERT INTO alembic_version (version_num) VALUES ('0001_backend_baseline') RETURNING alembic_version.version_num;

COMMIT;


-- TimescaleDB configuration. Run after the relational schema is created.
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Telemetry is append-only, time-ordered data. A 7-day chunk keeps recent
-- ingestion and interval queries bounded while preserving relational FKs.
-- Hypertable conversion is deferred: the current primary/foreign-key design
-- uses UUID identity keys and global interval uniqueness. Converting it would
-- require a composite time-aware key migration. See architecture_decisions.md.

-- Keep raw telemetry for audit and recalculation; operational retention is
-- intentionally not enabled until the product retention decision is approved.
