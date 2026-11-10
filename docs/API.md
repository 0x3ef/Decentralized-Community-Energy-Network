# API

The FastAPI application exposes Swagger at `/docs` and ReDoc at `/redoc`. All domain endpoints use `/api/v1`.

Core endpoints include:

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `GET /api/v1/auth/me`
- `GET /api/v1/users/me/wallets`
- `POST /api/v1/homes`
- `POST /api/v1/devices`
- `GET /api/v1/energy/homes/{home_id}/intervals`
- `POST /api/v1/marketplace/orders`
- `POST /api/v1/marketplace/fill`
- `POST /api/v1/redemptions`

Use `Authorization: Bearer <access_token>`. Request identity controls ownership; clients must not submit substitute buyer, seller, owner, or user identifiers.
