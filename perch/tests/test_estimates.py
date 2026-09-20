import pytest

from perch.core.estimates import load_estimates


def test_blank_low_and_high_mean_a_single_number(world):
    estimates = load_estimates(world.parent / "estimates.csv")
    assert estimates["#1"].low == estimates["#1"].hours == estimates["#1"].high == 15
    assert estimates["#101"].is_issue
    billing = estimates["epic::billing"]
    assert (billing.low, billing.hours, billing.high) == (50, 60, 80)
    assert not billing.is_issue


def test_a_duplicate_key_is_an_error(tmp_path):
    path = tmp_path / "e.csv"
    path.write_text("key,hours,low,high\n#1,5,,\n#1,6,,\n")
    with pytest.raises(ValueError, match="`#1` appears more than once"):
        load_estimates(path)


def test_low_mode_high_must_be_ordered(tmp_path):
    path = tmp_path / "e.csv"
    path.write_text("key,hours,low,high\n#1,5,6,\n")
    with pytest.raises(ValueError, match="low <= hours <= high"):
        load_estimates(path)
