-- database/seeds/01_users.sql
--
-- Demo users of the community. Every user can both produce and consume
-- energy: the role in the market depends on the net balance of the
-- home in each interval, not on the user account. The demo community
-- has five users, one per home, so each user owns exactly one
-- installation and one wallet.
--
-- Passwords are intentionally left as NULL in the seed: they are set
-- through the API (`POST /api/v1/auth/register`) which hashes them with Argon2id
-- before storing. The seeds only provide the identity of the accounts
-- so that homes, devices and wallets can be linked to a real user row.

INSERT INTO users (id, email, password_hash, full_name, status)
VALUES
    ('11111111-1111-1111-1111-111111111111',
     'roboute@solar.local', '$argon2id$v=19$m=65536,t=3,p=4$x2yWUv0LvlqY9Wx+HwOyXQ$EhH9Gmrmu1gbgmTCZXjh+XKwhaWYXRjVdyZB81paeJw', 'Roboute Guilliman', 'active'),
    ('22222222-2222-2222-2222-222222222222',
     'ranni@solar.local', '$argon2id$v=19$m=65536,t=3,p=4$x2yWUv0LvlqY9Wx+HwOyXQ$EhH9Gmrmu1gbgmTCZXjh+XKwhaWYXRjVdyZB81paeJw', 'Ranni la Bruja', 'active'),
    ('33333333-3333-3333-3333-333333333333',
     'shadowheart@solar.local', '$argon2id$v=19$m=65536,t=3,p=4$x2yWUv0LvlqY9Wx+HwOyXQ$EhH9Gmrmu1gbgmTCZXjh+XKwhaWYXRjVdyZB81paeJw', 'Corazón Sombrío', 'active'),
    ('44444444-4444-4444-4444-444444444444',
     'malenia@solar.local', '$argon2id$v=19$m=65536,t=3,p=4$x2yWUv0LvlqY9Wx+HwOyXQ$EhH9Gmrmu1gbgmTCZXjh+XKwhaWYXRjVdyZB81paeJw', 'Malenia Miquella', 'active'),
    ('55555555-5555-5555-5555-555555555555',
     'inquisitor@solar.local', '$argon2id$v=19$m=65536,t=3,p=4$x2yWUv0LvlqY9Wx+HwOyXQ$EhH9Gmrmu1gbgmTCZXjh+XKwhaWYXRjVdyZB81paeJw', 'Inquisidor Eisenhorn', 'active')
ON CONFLICT (email) DO NOTHING;