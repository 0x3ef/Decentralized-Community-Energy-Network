# Architecture Decisions

## Confirmed decisions

1. **Schema ownership.** SQLAlchemy metadata plus Alembic is the canonical
   relational schema. `database/schema_v2.sql` is a reproducible bootstrap
   artifact, not a second application schema.
2. **Raw telemetry first.** MQTT/gRPC envelopes are validated, deduplicated,
   and stored before typed readings or interval calculations. Raw payloads are
   retained for audit and recalculation.
3. **Idempotency.** Telemetry is unique by device and sequence; an energy
   interval is unique by home and time window; a credit and issuance are unique
   per interval/credit.
4. **Access control.** Household energy and devices require a home membership.
   Administrative aggregation and state-changing settlement operations require
   an administrator or worker identity.
5. **Blockchain confirmation.** Submission is not confirmation. Transaction
   rows remain `submitted` until receipt status and the expected event are
   verified.
6. **Outbox.** Database state changes and `outbox_events` are committed in one
   transaction. Workers claim bounded batches, retry with backoff, and
   dead-letter exhausted or unknown event types.
7. **Canonical registration.** User creation is owned by the authentication
   router at `/api/v1/auth/register`; the users router contains only
   authenticated user and wallet resources, avoiding duplicate registration
   semantics.

## Recommendations requiring product approval

### Energy eligibility

The implementation currently treats measured grid export as the upper bound for
eligible export and records a calculation version. Product must approve the
final rule for missing samples, maximum gap duration, meter rollover, and
whether battery discharge can qualify. Recommended policy: reject incomplete
windows, never infer missing energy, and preserve rejected intervals with a
reason.

### SUN issuance

Recommended lifecycle:
`eligible -> issuance_pending -> submitted -> confirmed` with explicit
`failed` and retry states. Mint exactly `eligible_export_wh` converted by a
versioned, configurable unit rule. Never overwrite a confirmed issuance.

### Marketplace settlement

The current boundary is off-chain order matching with a pending trade record.
Product must choose between (a) custodial escrow and backend settlement or (b)
contract escrow and on-chain settlement. Contract escrow is safer for
non-custodial ownership but adds gas, nonce, and reconciliation complexity.
Until selected, no API should claim that a pending trade transferred tokens.

### Redemption

Before approval, tokens must be reserved so the same credit cannot be sold and
redeemed simultaneously. Recommended implementation is a reservation ledger
with an expiry and compensating release on rejection/failure. This is not yet
represented by a dedicated table and is a remaining implementation item.

### Device authentication

Device codes are identifiers, not credentials. Production provisioning should
issue hashed credentials, support rotation/revocation, and authenticate MQTT
connections independently of user JWTs. Sequence monotonicity and duplicate
replay rejection remain mandatory.

### TimescaleDB retention

TimescaleDB is enabled, but hypertable conversion is deferred for both current
high-volume tables. `telemetry_messages` remains a relational table because
its global unique
`(device_id, sequence_number)` idempotency constraint cannot be preserved by a
Timescale hypertable unless the time column is part of the key.
`energy_intervals` also requires a composite time-aware key migration because
its UUID primary key is referenced by credits and revisions. No retention
policy is enabled in `schema_v2.sql` because legal/audit retention duration is
not defined.

## Remaining technical debt

- Typed-reading normalization is not yet a separate worker for every sensor type.
- Credit reservation is not yet a first-class ledger.
- Marketplace concurrency needs a PostgreSQL integration test with two
  independent transactions.
- Device provisioning/credential rotation endpoints need an admin-only API.
- Blockchain event indexing and nonce coordination need a dedicated production
  worker and reconciliation schedule.
