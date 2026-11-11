# HTTP API

The current application is [src.main:app](../apps/backend/src/main.py). All domain
routes use **`/api/v1`**. Swagger is at
[http://127.0.0.1:8000/api/v1/docs](http://127.0.0.1:8000/api/v1/docs), ReDoc at
[http://127.0.0.1:8000/api/v1/redoc](http://127.0.0.1:8000/api/v1/redoc), and the
live contract at
[http://127.0.0.1:8000/api/v1/openapi.json](http://127.0.0.1:8000/api/v1/openapi.json).
These locations require a running local API. There is no parallel `/api/v2`.

## Authentication and authorization

`POST /api/v1/auth/signup` creates an account; `POST /api/v1/auth/login` returns
`access_token`, `refresh_token`, message and user identifiers. Access and refresh
values are signed JWTs, with the refresh flag checked by separate bearer
dependencies. Current defaults are one-hour access and two-day refresh lifetimes.
Passwords use bcrypt. This implementation does not use Argon2, opaque rotating
refresh tokens, database refresh-token hashes or HTTP-only cookie sessions.

Use `Authorization: Bearer <access-token>` for authenticated calls.
`GET /api/v1/auth/refresh_token` takes the refresh JWT as bearer and returns a new
access token; it does not rotate the refresh JWT. `GET /api/v1/auth/logout` blocks
the presented access token's JTI in Redis. `GET /api/v1/auth/me` returns the current
user. Logout is not revocation of every token issued to that user.

Home/device services enforce ownership. Community data requires current membership;
operator jobs and privileged operations require the appointed operator. Governed
protocol authority is checked against registry state, independently of application
roles. Wallet ownership uses `POST /api/v1/communities/wallet/challenge` followed by
`POST /api/v1/communities/wallet/verify`, with an expiring single-use EIP-191 proof.
Neither JWT login nor wallet connection activates a community.

## Important endpoint groups

Paths in this table are relative to `/api/v1`. Route spelling, including repeated
`device`, reflects the implementation.

| Methods and path | Purpose |
| --- | --- |
| `POST /auth/signup`, `POST /auth/login`, `GET /auth/me` | Identity and session |
| `GET /wallet/` | Current user's wallets |
| `GET /home/`, `POST /home/`, `GET /home/{home_id}` | Owned homes |
| `POST /device/device`, `GET /device/device/` | Create a pending device; list by `home_id` query |
| `GET /device/device/{device_id}` | Device metadata by internal UUID |
| `GET /iot/devices/{device_id}/health`, `GET /iot/devices/{device_id}/quality` | Owned device freshness, source and safe quality evidence |
| `GET /communities`, `POST /communities` | Own memberships/proposals; create a draft |
| `POST /communities/{community_id}/propose` | Unsigned governed proposal |
| `POST /communities/{community_id}/memberships/apply` | Pending membership, no operational grant |
| `POST /communities/{community_id}/memberships/sync` | Confirm own registry membership |
| `POST /communities/{community_id}/nodes`, `POST /communities/nodes/{node_id}/meters` | Node and scoped meter provisioning |
| `POST /communities/{community_id}/governance/prepare`, `POST /communities/{community_id}/governance/sync` | Role-checked unsigned governance actions and receipt synchronization |
| `POST /communities/{community_id}/native-deployment` | Validate and register governed native contract bindings |
| `GET /communities/{community_id}/native-wallet`, `POST /communities/{community_id}/native/prepare` | Confirmed own balances and unsigned participant actions |
| `POST /communities/{community_id}/native/transactions`, `GET /communities/{community_id}/native/transactions` | Track own submitted hashes and confirmed status |
| `POST /communities/{community_id}/settlements/calculate`, `GET /communities/{community_id}/settlements` | Operator calculation and member batch history |
| `GET /communities/{community_id}/settlements/{batch_id}` | Batch energy and obligation totals |
| `GET /communities/{community_id}/settlements/{batch_id}/allocations`, `GET /communities/{community_id}/settlements/{batch_id}/claims` | Participant-scoped allocations and proofs |
| `GET /communities/{community_id}/allocations/{allocation_id}/funding` | Funding state; only the caller's own balances disclosed |
| `GET /communities/{community_id}/settlement-statement`, `GET /communities/{community_id}/settlement-policy` | Own dues/earnings/retirement and governed immutable policy |
| `GET /communities/{community_id}/settlements/{batch_id}/operations` | Operator job and operation references |
| `POST /communities/{community_id}/settlements/{batch_id}/reconcile`, `POST /communities/{community_id}/settlements/{batch_id}/jobs/{job_id}/retry` | Explicit canonical audit or retry of terminal failed work |
| `GET /system/status`, `GET /communities/{community_id}/operations/status` | Authenticated service status; operator lag/quality/reconciliation alerts |

For batch approval, `governance/prepare` accepts
`{"action":"finalize_batch","batch_id":"<batch UUID>"}`. The verified timelock
proposer receives unsigned schedule/execute calldata targeting the community's
settlement contract. Preparation requires a matching challengeable on-chain batch
whose challenge period has elapsed. It does not submit a transaction or mint SUN;
the authorized wallet signs both governance steps and the worker issues SUN after
confirmed finalization.

The live schema also includes energy and historical marketplace/community endpoints.
Their presence does not make them active native ETH marketplace routes. No registered
redemption HTTP router or global community directory is provided by `src.main`.

## Schema-derived examples

A home creation request uses [HomeCreateModel](../apps/backend/src/modules/home/schemas.py):

```http
POST /api/v1/home/
Authorization: Bearer <access-token>
Content-Type: application/json
```

```json
{
  "name": "Solar home",
  "address": "Calle 10 #20-30",
  "city": "Cali",
  "country": "Colombia",
  "timezone": "America/Bogota",
  "installed_capacity_w": 4000,
  "has_battery": true
}
```

The response wrapper is `{"message": "Home created successfully", "home": ...}`;
`owner_id` comes from the authenticated user. Device creation uses
[DeviceCreateModel](../apps/backend/src/modules/device/schemas.py):

```json
{
  "home_id": "11111111-1111-4111-8111-111111111111",
  "device_code": "SM-EXAMPLE-001",
  "device_type": "SMART_METER",
  "telemetry_source": "SIMULATED",
  "mqtt_client_id": "meter-example-001"
}
```

Send it to `POST /api/v1/device/device` after replacing the illustrative home UUID
with an owned home. Device activation, node authorization and credential provisioning
are separate. This body does not make a meter eligible for settlement.

`POST /api/v1/communities/{community_id}/settlements/calculate` takes
`{"interval_start": "2026-11-10T17:00:00Z"}`; the time must be aligned, closed and
supported by actual evidence. `BatchView.total_due_wei` and other monetary fields
are decimal integer strings, such as `"3000000000000000"`. Never parse financial
quantities through JavaScript floating-point numbers.

## Pagination, errors and health

Settlement/history/quality lists generally use `limit` (default 50, maximum 100)
and nonnegative `offset`; claim lists also accept `kind=0` or `kind=1`. Defaults vary
on other routes; use their actual OpenAPI parameters. Empty home/device lists can
return 404 rather than `[]`; the frontend normalizes only the known empty cases.

Request validation returns 422 with FastAPI's validation details. Domain
`ValueError`, `PermissionError`, `LookupError` and database integrity conflicts map
to 422, 403, 404 and 409 with a `detail` field. Authentication errors use registered
application error responses; consumers must not assume one universal error shape.
See [errors](../apps/backend/src/core/errors.py).

`GET /health` checks API/database liveness. `GET /ready` additionally checks Redis,
RPC chain match and fresh worker/subscriber heartbeats, returning 503 when degraded.
Neither endpoint proves physical evidence correctness or completion of a particular
settlement. Frontend `/health` checks static serving only.

## Frontend contract maintenance

The [frontend OpenAPI snapshot](../apps/frontend/scripts/openapi.json) and
[generated types](../apps/frontend/src/shared/api/generated.ts) are the retained
API reference artifacts. Some routes return untyped JSON and require explicit
adapter models. Update the snapshot from the running current API and run
`npm run generate:api` in `apps/frontend`, then typecheck and test the adapter.
The separate `docs/openapi_v2.yaml` is an obsolete snapshot retained as a non-Markdown
historical artifact; it is not the contract for this application.
