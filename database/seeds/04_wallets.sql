-- database/seeds/04_wallets.sql
--
-- One EVM wallet per demo user. Each wallet belongs to the user: the
-- application never stores the private key. The user signs transactions
-- with their own wallet (MetaMask in the browser) and only the public
-- address is persisted here.
--
-- The addresses below are deterministic placeholders for the local
-- Anvil network (chain_id = 31337). When running against a real chain,
-- replace them with the addresses the users actually control.
--
-- Every user has exactly one wallet in the demo. The unique constraint
-- on `address` prevents the same wallet from being linked to two users.

INSERT INTO wallets (
    id, user_id, address, chain_id, is_verified
) VALUES
    ('d0000000-0000-0000-0000-000000000001',
     '11111111-1111-1111-1111-111111111111',
     '0x1111111111111111111111111111111111111111',
     31337, TRUE),

    ('d0000000-0000-0000-0000-000000000002',
     '22222222-2222-2222-2222-222222222222',
     '0x2222222222222222222222222222222222222222',
     31337, TRUE),

    ('d0000000-0000-0000-0000-000000000003',
     '33333333-3333-3333-3333-333333333333',
     '0x3333333333333333333333333333333333333333',
     31337, TRUE),

    ('d0000000-0000-0000-0000-000000000004',
     '44444444-4444-4444-4444-444444444444',
     '0x4444444444444444444444444444444444444444',
     31337, TRUE),

    ('d0000000-0000-0000-0000-000000000005',
     '55555555-5555-5555-5555-555555555555',
     '0x5555555555555555555555555555555555555555',
     31337, TRUE)

ON CONFLICT (address) DO NOTHING;