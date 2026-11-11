# Security and trust assumptions

This is a technical prototype without an independent production security audit.
The executed checks and their limits are in [verification report](docs/verification.md).

## Trust boundaries

- **Physical truth:** a blockchain receipt does not prove a meter is calibrated,
  tamper-resistant or reporting physical reality. Node ownership, meter identity,
  signed wallet challenges, device credentials, schema validation, timestamps,
  sequences, counters and plausibility checks establish a controlled input path.
  Real deployment still needs installation approval, metrology, credential security
  and independent evidence review. Simulated sources are labeled and permitted only
  by explicit community policy. The finite 5/3-kWh fixture uses authoritative grid
  counters; it does not infer gross PV production from export or invent missing
  inverter/battery readings. Full simulated energy-balance identities are separately
  exercised by the physics tests.
- **Governance:** registry and settlement administration belong to a timelock.
  Proposer/executor roles must represent the authorized organization or multisig.
  Proposal creation, application login and operator appointment confer different
  permissions. The local zero-delay authority is a fixture convenience, never the
  public-testnet deployment policy. A compromised authorized governance authority
  can change roles/policies; this is not a permissionless or legally authorized DAO.
- **Oracle:** the dedicated backend signer submits approved source commitments and
  processes protocol-approved allocation operations. It is distinct from governance
  and participant keys, has no vault sweep, and cannot sign user withdrawals. Source
  verification and governance finalization remain trusted review steps.
- **Custody:** participant deposits, SUN approvals, escrows, withdrawals and retirements
  require the participant's wallet signature. The frontend never handles private keys.
  Local fixture keys are generated from an ignored private seed, encrypted at rest,
  and unlocked only on a guarded Anvil chain. Never use these fixtures on Sepolia.
- **Infrastructure:** authenticated RPC, database, Redis and MQTT services are trusted
  operational dependencies. Use per-device broker ACLs/TLS across untrusted networks.
  The anonymous broker and default database passwords are local-loopback development
  settings. Keep secrets in environment settings/ignored files and access controls.

## Financial and evidence invariants

- All money is integer wei; SUN uses 18 decimals; one Wh maps to 10^15 SUN units.
  Energy allocation is bounded by eligible injection and demand, with immutable
  policy/evidence references. A finalized interval cannot be issued or settled twice.
- Vault ETH backs available deposits, reservations and producer earnings. Reserved
  ETH/SUN cannot be withdrawn or spent again. Delivery moves SUN and settles ETH
  atomically. Failed/reentrant withdrawals preserve liabilities and state.
- Consumer retirement requires a finalized, authorized, delivered consumption claim,
  the correct SUN allowance and a valid Merkle proof. Burning SUN does not collect
  another ETH payment. Utility bills and physical power routing remain external.
- Submitted transactions do not establish payment. Receipt depth, canonical block
  hashes, expected contracts/functions/events and confirmed index projections are
  checked. Replacements retain nonce/calldata and earlier hashes for reconciliation.
  Failed or ambiguous actions are not retried as new participant payments.
- A signed oracle operation is committed before broadcast. Nonces are coordinated
  under a database advisory lock and scoped to chain ID, **genesis hash**, sender and
  nonce. The genesis binding prevents a fresh local chain with a reused chain ID from
  inheriting stale nonce allocations or automatically replaying old raw signatures.
- Migration `20261111_chain_identity` preserves older journal rows with an unknown
  genesis rather than inventing their origin. Unanchored pending operations are
  quarantined as BLOCKED/FAILED and require explicit receipt review. On a local reset,
  drop a reviewed orphaned pending oracle transaction from the test node before an
  explicit retry if needed. Never apply that local RPC procedure to public accounts.
  Existing canonical confirmations must be reconciled, not paid again.
- Missing deployment bytecode marks native batches and previously confirmed native
  transaction projections RECONCILIATION_REQUIRED. Missing contracts do not cause
  silent activation, reissuance or new settlement. Keep database and EVM history
  together; preserve historical states when persisting Anvil. A real reorganization
  is handled by canonical receipt/event checks and review states, not optimistic
  balances. Deep/public reorganization handling still needs an operational runbook.

## Logging, privacy and recovery

Structured worker logs carry counts, latency, event names and exception types, not
telemetry credentials, signing keys, raw signed transactions or provider exception
arguments. Settings errors hide input values. Broker credentials are removed from
persisted telemetry and quality digests. The dedicated migration service applies
reviewed revisions; it never generates schema changes at startup. API/worker/subscriber
images run without root privileges. Build contexts exclude environment/fixture files.

Readiness distinguishes database, Redis, matching RPC, worker progress and MQTT
connectivity. Community operation counters/lag/alerts require an active operator;
private allocations, claims and balances remain participant-scoped. The transaction
journal in a browser is a recovery aid, not the canonical ledger or cross-device
history. Back up private database journals and node history with suitable controls.

The authenticated APIs still use browser-readable bearer tokens because the backend
has no HTTP-only cookie authentication flow. Production hardening, key management,
independent audits, high availability and a complete WCAG review remain necessary.
Sepolia ETH is a valueless test asset; SUN is an eligible energy credit, not a fiat
promise. Neither local execution nor a Sepolia deployment establishes legal authority
to sell electricity or changes an official electricity bill.

## Known authentication and operational gaps

Passwords use bcrypt. Refresh tokens are JWTs, not opaque rotating tokens; logout
revokes only the presented access-token JTI through Redis. Browser-readable
`sessionStorage` tokens require careful cross-site scripting prevention. Mail/reset
code exists but the canonical stack does not deploy its Celery mail worker;
production reset-token expiry and delivery hardening need separate review.

The repository does not define an official private vulnerability-disclosure contact
or supported-version policy. No contact address is invented here. Do not disclose
secrets or exploit details through a public issue without first establishing an
appropriate private channel with the repository owner.
