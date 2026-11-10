# Redemptions

A redemption request identifies the authenticated user, a verified wallet, token quantity, compensation amount/currency, and lifecycle status. Approval and blockchain token operations are distinct from any external bank or utility settlement.

External payment evidence belongs in `redemption_settlements`. A completed token transaction must not be reported as a completed external payment unless the settlement worker has independent confirmation.
