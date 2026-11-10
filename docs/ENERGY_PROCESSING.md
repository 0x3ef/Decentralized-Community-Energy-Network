# Energy processing

Energy is stored as integer Wh. Instantaneous power is converted with decimal arithmetic: `Wh = W * seconds / 3600`. Interval calculations retain a version and source links.

The initial calculation records generation, consumption, grid import, grid export, battery charge/discharge, and eligible export. Eligible export is based on measured grid export and protocol validation, not simply generation minus consumption. Missing readings contribute no unverified energy; counter resets and quality problems require a new revision or review status rather than silently overwriting history.

The initial conversion rule is `1,000 eligible Wh = 1 SUN`. Token values are persisted as `NUMERIC(38,18)` and converted to ERC-20 base units only at the blockchain boundary.
