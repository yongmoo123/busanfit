"""validate_open_hours — proposed (임시) open_hours shape, 김영무 확인 대기. [가상] values only."""
import pytest

from app.domain.place import WEEKDAY_KEYS, validate_open_hours


@pytest.mark.parametrize("parsed", [
    {},                                                                  # every day unknown
    {"mon": [{"open": "09:00", "close": "18:00"}]},                      # other days unknown
    {"tue": []},                                                         # confirmed closed
    {"wed": [{"open": "10:00", "close": "12:00"}, {"open": "13:00", "close": "18:00"}]},
    {"fri": [{"open": "18:00", "close": "02:00"}]},                      # past midnight
    {"sat": [{"open": "00:00", "close": "23:59"}]},
    {day: [{"open": "09:00", "close": "18:00"}] for day in WEEKDAY_KEYS},
])
def test_valid_shapes(parsed):
    validate_open_hours(parsed)


@pytest.mark.parametrize("parsed", [
    {"monday": []}, {"Mon": []}, {"holiday": []}, {1: []},               # day keys
])
def test_rejects_unknown_day_key(parsed):
    with pytest.raises(ValueError, match="weekday key"):
        validate_open_hours(parsed)


@pytest.mark.parametrize("value", ["9:00", "09:0", "0900", "24:00", "23:60", "09:00:00",
                                   " 09:00", "09:00 ", "", None, 900])
def test_rejects_bad_hh_mm(value):
    with pytest.raises(ValueError, match="HH:mm"):
        validate_open_hours({"mon": [{"open": value, "close": "18:00"}]})
    with pytest.raises(ValueError, match="HH:mm"):
        validate_open_hours({"mon": [{"open": "09:00", "close": value}]})


def test_rejects_open_equal_close():
    with pytest.raises(ValueError, match="differ"):
        validate_open_hours({"sun": [{"open": "09:00", "close": "09:00"}]})


@pytest.mark.parametrize("parsed", [
    None, [], "mon", {"mon": None}, {"mon": "09:00-18:00"}, {"mon": [["09:00", "18:00"]]},
    {"mon": [{"open": "09:00"}]}, {"mon": [{"open": "09:00", "close": "18:00", "note": "x"}]},
])
def test_rejects_malformed_structure(parsed):
    with pytest.raises(ValueError):
        validate_open_hours(parsed)
