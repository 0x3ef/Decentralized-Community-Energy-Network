# Security

Never commit secrets, private keys, JWT signing keys, or device credentials. Use environment or a managed secret store. Redact credentials and tokens from logs. Apply least-privilege database roles and restrict MQTT topics per device in production.

All authenticated resource queries must enforce ownership or home membership in the service layer. Use parameterized SQLAlchemy statements, bounded pagination, validation, and idempotency keys. Administrative credit, blockchain, and redemption actions require explicit authorization and audit records.
