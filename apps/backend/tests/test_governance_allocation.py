import pytest
from src.modules.community.allocation import allocate


def test_allocation_conserves_energy_and_is_independent_of_input_order():
    assert (
        allocate(5, {"b": 3, "a": 3})
        == allocate(5, {"a": 3, "b": 3})
        == {"a": 3, "b": 2}
    )
    assert allocate(100, {"a": 3, "b": 2}) == {"a": 3, "b": 2}
    assert allocate(0, {"a": 3}) == {"a": 0}
    assert allocate(5, {}) == {}


@pytest.mark.parametrize("available,withdrawals", [(-1, {"a": 2}), (1, {"a": -2})])
def test_invalid_measurements_cannot_be_allocated(available, withdrawals):
    with pytest.raises(ValueError):
        allocate(available, withdrawals)
