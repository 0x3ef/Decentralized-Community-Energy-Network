# Marketplace

Orders are represented with side, token amount, remaining amount, price, owner, and status. Matching is backend-controlled for the MVP and uses price-time ordering. Database row locks protect concurrent fills; fills may be partial and every trade is retained.

The service rejects non-positive quantities, prevents self-trading, does not allow remaining amounts to become negative, and keeps cancellation separate from settlement. Final token movement must be confirmed by the blockchain integration.
