# Solar Energy Market frontend

This is the React/Vite application for the Solar Energy Market platform. It
uses the FastAPI API under `/api/v1` and never connects directly to PostgreSQL
or blockchain signing keys.

## Development

```bash
npm install
cp .env.example .env
npm run dev
```

Set `VITE_API_BASE_URL` to the backend origin, for example
`http://localhost:8000`. The frontend stores the short-lived access token and
rotating refresh token in browser local storage because the current backend
returns JSON tokens rather than HttpOnly cookies. Production should add a
cookie-based session endpoint when deployment security requirements demand it.

## Checks

```bash
npm run lint
npm run build
```

## Docker deployment

The production image is built with `infrastructure/docker/Dockerfile.frontend`
and served by Nginx. The Vite API URL is injected at image build time:

```bash
docker compose -f infrastructure/docker/docker-compose.yml \
  --env-file infrastructure/docker/.env up -d --build frontend
```

Open `http://localhost:8080`. Set `VITE_API_BASE_URL` to the browser-reachable
API origin and include the frontend origin in `CORS_ORIGINS`.

## Architecture

- `src/lib/api.ts` contains the typed Axios client, token refresh interceptor,
  and domain response types.
- `src/shell.tsx` contains protected routing, layouts, reusable dashboard
  components, and domain pages.
- `src/index.css` defines the responsive visual system and accessible states.

The UI only displays values returned by the backend. Unsupported actions such
as administrative redemption approval and direct blockchain signing are not
presented to regular users.

## Backend limitations

The current API does not expose a complete portfolio history, transaction
history, or device provisioning endpoint. Those areas use honest empty states
or read-only summaries rather than fabricated data.
