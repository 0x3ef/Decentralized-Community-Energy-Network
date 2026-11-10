# Database

PostgreSQL/TimescaleDB is the source of truth for users, homes, devices,
telemetry, interval calculations, credits, orders, trades, redemptions,
blockchain transactions, audit events, and outbox state.

## Schema ownership

The canonical schema is the typed SQLAlchemy model metadata in
`apps/backend/app/db/models/`. Alembic creates it through
`apps/backend/alembic/versions/0001_backend_baseline.py`; it is not generated
from a hand-maintained SQL snapshot.

The Compose stack starts a one-shot `migrator` service before the API,
subscriber, worker, and test services:

```text
TimescaleDB healthy -> alembic upgrade head -> application services
```

Use these commands:

```bash
make migrate
make seed
```

`database/seeds/` remains because seed data is environment data, not schema
definition. The old `database/schema.sql` and SQL migration copies were
removed to prevent two competing schema sources.

## Data model

Business entities use UUID primary keys. Financial and token quantities use
`NUMERIC(38,18)`. Energy accounting uses integer Wh. Telemetry is idempotent
through the unique `(device_id, sequence_number)` constraint. Credits enforce
one credit per interval, while blockchain submissions use an idempotency key.

Typed reading tables reference `telemetry_messages` with cascading deletes.
`energy_interval_sources` preserves calculation provenance. `outbox_events`
is written in the same transaction as the business change and processed by a
separate worker.

## Entity relationship diagram

The source diagram is [docs/diagrams/database.mmd](diagrams/database.mmd).
It can be rendered by Mermaid-compatible tooling.
