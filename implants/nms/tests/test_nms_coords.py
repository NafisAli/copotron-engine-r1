import json
from pathlib import Path

import pytest
from nmslib.coords import SAME_REGION_LY, Address, parse_galaxy, parse_glyphs

ORACLES = json.loads((Path(__file__).parent / "fixtures" / "address-oracles.json").read_text(encoding="utf-8"))
CASES = ORACLES["discovery"] + ORACLES["bases"]


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_packed56_matches_game_confirmed_oracles(case):
    a = Address.from_packed56(case["input"])
    e = case["expected"]
    assert (a.planet, a.system, a.galaxy, a.x, a.y, a.z) == (
        e["planet_index"], e["solar_system_index"], e["reality_index"],
        e["voxel_x"], e["voxel_y"], e["voxel_z"])
    assert a.glyphs == e["portal"]


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_every_notation_round_trips(case):
    a = Address.from_packed56(case["input"])
    assert Address.from_glyphs(a.glyphs, a.galaxy) == a
    assert Address.from_glyphs(a.glyph_emoji, a.galaxy) == a
    assert Address.from_signal_booster(a.signal_booster, a.galaxy, a.planet) == a
    assert Address.from_packed48(a.packed48, a.galaxy) == a


def test_signal_booster_known_value():
    a = Address(0, 1701, -2, -578, 95, 0)
    assert a.signal_booster == "0EA4:007D:05BD:005F"
    assert a.glyphs == "005FFEDBE6A5"


def test_glyph_names_and_separators():
    assert parse_glyphs("sunset:sunset:balloon:atlas:atlas:tree:rocket:whale:tree:boat:voxel:balloon") == "005FFEDBE6A5"
    assert parse_glyphs("005F FEDB E6A5") == "005FFEDBE6A5"


def test_hex_spelling_a_glyph_name_stays_hex():
    assert parse_glyphs("0FACE0000000") == "0FACE0000000"


@pytest.mark.parametrize("bad", ["123", "0123456789ABC", "ZZZZZZZZZZZZ"])
def test_bad_glyphs_raise(bad):
    with pytest.raises(ValueError):
        parse_glyphs(bad)


def test_galaxy_selection():
    assert parse_galaxy("Eissentam") == 9
    assert parse_galaxy("#10") == 9
    assert parse_galaxy("9") == 9
    with pytest.raises(ValueError):
        parse_galaxy("Narnia")


def test_distance_rules():
    a = Address(0, 0, 0, 0, 1, 0)
    assert a.distance_ly(Address(0, 0, 0, 0, 1, 3)) == 0.0  # same system, other planet
    assert a.distance_ly(Address(0, 0, 0, 0, 2, 0)) == SAME_REGION_LY
    assert a.distance_ly(Address(0, 3, 0, 4, 1, 0)) == 2000.0
    assert a.distance_ly(Address(1, 0, 0, 0, 1, 0)) is None  # galaxies don't connect


def test_packed56_rejects_overwide_values():
    with pytest.raises(ValueError):
        Address.from_packed56("0x100000000000000")
    with pytest.raises(ValueError):
        Address.from_packed56(-1)
