"""Deterministic proportional allocation in integer Wh, independent of money."""

from collections.abc import Mapping


def allocate(injection_wh: int, withdrawals: Mapping[str, int]) -> dict[str, int]:
    if injection_wh < 0 or any(value < 0 for value in withdrawals.values()):
        raise ValueError("Nonnegative verified energy is required")
    total = sum(withdrawals.values())
    available = min(injection_wh, total)
    if not total:
        return {key: 0 for key in sorted(withdrawals)}
    result = {key: available * value // total for key, value in withdrawals.items()}
    # Largest remainder, stable node/interval identity breaks ties.
    priority = sorted(
        withdrawals, key=lambda key: (-(available * withdrawals[key] % total), key)
    )
    for key in priority[: available - sum(result.values())]:
        result[key] += 1
    return dict(sorted(result.items()))
