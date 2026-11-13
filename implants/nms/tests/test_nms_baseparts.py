"""Base-part categories: build-menu groups -> the fixed functional categories (#30)."""

import pytest
from nmslib import baseparts


@pytest.mark.parametrize("part_id, groups, expected", [
    # a subgroup that holds one function names it
    ("U_SOLAR_S", [["POWER", "POWERPOWER"]], "power"),
    ("U_SWITCHPROX", [["POWER", "POWERSWITCHES"]], "power"),
    ("CONTAINER3", [["BASE_TECH", "TECHSTORAGE"]], "storage"),
    ("PLANTER", [["BASE_TECH", "TECHFARMING"]], "farming"),
    ("SNOWPLANT", [["FREIGHTER_BIO", "FRE_PLANTS"], ["BIGGS_LOW_PERF", "BIGGSFARMING"]], "farming"),
    ("U_EXTRACTOR_S", [["POWER", "POWERINDUSTRY"]], "extraction"),
    ("GARAGE_M", [["PLANET_TECH", "PLANETEXOCRAFT"]], "travel"),
    ("NPCSCIENCETERM", [["BASE_TECH", "TECHTEMINALS"]], "terminals"),
    ("B_GEN_0", [["BIGGS_CORE", "BIGGS_GENERATOR"]], "corvette_modules"),
    ("B_TUR_A", [["BIGGS_CORE", "BIGGS_GUNS"]], "corvette_modules"),
    # mixed subgroups: the part's own function wins over its subgroup's
    ("BASE_FLAG", [["PLANET_TECH", "PLANETPORTABLE"]], "base_computer"),
    ("COOKER", [["PLANET_TECH", "PLANETPORTABLE"], ["FREIGHTER_TECH", "FRE_TECH_OTHER"]], "utility"),
    ("BUILD_REFINER1", [["PLANET_TECH", "PLANETPORTABLE"], ["FREIGHTER_TECH", "FRE_TECH_OTHER"]], "refining"),
    ("BUILD_REFINER3", [["BASE_TECH", "TECHTECH"]], "refining"),
    ("BUILDHARVESTER", [["PLANET_TECH", "PLANETPORTABLE"]], "extraction"),
    ("TELEPORTER", [["BASE_TECH", "TECHTECH"]], "travel"),
    ("BUILDLANDINGPAD", [["BASE_TECH", "TECHTECH"]], "travel"),
    ("FRE_ROOM_REFINE", [["FREIGHTER_IND", "FRE_IND_SUB"], ["SPACE", "SPACE_IND_SUB"]], "refining"),
    ("FRE_ROOM_NPCSCI", [["FREIGHTER_TECH", "FRE_TECH_SUB"], ["SPACE", "SPACE_TECH_SUB"]], "terminals"),
    # every chest the inventory reads is storage, whatever menu it sits in
    ("FRE_ROOM_STORE0", [["FREIGHTER_IND", "FRE_IND_SUB"], ["SPACE", "SPACE_IND_SUB"]], "storage"),
    ("S_CONTAINER2", [["FREIGHT_LEGACY", "FREIGHTERLEGACY"]], "storage"),
    # structural and decor: no category
    ("F_WALL", [["BASIC_F", "F_WALLS"]], None),
    ("MAINROOM", [["ROOMS", "ROOMSMAIN"]], None),
    ("B_STR_R_N", [["BIGGS_EXT", "BIGGS_STRUCT"]], None),
    ("S_POSTER0", [["WALL_ART", "WALLPOSTERS"]], None),
    ("FRE_ROOM_IND", [["FREIGHTER_IND", "FRE_IND_SUB"], ["SPACE", "SPACE_IND_SUB"]], None),  # an empty expansion
    ("CORRIDOR_SPACE", [["FREIGHT_LEGACY", "FREIGHTERLEGACY"]], None),
    ("WALL", [], None),  # no build-menu group
    ("NEW_PART", [["SOMETHING", "UNKNOWN_SUB"]], None),
    # wires and pipes are structural even though they sit in a functional subgroup
    ("U_POWERLINE", [["POWER", "POWERPOWER"]], None),
    ("U_PIPELINE", [["POWER", "POWERINDUSTRY"]], None),
    ("U_PORTALLINE", [["BASE_TECH", "TECHTECH"], ["FREIGHTER_TECH", "FRE_TECH_OTHER"]], None),
])
def test_a_part_is_categorised_by_its_build_menu_groups(part_id, groups, expected):
    assert baseparts.category_of(part_id, groups) == expected


def test_categories_are_the_fixed_list():
    assert baseparts.CATEGORIES == ("power", "storage", "refining", "farming", "extraction", "travel",
                                    "terminals", "utility", "base_computer", "corvette_modules")


def test_the_bundled_map_categorises_a_placed_part():
    assert baseparts.category("U_SOLAR_S") == "power"
    assert baseparts.category("^BUILD_REFINER2") == "refining"  # the save's caret is ignored
    assert baseparts.category("NOT_A_PART") is None
