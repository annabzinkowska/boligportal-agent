from pathlib import Path

import pytest
import yaml

from filters import match

CONFIG = yaml.safe_load((Path(__file__).parents[1] / "config.yaml").read_text())


def listing(**overrides):
    base = {
        "postal_code": 2100,
        "district": "København Ø",
        "rooms": 2,
        "monthly_rent": 12000,
        "aconto": 1000,
        "rental_period_months": 0,
        "available_from": "2026-12-15",
    }
    return base | overrides


def test_solo_match():
    result = match(listing(), CONFIG)
    assert result.profile == "solo"
    assert result.warnings == []


@pytest.mark.parametrize("rent, aconto, profile", [
    (13000, 1000, "solo"),       # exactly 14,000 incl. aconto
    (13000, 1001, None),         # 14,001
    (17500, 1500, "shared"),     # exactly 19,000
    (17500, 1501, None),
])
def test_rent_boundaries(rent, aconto, profile):
    rooms = 2 if rent < 15000 else 3
    assert match(listing(rooms=rooms, monthly_rent=rent, aconto=aconto), CONFIG).profile == profile


def test_shared_match_with_four_rooms():
    assert match(listing(rooms=4, monthly_rent=17000, aconto=1500), CONFIG).profile == "shared"


def test_one_room_rejected():
    assert match(listing(rooms=1), CONFIG).profile is None


@pytest.mark.parametrize("months, ok", [(0, True), (23, False), (24, True), (36, True)])
def test_lease(months, ok):
    assert (match(listing(rental_period_months=months), CONFIG).profile is not None) == ok


@pytest.mark.parametrize("day, ok", [
    ("2026-11-30", False), ("2026-12-01", True), ("2027-01-31", True), ("2027-02-01", False),
])
def test_move_in_window(day, ok):
    assert (match(listing(available_from=day), CONFIG).profile is not None) == ok


@pytest.mark.parametrize("postcode, ok", [
    (1050, True), (1620, True), (2100, True), (2200, True), (2400, True),
    (2300, False), (2500, False), (2000, False),
])
def test_postcodes(postcode, ok):
    assert (match(listing(postal_code=postcode), CONFIG).profile is not None) == ok


def test_district_used_when_postcode_missing():
    assert match(listing(postal_code=None, district="København NV"), CONFIG).profile == "solo"
    assert match(listing(postal_code=None, district="København S"), CONFIG).profile is None


def test_missing_fields_pass_with_warnings():
    result = match(listing(postal_code=None, district=None, rental_period_months=None,
                           available_from=None, aconto=None), CONFIG)
    assert result.profile == "solo"
    assert set(result.warnings) == {"area unknown", "lease length unknown",
                                    "move-in date unknown", "aconto unknown, compared rent only"}


def test_unknown_rooms_falls_through_to_shared_on_budget():
    result = match(listing(rooms=None, monthly_rent=16000, aconto=1000), CONFIG)
    assert result.profile == "shared"
    assert "room count unknown" in result.warnings
