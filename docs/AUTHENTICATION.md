# Authentication

Passwords are hashed with Argon2id. Access tokens are short-lived JWTs. Refresh tokens are opaque random values stored only as SHA-256 hashes and rotated on use; a used or expired token cannot be reused.

Wallet linking initially creates an unverified wallet record. A production wallet flow must issue a short-lived challenge, verify an EIP-191 signature, consume the challenge once, and only then mark the wallet verified. Private keys are never accepted or stored by the backend.

Administrative operations must require an administrator role and should be audited. Authentication failures must not reveal whether an email exists.
