-- database/seeds/02_homes.sql
--
-- Every home is a prosumer: it can produce and consume at the same
-- time. The columns below describe *installed capacity*, not the
-- role the home plays in the market. Whether a home sells or buys
-- in a given interval depends on its net balance
-- (generation_wh - consumption_wh), which is computed by
-- EnergyService and stored in energy_intervals.
--
--   solar_kw   = installed PV capacity in watts (0 = no panels)
--   has_battery = whether the home has storage
--
-- None of these homes is "a producer" or "a consumer" in the
-- abstract: they all buy or sell depending on the interval.
INSERT INTO homes (
    id, owner_id, name, city, country, timezone,
    installed_capacity_w, has_battery, status
) VALUES
    -- HOME-Moscow-001: 4 kW PV + 10 kWh battery.
    -- Can generate surplus during the day, store part of it, sell the rest.
    ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
     '11111111-1111-1111-1111-111111111111',
     'HOME-MS-001', 'Moscow', 'Russia', 'Europe/Moscow',
     4000, TRUE, 'active'),

    -- HOME-Moscow-002: 6 kW PV, no battery.
    -- Sells all surplus immediately; buys from the grid at night.
    ('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
     '22222222-2222-2222-2222-222222222222',
     'HOME-MS-002', 'Moscow', 'Russia', 'Europe/Moscow',
     6000, FALSE, 'active'),

    -- HOME-Moscow-003: no PV, no battery.
    -- Net buyer every interval, but still a market participant
    -- (it can buy SUN tokens from other homes).
    ('cccccccc-cccc-cccc-cccc-cccccccccccc',
     '33333333-3333-3333-3333-333333333333',
     'HOME-MS-003', 'Moscow', 'Russia', 'Europe/Moscow',
     1000, FALSE, 'active'),

    -- HOME-Moscow-004: no PV, 5 kWh battery.
    -- Can charge from the grid when energy is cheap and discharge
    -- when it is expensive, arbitraging the price.
    ('dddddddd-dddd-dddd-dddd-dddddddddddd',
     '44444444-4444-4444-4444-444444444444',
     'HOME-MS-004', 'Moscow', 'Russia', 'Europe/Moscow',
     1000, TRUE, 'active'),

    -- HOME-Moscow-005: 3 kW PV, no battery.
    -- Small producer, sells surplus during the day, buys at night.
    ('eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee',
     '55555555-5555-5555-5555-555555555555',
     'HOME-MS-005', 'Moscow', 'Russia', 'Europe/Moscow',
     3000, FALSE, 'active')
ON CONFLICT DO NOTHING;