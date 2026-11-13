"""The Save Delta as a pure function over the model: no save files (#29)."""

import dataclasses

from nmslib.coords import Address
from nmslib.model import Base, Container, Planet, Player, Save, Slot, System
from nmslib.watch import BaseChange, CurrencyChange, ItemChange, save_delta

HERE = Address(0, 10, 0, 10, 5, 1)


def item(item_id, amount, name=None, kind="Substance"):
    return Slot(id=item_id, name=name, amount=amount, max_amount=9999, item_type=kind, damage_factor=0.0,
                fully_installed=True, x=0, y=0)


def grid(owner, *slots, category="suit"):
    return Container(category=category, owner=owner, grid="general", capacity=50, slots=list(slots))


def base(name, a=HERE, parts=(), kind="HomePlanetBase", mine=True, position=(1.0, 2.0, 3.0), updated=100):
    return Base(name=name, kind=kind, address=a, position=position, owner_uid="", owner_name="", is_mine=mine,
                last_update=updated, parts=list(parts))


def system(a, name=None, planets=()):
    return System(address=Address(a.galaxy, a.x, a.y, a.z, a.system, 0), name=name, discoverer=None,
                  discovered_at=None, is_mine=True, planets=list(planets))


def planet(index, name=None, biome="Lush"):
    return Planet(index=index, biome=biome, infested=False, name=name, discoverer=None, is_mine=True, seed=None)


def make_save(here=HERE, containers=(), bases=(), systems=(), units=0, nanites=0, quicksilver=0,
              game_mode="Normal"):
    player = Player(uid=None, location=here, previous_location=None, units=units, nanites=nanites,
                    quicksilver=quicksilver, game_mode=game_mode, context="main", save_name="", save_summary="",
                    play_time_s=0, current_ship=None, ships=[], freighter_name="")
    return Save(file=None, version=0, platform="", player=player, containers=list(containers),
                bases=list(bases), systems={s.address.system_key: s for s in systems}, discoveries=[])


def test_an_identical_save_is_an_empty_delta():
    s = make_save(containers=[grid("Exosuit", item("FUEL1", 10, "Carbon"))], bases=[base("Home")],
                  systems=[system(HERE, "Testoria", [planet(1)])], units=5)
    d = save_delta(s, s)
    assert d.empty
    assert d.to_json() == {"inventory": [], "currencies": [], "discoveries": {"systems": [], "planets": []},
                           "bases": {"added": [], "edited": [], "removed": []}, "location": None,
                           "game_mode": None}


# ---- inventory -------------------------------------------------------------------
def test_inventory_reports_gains_and_losses_by_name_group_with_the_new_total():
    before = make_save(containers=[grid("Exosuit", item("FUEL1", 10, "Carbon"), item("LAND1", 50, "Ferrite Dust"))])
    after = make_save(containers=[grid("Exosuit", item("FUEL1", 130, "Carbon"),
                                       item("YELLOW2", 5, "Copper"))])
    assert save_delta(before, after).inventory == [
        ItemChange("Carbon", ["FUEL1"], 120, 130),
        ItemChange("Copper", ["YELLOW2"], 5, 5),
        ItemChange("Ferrite Dust", ["LAND1"], -50, 0),
    ]


def test_ids_sharing_a_name_are_one_group():
    before = make_save(containers=[grid("Exosuit", item("CV_HYP2", 2, "Hyperdrive", "Product"))])
    after = make_save(containers=[grid("Exosuit", item("CV_HYP2", 1, "Hyperdrive", "Product"),
                                       item("UP_HYP1#4242", 3, "Hyperdrive", "Product"))])
    assert save_delta(before, after).inventory == [ItemChange("Hyperdrive", ["CV_HYP2", "UP_HYP1#4242"], 2, 4)]


def test_moving_stacks_between_containers_is_no_change():
    before = make_save(containers=[grid("Exosuit", item("FUEL1", 100, "Carbon")), grid("Storage 0", category="storage")])
    after = make_save(containers=[grid("Exosuit", item("FUEL1", 40, "Carbon")),
                                  grid("Storage 0", item("FUEL1", 60, "Carbon"), category="storage")])
    assert save_delta(before, after).empty


def test_an_unnamed_id_is_its_own_group():
    after = make_save(containers=[grid("Exosuit", item("NOT_REAL", 3))])
    assert save_delta(make_save(), after).inventory == [ItemChange(None, ["NOT_REAL"], 3, 3)]


def test_technology_counts_installed_slots_not_its_charge():
    jet = lambda charge: item("JET1", charge, "Jetpack", "Technology")  # noqa: E731
    before = make_save(containers=[grid("Exosuit", jet(100))])
    assert save_delta(before, make_save(containers=[grid("Exosuit", jet(37))])).empty
    assert save_delta(before, make_save(containers=[grid("Exosuit", jet(37), jet(80))])).inventory == [
        ItemChange("Jetpack", ["JET1"], 1, 2)]
    assert save_delta(before, make_save()).inventory == [ItemChange("Jetpack", ["JET1"], -1, 0)]


# ---- currencies, location, Game Mode ------------------------------------------------
def test_currencies_report_the_change_and_the_new_balance():
    d = save_delta(make_save(units=5000, nanites=10, quicksilver=7), make_save(units=3800, nanites=58, quicksilver=7))
    assert d.currencies == [CurrencyChange("units", -1200, 3800), CurrencyChange("nanites", 48, 58)]


def test_moving_to_another_planet_or_system_is_a_location_change():
    there = Address(0, 11, 0, 10, 2, 4)
    after = make_save(here=there, systems=[system(there, "Ekoxim", [planet(4, "Ekoxim IV")])])
    d = save_delta(make_save(), after)
    assert (d.location.before, d.location.after, d.location.label) == (HERE, there, "Ekoxim IV")
    to_space = save_delta(make_save(), make_save(here=dataclasses.replace(HERE, planet=0)))
    assert to_space.location.label == f"system {dataclasses.replace(HERE, planet=0).glyphs}"


def test_a_game_mode_change_reports_both_modes():
    assert save_delta(make_save(), make_save(game_mode="Survival")).game_mode == ("Normal", "Survival")


# ---- Discoveries ---------------------------------------------------------------------
def test_new_star_systems_and_planets_are_reported_and_nothing_known_is():
    other = Address(0, 11, 0, 10, 2, 0)
    before = make_save(systems=[system(HERE, "Testoria", [planet(1)])])
    after = make_save(systems=[system(HERE, "Testoria", [planet(1), planet(3, "Glowball", "Toxic")]),
                               system(other, "Ekoxim", [planet(2)])])
    d = save_delta(before, after)
    assert [(p.label, p.address) for p in d.systems] == [("Ekoxim", other)]
    assert [(p.label, p.biome) for p in d.planets] == [("Glowball", "Toxic"), ("Ekoxim planet 2", "Lush")]
    assert save_delta(after, before).systems == [] and save_delta(after, before).planets == []


# ---- Bases ------------------------------------------------------------------------------
def test_own_bases_are_reported_added_edited_and_removed():
    before = make_save(bases=[base("Home", parts=["A"]), base("Camp", position=(9.0, 9.0, 9.0)),
                              base("Old", position=(5.0, 5.0, 5.0))])
    after = make_save(bases=[base("Home", parts=["A", "B", "B"], updated=200),
                             base("Camp", position=(9.0, 9.0, 9.0)), base("New", position=(7.0, 7.0, 7.0))])
    d = save_delta(before, after)
    assert d.bases_added == [BaseChange("New", "HomePlanetBase", HERE, 0, 0, None)]
    assert d.bases_edited == [BaseChange("Home", "HomePlanetBase", HERE, 3, 2, None)]
    assert d.bases_removed == [BaseChange("Old", "HomePlanetBase", HERE, 0, 0, None)]


def test_a_renamed_base_is_edited_not_replaced():
    d = save_delta(make_save(bases=[base("Camp")]), make_save(bases=[base("Lakeside")]))
    assert (d.bases_added, d.bases_removed) == ([], [])
    assert d.bases_edited == [BaseChange("Lakeside", "HomePlanetBase", HERE, 0, 0, "Camp")]


def test_a_base_that_moves_with_the_player_is_the_same_base():
    away = Address(0, 99, 0, 10, 2, 0)
    before = make_save(bases=[base("Ark", kind="FreighterBase", parts=["A"])])
    after = make_save(bases=[base("Ark", a=away, kind="FreighterBase", parts=["A"])])
    assert save_delta(before, after).empty


def test_visited_bases_are_not_reported():
    visited = base("Bazaar", kind="ExternalPlanetBase", mine=False)
    assert save_delta(make_save(), make_save(bases=[visited])).empty


def test_parts_rearranged_without_a_new_timestamp_are_no_edit():
    before = make_save(bases=[base("Home", parts=["A", "B"])])
    assert save_delta(before, make_save(bases=[base("Home", parts=["B", "A"])])).empty
