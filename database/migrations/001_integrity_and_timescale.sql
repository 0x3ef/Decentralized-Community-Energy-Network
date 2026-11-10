-- Safe post-baseline hardening migration.
-- Prerequisite: apps/backend Alembic revision 0001_backend_baseline.
-- This migration is additive and does not delete or rewrite production data.

CREATE EXTENSION IF NOT EXISTS timescaledb;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_telemetry_sequence_nonnegative') THEN
        ALTER TABLE telemetry_messages
            ADD CONSTRAINT ck_telemetry_sequence_nonnegative CHECK (sequence_number >= 0);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_interval_energy_nonnegative') THEN
        ALTER TABLE energy_intervals
            ADD CONSTRAINT ck_interval_energy_nonnegative CHECK (
                generation_wh >= 0 AND consumption_wh >= 0 AND
                grid_import_wh >= 0 AND grid_export_wh >= 0 AND
                battery_charge_wh >= 0 AND battery_discharge_wh >= 0 AND
                eligible_export_wh >= 0
            );
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_order_remaining_lte_total') THEN
        ALTER TABLE orders
            ADD CONSTRAINT ck_order_remaining_lte_total CHECK (remaining_amount <= token_amount);
    END IF;
END $$;

-- Hypertable conversion is intentionally deferred until the UUID/FK key
-- migration includes the time partitioning column.

CREATE INDEX IF NOT EXISTS ix_telemetry_device_measured
    ON telemetry_messages (device_id, measured_at DESC);
CREATE INDEX IF NOT EXISTS ix_intervals_home_start
    ON energy_intervals (home_id, interval_start DESC);
CREATE INDEX IF NOT EXISTS ix_orders_open_price
    ON orders (status, order_type, price_per_token, created_at);
