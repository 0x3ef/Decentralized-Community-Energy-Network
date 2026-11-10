# Database and API Mapping

The canonical application schema is defined by `apps/backend/app/db/models` and
created by Alembic revision `0001_backend_baseline`. `database/schema_v2.sql`
is the generated PostgreSQL/TimescaleDB bootstrap script; the SQL in
`database/migrations/` is additive hardening for an already migrated database.

## Identity and access

| API area | Request/response | Tables | Authorization | Transaction boundary |
|---|---|---|---|---|
| `POST /api/v1/auth/register` | `UserCreate` / `TokenResponse` | `users`, `refresh_tokens` | Public; canonical registration endpoint | One request transaction |
| `GET /api/v1/users/me` | None / `UserOut` | `users`, `wallets`, `energy_credits` | Authenticated principal only | Read-only request |
| `POST /api/v1/homes` | `HomeCreate` / `HomeOut` | `homes`, `home_members` | Authenticated; owner is derived from the token | Home and owner membership are committed together |
| `GET /api/v1/users/me/homes` | None / `HomeOut[]` | `homes`, `home_members` | Authenticated member | Read-only request |
| `POST /api/v1/homes/{id}/members` | member request / membership | `homes`, `home_members` | Home owner only | Membership insert is committed with the request |

`owner_id`, `seller_id`, `buyer_id`, and redemption `user_id` are not accepted
as authoritative identity inputs. The authenticated principal is used instead.
User registration is intentionally exposed only at `/api/v1/auth/register`;
`/api/v1/users` is reserved for user resources and has no registration action.

## Devices and telemetry

| API area | Tables | Authorization |
|---|---|---|
| `POST /api/v1/devices` | `homes`, `devices` | Home owner |
| `GET/PATCH /api/v1/devices/{device_code}` | `devices`, `homes`, `home_members` | Home member for reads; owner for metadata updates |
| `POST /api/v1/iot/telemetry` | `devices`, `telemetry_messages` | User-authenticated HTTP path; MQTT path is service/device authenticated |
| Device telemetry history | `devices`, `telemetry_messages` | Home member |

The external `device_code` resolves to the internal `devices.id`. The home is
resolved from that device relationship and the envelope is rejected when its
claimed home or sensor type does not match. `(device_id, sequence_number)` is
unique, making duplicate delivery idempotent.

Typed sensor readings (`smart_meter_readings`, `inverter_readings`,
`weather_readings`, and `battery_readings`) reference a raw telemetry row.
Normalization is intentionally separate from raw-envelope persistence so
invalid or late payloads remain auditable.

## Energy and credits

All `/homes/{home_id}/energy/*` reads require an authenticated home member.
`POST /energy/aggregate` is administrator-only because it changes calculated
energy state. The service writes `energy_intervals` with a unique
`(home_id, interval_start, interval_end)` key and preserves source rows in
`energy_interval_sources`.

An eligible interval can create only one `energy_credits` row because
`energy_credits.interval_id` is unique. `token_issuances.credit_id` is also
unique. Blockchain confirmation must update issuance state only after a
successful receipt and event check.

## Marketplace and redemption

`orders` and `trades` model the current off-chain matching boundary. The
authenticated principal owns an order; a fill creates a `trades` row linked to
that order and reduces `orders.remaining_amount` in the same transaction.
PostgreSQL row locks are required for concurrent fills before enabling
multi-worker matching in production.

`redemptions` references the user's wallet and follows `pending -> approved ->
completed` (or `rejected`). `redemption_settlements` stores external settlement
evidence separately. Credit reservation and on-chain escrow remain an explicit
product decision documented in `architecture_decisions.md`.
