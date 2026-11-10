# SQLModel development seed

The old raw SQL used nonexistent columns (users.id/full_name, wallets.chain_id),
missing required addresses/client IDs, incompatible hashes and falsely verified
wallets. It has been replaced by `apps/backend/src/seed.py`, which imports actual
SQLModel entities and runs inside one transaction under a PostgreSQL advisory lock.

Apply Alembic first. Set DATABASE_URL and JWT_SECRET through your environment, then
provide SEED_PASSWORD (12+ characters) and run `./scripts/seed_db.sh` from an activated
backend virtual environment. Production configuration is refused.

Optional SEED_DEVICE_KEY (32+ characters) explicitly authorizes new demo nodes and
derives distinct device credentials. SEED_OUTPUT_DIR defaults to /tmp/solar-market-demo;
it receives a UUID registry and a private simulator.env file with permissions 0600.
Files are never silently overwritten. Reuse the same key on rerun; changing it is
not an implicit credential rotation. Without a key, devices remain PENDING and
nodes unauthorized until provisioned through the community APIs.

The five homes match the simulator's stable MS labels but are located in Cali,
Colombia. Solar capacities are 4, 6, 0, 0 and 3 kW; batteries are 10, 0, 0, 5 and 0
kWh. Consumer-only homes genuinely have zero PV. Public device UUIDs differ from
internal device row IDs; the generated registry uses the public UUIDs.

Repeated seeds preserve existing passwords, device statuses and revocations.
Conflicting identities fail and roll back. Wallet placeholders are unverified;
link a real user-controlled wallet with a signed challenge. No telemetry, credits,
SUN, USDx or financial settlements are pre-created as supposedly verified history.
