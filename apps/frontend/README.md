# SolarMarket frontend

React 19, Vite, strict TypeScript, Tailwind CSS, TanStack Query, Recharts and viem.

```bash
cd apps/frontend
npm ci
npm run dev -- --host 127.0.0.1
npm run build
npm run lint
npm test
npx playwright test
```

Start the real backend with the root README instructions before Playwright. Browser
tests use localhost:8000 and the Vite server on localhost:5173. The test configuration
uses system Chromium at /usr/bin/chromium in the managed environment; change that
path for another machine. Configure VITE_API_BASE_URL for a different API origin.
No deployed contract addresses or user private keys are bundled in the frontend.

The workspace views use actual supported API endpoints: community statements,
homes/devices, UTC energy intervals, credits and issuance operations, simulated
payments, retirements and a paginated accounting ledger. Empty results remain empty.
Community selection is restricted to memberships returned by the backend. Charts
show accumulated Wh, never instantaneous W. Queries poll only while mounted and
pass cancellation signals where supported; financial mutations do not auto-retry.

Wallet transactions require the linked account and configured chain. Quotes use
integer arithmetic with distinct SUN/USDx decimals, round payment dust upward,
and reject insufficient funds/allowance. Receipt confirmation precedes reconciliation.
Submitted hashes remain visible for recovery; an unknown outcome is not labelled
as a failed payment that is safe to repeat. Application login and wallet ownership
remain separate challenges. Tokens use the backend's existing bearer-token storage;
HTTP-only authentication cookies are not currently supported by the backend.

## Verified in the cloud environment

- Production TypeScript/Vite build passed, with the advisory main-bundle size warning.
- 15 Vitest unit, component and community-selection hook tests passed.
- 2 Playwright tests passed against the real backend: protected navigation and an
  authenticated community creation/overview/mobile navigation flow.
- Oxlint passed with two Fast Refresh export-organization advisories.
- Heavy chart views are loaded as a separate route chunk.

## Remaining integration boundaries

The backend has no membership-list endpoint or permission-capabilities response,
so the frontend does not fabricate member lists or grant administrator permissions.
Raw power/battery detail and fine-grained measurement filters require additional
telemetry schemas and UI work. The existing transaction controls still require
source/withdrawal UUID selection; a guided eligibility selector needs a dedicated
backend eligibility API. There is no WebSocket endpoint; controlled polling is used.
Public explorer links require an explorer configuration, which is absent for the
local chain. Wallet-extension trade/burn automation, complete keyboard-accessibility
review and production security review remain unverified. USDx is unbacked simulated
payment points; no real currency conversion or utility bill compensation is claimed.
