# Prototype implementation architecture

The existing src package, SQLModel tables and FastAPI routers remain canonical.
The application entry point is now src.main:app; importing src no longer boots the
HTTP application during migrations or worker initialization.

```
authorized meter -> MQTT QoS1 -> subscriber -> typed telemetry
    -> energy worker -> counter snapshots -> finalized UTC intervals
    -> operator approval -> transactional outbox -> durable signed chain operation
    -> verified SUN mint -> accounting commitment
user wallet -> SUN escrow / USDx approval -> atomic marketplace fill
    -> receipt + both Transfer events -> simulated payment evidence
consumer withdrawal + issued injection -> locked allocation reservation
    -> operator on-chain authorization -> user-approved SUN burn
    -> verified retirement receipt -> compensated energy + append-only ledger
```

New community tables reference existing users, homes, devices, energy_intervals,
energy_credits and outbox_events. They do not create parallel definitions of those
entities. community_nodes binds a home to one community; membership is many-to-many
between users and communities. Wallet addresses are globally unique and linked by
a single-use signed challenge. Meter credentials are scoped to authorized nodes.

community_energy_allocations stores reserved physical accounting quantities;
compensation_requests combines retirement authorization and confirmation state;
settlement_obligations stores verified simulated payment evidence; the community
ledger connects these operations to source UUIDs and blockchain hashes.
community_chain_deployments selects independent contract boundaries.
community_chain_operations stores signed bytes before broadcast and has a unique
chain/sender/nonce constraint. Signed bytes are not user private keys.

The additive Alembic revisions introduce these tables and the append-only
trigger without resetting existing tables. Old homes and credits are preserved;
operators explicitly associate them with communities rather than assigning an
invented default accounting boundary. Only the dedicated migration service runs
Alembic; API replicas do not create or autogenerate schema.

One dedicated community worker runs interval processing, outbox submission,
confirmed-event synchronization with persisted cursors, and canonical-history audits. Its database locks support multiple workers sharing the
same configured signer, as exercised by integration tests. HTTP workers do not
spawn duplicate background loops. Legacy financial redemption remains a separate
contract and is not used for consumption compensation.

Docker builds use normal TLS verification and optional BuildKit CA mounts for
managed environments. Runtime dependency versions are pinned in requirements.lock;
Solidity sources use OpenZeppelin v5.4.0 and forge-std v1.9.7. Public ABIs are checked
into src/blockchain/abis and regenerated from compiled artifacts after contract
changes. Production secrets are not part of source or the distribution ZIP.
