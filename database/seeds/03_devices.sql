-- database/seeds/03_devices.sql
--
-- Devices matching the device_code convention produced by
-- `iot/config/homes.py`.
--
-- Convention: <PREFIX>-<CITY>-<home_suffix>-<index>
--   PREFIX : SM  = smart_meter
--            INV = solar_inverter
--            WS  = weather_sensor
--            BM  = battery_monitor
--   index  : position in the SensorType enum
--            1 = smart_meter, 2 = solar_inverter,
--            3 = weather_sensor, 4 = battery_monitor
--
-- Every home is a prosumer. The presence of an inverter depends on the
-- home having PV capacity (solar_kw > 0); the presence of a battery
-- monitor depends on the home having storage (battery_kwh > 0). A
-- smart meter and a weather sensor are present in every home.
--
--   HOME-MS-001: PV + battery → SM, INV, WS, BM
--   HOME-MS-002: PV only      → SM, INV, WS
--   HOME-MS-003: no PV        → SM, WS
--   HOME-MS-004: battery only → SM, WS, BM
--   HOME-MS-005: PV only      → SM, INV, WS
--
-- Homes without PV are net buyers in most intervals, but they still
-- participate in the market: they can buy SUN tokens from the other
-- homes whenever their net balance is negative. Homes with PV but no
-- battery are net sellers during the day and net buyers at night.

INSERT INTO devices (
    id, home_id, device_code, device_type, status
) VALUES

    -- ---------------------------------------------------------------------
    -- HOME-MS-001: PV + battery → SM, INV, WS, BM
    -- ---------------------------------------------------------------------
    ('a0000000-0000-0000-0000-000000000001',
     'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
     'SM-MS-001-001',  'smart_meter',     'active'),
    ('a0000000-0000-0000-0000-000000000002',
     'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
     'INV-MS-001-002', 'solar_inverter',  'active'),
    ('a0000000-0000-0000-0000-000000000003',
     'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
     'WS-MS-001-003',  'weather_sensor',  'active'),
    ('a0000000-0000-0000-0000-000000000004',
     'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
     'BM-MS-001-004',  'battery_monitor', 'active'),

    -- ---------------------------------------------------------------------
    -- HOME-MS-002: PV only → SM, INV, WS
    -- ---------------------------------------------------------------------
    ('b0000000-0000-0000-0000-000000000001',
     'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
     'SM-MS-002-001',  'smart_meter',     'active'),
    ('b0000000-0000-0000-0000-000000000002',
     'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
     'INV-MS-002-002', 'solar_inverter',  'active'),
    ('b0000000-0000-0000-0000-000000000003',
     'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
     'WS-MS-002-003',  'weather_sensor',  'active'),

    -- ---------------------------------------------------------------------
    -- HOME-MS-003: no PV, no battery → SM, WS
    -- ---------------------------------------------------------------------
    ('c0000000-0000-0000-0000-000000000001',
     'cccccccc-cccc-cccc-cccc-cccccccccccc',
     'SM-MS-003-001',  'smart_meter',     'active'),
    ('c0000000-0000-0000-0000-000000000003',
     'cccccccc-cccc-cccc-cccc-cccccccccccc',
     'WS-MS-003-003',  'weather_sensor',  'active'),

    -- ---------------------------------------------------------------------
    -- HOME-MS-004: battery only → SM, WS, BM
    -- ---------------------------------------------------------------------
    ('d0000000-0000-0000-0000-000000000001',
     'dddddddd-dddd-dddd-dddd-dddddddddddd',
     'SM-MS-004-001',  'smart_meter',     'active'),
    ('d0000000-0000-0000-0000-000000000003',
     'dddddddd-dddd-dddd-dddd-dddddddddddd',
     'WS-MS-004-003',  'weather_sensor',  'active'),
    ('d0000000-0000-0000-0000-000000000004',
     'dddddddd-dddd-dddd-dddd-dddddddddddd',
     'BM-MS-004-004',  'battery_monitor', 'active'),

    -- ---------------------------------------------------------------------
    -- HOME-MS-005: PV only → SM, INV, WS
    -- ---------------------------------------------------------------------
    ('e0000000-0000-0000-0000-000000000001',
     'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee',
     'SM-MS-005-001',  'smart_meter',     'active'),
    ('e0000000-0000-0000-0000-000000000002',
     'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee',
     'INV-MS-005-002', 'solar_inverter',  'active'),
    ('e0000000-0000-0000-0000-000000000003',
     'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee',
     'WS-MS-005-003',  'weather_sensor',  'active')

ON CONFLICT (device_code) DO NOTHING;