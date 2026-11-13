"""The Discovery Atlas as pure functions over the model: no save files (#14)."""

import pytest
from nmslib import atlas
from nmslib.coords import SAME_REGION_LY, Address
from nmslib.model import Base, Planet, Player, Save, System


def addr(x=0, y=0, z=0, system=1, planet=0, galaxy=0):
    return Address(galaxy, x, y, z, system, planet)


def planet(index, biome="Lush", name=None, infested=False, mine=False):
    return Planet(index=index, biome=biome, infested=infested, name=name, discoverer=None, is_mine=mine,
                  seed=None)


def system(a, name=None, planets=(), mine=False):
    return System(address=a, name=name, discoverer=None, discovered_at=None, is_mine=mine, planets=list(planets))


def base(name, a, mine=True):
    return Base(name=name, kind="HomePlanetBase" if mine else "ExternalPlanetBase", address=a,
                position=(0.0, 0.0, 0.0), owner_uid="", owner_name="", is_mine=mine, last_update=0, parts=[])


def make_save(here, systems=(), bases=()):
    """A Save built straight from the model: the atlas reads nothing else."""
    player = Player(uid=None, location=here, previous_location=None, units=0, nanites=0, quicksilver=0,
                    game_mode="Normal", context="main", save_name="", save_summary="", play_time_s=0,
                    current_ship=None, ships=[], freighter_name="")
    return Save(file=None, version=0, platform="", player=player, containers=[], bases=list(bases),
                systems={s.address.system_key: s for s in systems}, discoveries=[])


# ---- distance and Warp Jumps --------------------------------------------------
def test_distance_inside_one_star_system_is_zero_and_exact():
    assert atlas.distance(addr(planet=1), addr(planet=3)) == atlas.Distance(0.0, estimate=False)


def test_distance_inside_one_region_is_the_robbins_estimate():
    d = atlas.distance(addr(system=1), addr(system=2))
    assert d == atlas.Distance(SAME_REGION_LY, estimate=True) and round(d.ly) == 265


def test_distance_between_regions_is_euclidean_times_400():
    assert atlas.distance(addr(0, 0, 0), addr(3, 0, 4)) == atlas.Distance(2000.0, estimate=False)


def test_distance_across_galaxies_is_none():
    assert atlas.distance(addr(), addr(galaxy=1)) is None


@pytest.mark.parametrize(("a", "b", "warp_range", "jumps"), [
    (addr(planet=1), addr(planet=2), 100, 0),  # inside one Star System
    (addr(system=1), addr(system=2), 100, 1),  # one Region: exactly one, whatever the range
    (addr(system=1), addr(system=2), 1000, 1),
    (addr(0, 0, 0), addr(3, 0, 4), 500, 4),  # 2000 ly at 500
    (addr(0, 0, 0), addr(3, 0, 4), 450, 5),  # rounded up
])
def test_warp_jumps_are_ly_over_warp_range_rounded_up(a, b, warp_range, jumps):
    assert atlas.warp_jumps(atlas.distance(a, b), warp_range) == jumps


# ---- the name rule ----------------------------------------------------------------
HERE = addr(10, 0, 10, system=5, planet=2, galaxy=3)


def test_here_and_an_empty_name_are_the_player_location():
    s = make_save(HERE)
    for text in ("here", " HERE ", ""):
        p = atlas.resolve(s, text)
        assert (p.kind, p.address) == ("here", HERE)


def test_twelve_portal_glyphs_are_read_in_the_current_galaxy():
    s = make_save(HERE)
    p = atlas.resolve(s, "2005FE00A00A")  # planet 2, system 5, y 0xFE, z 0x00A, x 0x00A
    assert p.kind == "glyphs" and p.address == Address(3, 10, -2, 10, 5, 2)


NAMED = make_save(HERE, systems=[
    system(addr(1, galaxy=3), "Lidfor", [planet(1, name="Lidfor Prime"), planet(2)]),
    system(addr(2, galaxy=3), "Police Box"),
    system(addr(3, galaxy=3)),  # unnamed: never matched by name
], bases=[
    base("Police HQ", addr(4, galaxy=3, planet=1)),
    base("Toxic HQ", addr(5, galaxy=3, planet=1)),
    base("", addr(6, galaxy=3, planet=1)),  # unnamed
    base("Lidfor Outpost", addr(1, galaxy=3, planet=2)),
    base("Bazaar", addr(7, galaxy=3, planet=1), mine=False),
    base("Police Station", addr(8, galaxy=3, planet=1), mine=False),
])


@pytest.mark.parametrize(("text", "kind", "name"), [
    ("lidfor", "system", "Lidfor"),  # an exact Star System beats a Base prefix
    ("Lidfor O", "base", "Lidfor Outpost"),  # a unique prefix
    ("prime", "planet", "Lidfor Prime"),  # a unique substring, in the named-planet tier
    ("police b", "system", "Police Box"),
    ("Toxic", "base", "Toxic HQ"),
])
def test_names_match_exact_then_prefix_then_substring_in_tier_order(text, kind, name):
    p = atlas.resolve(NAMED, text)
    assert (p.kind, p.name) == (kind, name)


def test_on_an_equal_match_an_own_base_beats_a_star_system():
    s = make_save(HERE, systems=[system(addr(1, galaxy=3), "Home")], bases=[base("Home", addr(2, galaxy=3))])
    assert atlas.resolve(s, "home").kind == "base"


def test_a_name_matching_several_places_is_refused_with_up_to_five_candidates():
    s = make_save(HERE, bases=[base(f"HQ {i}", addr(i, galaxy=3)) for i in range(1, 8)])
    with pytest.raises(atlas.Unresolved, match="matches 7 places") as e:
        atlas.resolve(s, "hq")
    assert [p.name for p in e.value.candidates] == ["HQ 1", "HQ 2", "HQ 3", "HQ 4", "HQ 5"]


def test_a_visited_base_is_refused_without_all_and_named_with_the_hint():
    with pytest.raises(atlas.Unresolved, match=r"'Bazaar' is a Visited Base.*--all"):
        atlas.resolve(NAMED, "bazaar")
    p = atlas.resolve(NAMED, "bazaar", include_visited=True)
    assert (p.kind, p.name) == ("visited_base", "Bazaar")


def test_own_places_come_before_visited_bases():
    assert atlas.resolve(NAMED, "police", include_visited=True).name == "Police HQ"  # prefix, Base tier


def test_an_unknown_name_is_refused():
    with pytest.raises(atlas.Unresolved, match="Nothing in this save is called 'Atlantis'"):
        atlas.resolve(NAMED, "Atlantis")


# ---- find ---------------------------------------------------------------------
ORIGIN = addr(0, 0, 0, system=1)
PLANETS = make_save(ORIGIN, systems=[
    system(addr(0, 0, 0, system=1), planets=[planet(1, "Lush", mine=True), planet(2, "Frozen", infested=True)]),
    system(addr(0, 0, 0, system=9), planets=[planet(1, "Lush", name="Eden")]),  # same Region
    system(addr(3, 0, 4, system=2), planets=[planet(4, "Lush", infested=True)]),  # 2000 ly
    system(addr(1, 0, 0, system=3), planets=[planet(2, "Lush", mine=True)]),  # 400 ly
    system(addr(0, 0, 0, system=1, galaxy=1), planets=[planet(1, "Lush"), planet(2, "Lush")]),
])


def found(result):
    return [(f.place.address.system, f.place.address.planet, round(f.distance.ly), f.distance.estimate)
            for f in result.rows]


def test_find_lists_the_nearest_matching_planets_and_counts_those_in_other_galaxies():
    r = atlas.find_planets(PLANETS, ORIGIN, atlas.PlanetFilter(biome="Lush"), nearest=3)
    assert found(r) == [(1, 1, 0, False), (9, 1, 265, True), (3, 2, 400, False)]
    assert r.matched == 4 and r.other_galaxy == 2


def test_find_within_a_radius():
    r = atlas.find_planets(PLANETS, ORIGIN, atlas.PlanetFilter(biome="Lush"), within=400)
    assert [x[:2] for x in found(r)] == [(1, 1), (9, 1), (3, 2)] and r.matched == 3


@pytest.mark.parametrize(("flt", "planets"), [
    (atlas.PlanetFilter(infested=True), [(1, 2), (2, 4)]),
    (atlas.PlanetFilter(biome="Lush", infested=False), [(1, 1), (9, 1), (3, 2)]),
    (atlas.PlanetFilter(named=True), [(9, 1)]),
    (atlas.PlanetFilter(discoverer="mine"), [(1, 1), (3, 2)]),
    (atlas.PlanetFilter(discoverer="others"), [(1, 2), (9, 1), (2, 4)]),
])
def test_find_filters(flt, planets):
    assert [x[:2] for x in found(atlas.find_planets(PLANETS, ORIGIN, flt))] == planets


def test_planets_at_one_distance_are_ordered_by_address():
    s = make_save(ORIGIN, systems=[system(addr(0, 0, 0, system=s), planets=[planet(2), planet(1)])
                                   for s in (7, 3)])
    assert [x[:2] for x in found(atlas.find_planets(s, ORIGIN, atlas.PlanetFilter()))] == [
        (3, 1), (3, 2), (7, 1), (7, 2)]


# ---- route --------------------------------------------------------------------
def stop(name, x=0, z=0, system=1, planet=0, galaxy=0):
    return atlas.Place("system", addr(x, 0, z, system, planet, galaxy), name)


START = stop("start", 2, 4, system=1)
A, B, C = stop("A", 1, 0, system=2), stop("B", 4, 3, system=3), stop("C", 3, 2, system=4)


def visits(route):
    return [leg.end.name for leg in route.legs]


def test_a_route_runs_nearest_first_then_untangles_with_2opt_from_a_fixed_start():
    # nearest-first takes C (a tie with B, broken by address), then B, then A: 3,157 ly
    greedy = atlas.plan_route(START, atlas.nearest_first(START, [A, B, C]), keep_order=True)
    assert visits(greedy) == ["C", "B", "A"] and round(greedy.total_ly) == 3157
    r = atlas.plan_route(START, [A, B, C])
    assert visits(r) == ["B", "C", "A"] and round(r.total_ly) == 2591 and r.legs[0].start is START


def test_keep_order_visits_the_stops_exactly_as_listed():
    assert visits(atlas.plan_route(START, [A, B, C], keep_order=True)) == ["A", "B", "C"]


def test_a_round_trip_keeps_the_closing_stop():
    r = atlas.plan_route(START, [A, B, C], round_trip=True)
    assert visits(r)[-1] == "start" and len(r.legs) == 4
    assert visits(atlas.plan_route(START, [A, B, C], round_trip=True, keep_order=True)) == ["A", "B", "C", "start"]


def test_warp_jumps_are_counted_only_with_a_warp_range():
    r = atlas.plan_route(START, [A, B, C])
    assert r.jumps is None and all(leg.jumps is None for leg in r.legs)
    r = atlas.plan_route(START, [A, B, C], warp_range=500)
    assert [leg.jumps for leg in r.legs] == [2, 2, 3] and r.jumps == 7  # 894, 566, 1131 ly


def test_same_region_legs_are_estimates_of_one_jump_and_mark_the_total():
    near, far = stop("near", 2, 4, system=9), stop("far", 2, 5, system=9)
    r = atlas.plan_route(START, [near, far], warp_range=100)
    assert [(leg.distance.estimate, leg.jumps) for leg in r.legs] == [(True, 1), (False, 4)]
    assert r.estimate and round(r.total_ly) == 665
    assert not atlas.plan_route(START, [far]).estimate


def test_a_stop_listed_twice_is_visited_once_when_the_route_is_ordered():
    assert sorted(visits(atlas.plan_route(START, [A, B, A]))) == ["A", "B"]


def test_keep_order_visits_a_stop_listed_twice_each_time():
    assert visits(atlas.plan_route(START, [A, B, A], keep_order=True)) == ["A", "B", "A"]


def test_a_stop_in_another_galaxy_is_refused_with_the_reason():
    away = stop("Portal HQ", galaxy=56)
    with pytest.raises(atlas.RouteError, match="one Galaxy: it starts in Euclid, but Portal HQ is in Ilkerloor"):
        atlas.plan_route(START, [A, away])


def test_a_route_needs_a_stop():
    with pytest.raises(atlas.RouteError, match="at least one Stop"):
        atlas.plan_route(START, [])


def test_2opt_never_lengthens_the_nearest_first_route():
    import random
    rng = random.Random(14)
    for _ in range(300):
        stops = [stop(f"s{i}", rng.randint(-20, 20), rng.randint(-20, 20), system=rng.randint(1, 3))
                 for i in range(rng.randint(1, 9))]
        for round_trip in (False, True):
            greedy = atlas.plan_route(START, atlas.nearest_first(START, stops), keep_order=True,
                                      round_trip=round_trip)
            best = atlas.plan_route(START, stops, round_trip=round_trip)
            assert best.total_ly <= greedy.total_ly + 1e-6
            assert sorted(visits(best)) == sorted(visits(greedy))


# ---- Biome Tour -----------------------------------------------------------------
def test_a_biome_tour_routes_through_the_nearest_matching_planets():
    start = atlas.resolve(PLANETS, "here")
    r = atlas.biome_tour(PLANETS, start, atlas.PlanetFilter(biome="Lush"), 3, warp_range=1000)
    assert [(leg.end.address.system, leg.end.address.planet) for leg in r.legs] == [(1, 1), (9, 1), (3, 2)]
    assert [leg.jumps for leg in r.legs] == [0, 1, 1] and r.estimate
    assert r.legs[0].end.kind == "planet"


def test_a_biome_tour_with_no_matching_planet_in_the_galaxy_is_refused():
    with pytest.raises(atlas.RouteError, match="No discovered planet in Euclid matches"):
        atlas.biome_tour(PLANETS, atlas.resolve(PLANETS, "here"), atlas.PlanetFilter(biome="Lava"), 5)


# ---- the prototype's six walkthroughs, as oracles ----------------------------------
# Expected values come from running the prototype's own Atlas module (branch
# prototype/nms-atlas) over the same anonymised data. Walkthrough 5's waypoints
# (`knownWaypoints`) were dropped; only its direct Legs apply.
def walkthrough(name):
    import json
    from pathlib import Path
    raw = json.loads((Path(__file__).parent / "fixtures" / "atlas-walkthroughs.json").read_text(encoding="utf-8"))
    d = raw[name]
    systems = [system(Address(*s["addr"]), s["name"], [planet(p["index"], p["biome"], p["name"], p["infested"],
                                                               p["mine"]) for p in s["planets"]], s["mine"])
               for s in d["systems"]]
    return make_save(Address(*d["player"]), systems, [base(b["name"], Address(*b["addr"]), b["mine"])
                                                      for b in d["bases"]])


MAIN, EXPEDITION = walkthrough("save17.hg"), walkthrough("save14.hg")
LUSH = atlas.PlanetFilter(biome="Lush")


def where(place):
    a = place.address
    return (a.galaxy, a.x, a.y, a.z, a.system, a.planet)


def rows(result):
    return [(where(f.place), round(f.distance.ly), f.distance.estimate) for f in result.rows]


def test_walkthrough_1_nearest_planet():
    here = MAIN.player.location
    r = atlas.find_planets(MAIN, here, LUSH, nearest=5)
    assert rows(r) == [((0, -80, -2, -1791, 18, 1), 0, False), ((0, -80, -2, -1791, 18, 3), 0, False),
                       ((0, 1259, 15, -1074, 236, 4), 607592, False), ((0, 1485, -3, -962, 12, 5), 708403, False),
                       ((0, 1485, -3, -961, 6, 4), 708590, False)]
    assert (r.matched, r.other_galaxy) == (15, 1)
    mine = atlas.PlanetFilter(biome="Lush", discoverer="mine")
    r = atlas.find_planets(MAIN, here, mine, nearest=5)
    assert r.matched == 6 and rows(r)[-1] == ((0, -1785, 0, -39, 329, 2), 977878, False)
    urneti = atlas.resolve(MAIN, "Urneti Outpost").address
    assert rows(atlas.find_planets(MAIN, urneti, mine, nearest=5))[0] == ((0, -1785, 0, -39, 329, 2), 265, True)
    assert rows(atlas.find_planets(MAIN, urneti, mine, within=1000)) == [((0, -1785, 0, -39, 329, 2), 265, True)]


FOUR_BASES = ["Police HQ", "Lidfor Outpost", "Urneti Outpost", "Police Box - Void Egg"]


def test_walkthrough_2_base_hopping_trip():
    here = atlas.resolve(MAIN, "here")
    stops = [atlas.resolve(MAIN, n) for n in FOUR_BASES]
    given = atlas.plan_route(here, stops, keep_order=True, warp_range=2500)
    assert visits(given) == FOUR_BASES and (round(given.total_ly), given.jumps) == (4377979, 1752)
    best = atlas.plan_route(here, stops, warp_range=2500)
    assert visits(best) == ["Lidfor Outpost", "Police HQ", "Police Box - Void Egg", "Urneti Outpost"]
    assert (round(best.total_ly), best.jumps) == (2869484, 1149)
    assert [p.name for p in atlas.nearest_first(here, stops)] == visits(best)  # 2-opt finds nothing here
    trip = atlas.plan_route(here, stops, round_trip=True, warp_range=2500)
    assert trip.legs[-1].end is here and (round(trip.total_ly), trip.jumps) == (3847362, 1541)
    assert atlas.plan_route(here, stops, round_trip=True, warp_range=1000).jumps == 3850


def test_walkthrough_3_biome_tour():
    here = atlas.resolve(MAIN, "here")
    frozen = atlas.PlanetFilter(biome="Frozen")
    assert atlas.find_planets(MAIN, here.address, frozen, nearest=4).matched == 10
    tour = atlas.biome_tour(MAIN, here, frozen, 4, warp_range=2500)
    assert [leg.distance.estimate for leg in tour.legs] == [True, False, False, True]
    assert (round(tour.total_ly), tour.jumps) == (709448, 287) and tour.estimate
    tour = atlas.biome_tour(MAIN, here, frozen, 6, warp_range=2500)
    assert (round(tour.total_ly), tour.jumps) == (1408048, 567)
    assert [(round(leg.distance.ly), leg.jumps) for leg in tour.legs][4] == (0, 0)  # two planets, one system


def test_walkthrough_4_one_region_one_distance():
    here = atlas.resolve(EXPEDITION, "here")
    assert atlas.find_planets(EXPEDITION, here.address, atlas.PlanetFilter(), nearest=10).matched == 83
    names = ["Nellise", "OwO III: The Squeakule", "关注500G谢谢喵"]
    stops = [atlas.resolve(EXPEDITION, n) for n in names]
    r = atlas.plan_route(here, stops, warp_range=1500)
    assert visits(r) == ["OwO III: The Squeakule", "Nellise", "关注500G谢谢喵"]
    assert [leg.distance.estimate for leg in r.legs] == [False, True, True]
    assert (round(r.total_ly), r.jumps, r.estimate) == (1424, 3, True)
    given = atlas.plan_route(here, stops[::-1], keep_order=True, warp_range=1500)
    assert visits(given) == names[::-1] and round(given.total_ly) == 1424


def test_walkthrough_5_direct_legs_only():
    here = atlas.resolve(EXPEDITION, "here")
    edge = atlas.resolve(EXPEDITION, "0025F79B1D81")  # an unnamed system, by its glyphs
    assert edge.kind == "glyphs" and edge.system is not None
    assert [(round(atlas.plan_route(here, [edge], warp_range=w).total_ly), atlas.plan_route(
        here, [edge], warp_range=w).jumps) for w in (450, 600, 300)] == [(894, 2), (894, 2), (894, 3)]


def test_walkthrough_6_things_that_must_be_refused():
    here = atlas.resolve(MAIN, "here")
    with pytest.raises(atlas.RouteError, match="starts in Euclid, but Portal HQ is in Ilkerloor"):
        atlas.plan_route(here, [atlas.resolve(MAIN, "Portal HQ")])
    portal = atlas.resolve(MAIN, "Portal HQ").address
    r = atlas.find_planets(MAIN, portal, atlas.PlanetFilter(), nearest=5)
    assert (len(r.rows), r.matched, r.other_galaxy) == (2, 2, 84)
    with pytest.raises(atlas.Unresolved, match="'HQ' matches 6 places") as e:
        atlas.resolve(MAIN, "HQ")
    assert [p.name for p in e.value.candidates] == ["Police HQ", "Toxic HQ", "Dome HQ", "Redfern HQ", "Frozen HQ"]
    with pytest.raises(atlas.Unresolved, match="'Visited base 7' is a Visited Base"):
        atlas.resolve(EXPEDITION, "Visited base 7")
    visited = atlas.resolve(EXPEDITION, "Visited base 7", include_visited=True)
    r = atlas.plan_route(atlas.resolve(EXPEDITION, "here"), [visited], warp_range=2500)
    assert (round(r.total_ly), r.jumps) == (0, 0)
