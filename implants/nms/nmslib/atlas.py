"""The Discovery Atlas: places, distances and Routes over one loaded Save (#14).

Nothing is built or persisted: no spatial index, edge graph, A*, waypoints,
reachability or cache. Every call scans the Save, which holds at most a few hundred
places. The atlas reads only the model (`Save.systems`, `Save.bases`,
`Save.player.location`), never raw save keys.

The save stores only the Region a Star System sits in, not where inside it. A
distance between two Star Systems in one Region is therefore an estimate: the
Robbins constant x 400 (about 265 ly), which counts as exactly one Warp Jump.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import pairwise

from .coords import Address, parse_glyphs
from .model import Base, Planet, Save, System


@dataclass(frozen=True, slots=True)
class Distance:
    ly: float
    estimate: bool  # a same-Region gap: the save has no position inside a Region


def distance(a: Address, b: Address) -> Distance | None:
    """Light-years from `a` to `b`; None across Galaxies."""
    ly = a.distance_ly(b)
    if ly is None:
        return None
    return Distance(ly, estimate=a.same_region(b) and not a.same_system(b))


def warp_jumps(d: Distance, warp_range: float) -> int:
    """⌈ly ÷ Warp Range⌉ for one Leg: none inside a Star System, one inside a Region."""
    if d.ly == 0:
        return 0
    if d.estimate:
        return 1
    return math.ceil(d.ly / warp_range)


# ---- places ------------------------------------------------------------------
@dataclass(slots=True)
class Place:
    """Somewhere a name, Portal Glyphs or `here` points to: a Stop or a starting point."""

    kind: str  # here | glyphs | base | visited_base | system | planet
    address: Address
    name: str | None = None  # the name it was found by; None for here and glyphs
    system: System | None = None  # the discovered Star System at the address, if any
    planet: Planet | None = None
    base: Base | None = None


def label(p: Place) -> str:
    """How a place reads in text: its name, else what it is and where."""
    if p.name:
        return p.name
    if p.kind == "here":
        return "here"
    if p.kind == "glyphs":
        return f"Glyphs {p.address.glyphs}" + (f" ({p.system.name})" if p.system and p.system.name else "")
    s = p.system
    sys_label = s.name if s and s.name else f"system {(s.address if s else p.address).glyphs}"
    return f"{sys_label} planet {p.address.planet}" if p.kind == "planet" else sys_label


def planet_place(s: System, p: Planet) -> Place:
    a = s.address
    return Place("planet", Address(a.galaxy, a.x, a.y, a.z, a.system, p.index), p.name, s, p)


def address_key(a: Address) -> tuple[int, ...]:
    """Ties are broken by address: deterministic, though arbitrary inside one Region."""
    return (a.galaxy, a.x, a.y, a.z, a.system, a.planet)


class Unresolved(Exception):
    """A name the rule refuses rather than guess: unknown, ambiguous, or a Visited Base without --all."""

    def __init__(self, message: str, candidates: list[Place] | None = None) -> None:
        super().__init__(message)
        self.candidates = candidates or []


MAX_CANDIDATES = 5


def named_places(save: Save) -> list[list[Place]]:
    """The named places in the order the name rule checks them; unnamed places have no name to match."""
    own, visited = [], []
    for b in save.bases:
        if b.name:
            (own if b.is_mine else visited).append(
                Place("base" if b.is_mine else "visited_base", b.address, b.name, save.system_at(b.address), base=b))
    systems, planets = [], []
    for s in save.systems.values():
        if s.name:
            systems.append(Place("system", s.address, s.name, s))
        planets += [planet_place(s, p) for p in s.planets if p.name]
    return [own, systems, planets, visited]


def resolve(save: Save, text: str, *, include_visited: bool = False) -> Place:
    """One place for `text`, by the name rule; raises `Unresolved` rather than guess.

    Checked in order: `here`, 12 Portal Glyphs (read in the current Galaxy), the
    player's Bases, discovered Star Systems, named planets, then Visited Bases. Each
    name is tried exact, then as a unique prefix, then as a unique substring (any case).
    """
    q = text.strip()
    here = save.player.location
    if not q or q.casefold() == "here":
        return Place("here", here, system=save.system_at(here))
    try:
        glyphs = parse_glyphs(q)
    except ValueError:
        glyphs = None
    if glyphs:
        a = Address.from_glyphs(glyphs, here.galaxy)
        return Place("glyphs", a, system=save.system_at(a))
    lc = q.casefold()
    tiers = named_places(save)
    for match in (str.__eq__, str.startswith, str.__contains__):
        for tier in tiers:
            hits = [p for p in tier if match(p.name.casefold(), lc)]
            if len(hits) > 1:
                raise Unresolved(f"{q!r} matches {len(hits)} places", hits[:MAX_CANDIDATES])
            if hits:
                if hits[0].kind == "visited_base" and not include_visited:
                    raise Unresolved(f"{hits[0].name!r} is a Visited Base (another player's); "
                                     "pass --all to use it")
                return hits[0]
    raise Unresolved(f"Nothing in this save is called {q!r}")


# ---- find --------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class PlanetFilter:
    biome: str | None = None
    infested: bool | None = None  # None: either
    named: bool = False  # only planets with an uploaded name
    discoverer: str | None = None  # None | "mine" | "others"

    def matches(self, p: Planet) -> bool:
        return ((self.biome is None or p.biome == self.biome)
                and (self.infested is None or p.infested == self.infested)
                and (not self.named or bool(p.name))
                and (self.discoverer is None or p.is_mine == (self.discoverer == "mine")))


@dataclass(slots=True)
class Found:
    place: Place
    distance: Distance


@dataclass(slots=True)
class FindResult:
    rows: list[Found]  # nearest first, cut to `nearest` or `within`
    matched: int  # matching planets in the origin's Galaxy, before `nearest` cuts them
    other_galaxy: int  # matching planets left out because they are in another Galaxy


def find_planets(save: Save, origin: Address, flt: PlanetFilter, *, nearest: int | None = None,
                 within: float | None = None) -> FindResult:
    """Discovered planets matching `flt`, nearest to `origin` first, in `origin`'s Galaxy only."""
    rows, other_galaxy = [], 0
    for s in save.systems.values():
        for p in s.planets:
            if not flt.matches(p):
                continue
            place = planet_place(s, p)
            d = distance(origin, place.address)
            if d is None:
                other_galaxy += 1
            elif within is None or d.ly <= within:
                rows.append(Found(place, d))
    rows.sort(key=lambda f: (f.distance.ly, address_key(f.place.address)))
    return FindResult(rows if nearest is None else rows[:nearest], len(rows), other_galaxy)


# ---- route -------------------------------------------------------------------
class RouteError(Exception):
    """A Route that can't be planned: no Stops, or a Stop in another Galaxy."""


@dataclass(slots=True)
class Leg:
    start: Place
    end: Place
    distance: Distance
    jumps: int | None  # None without a Warp Range


@dataclass(slots=True)
class Route:
    start: Place
    legs: list[Leg]
    round_trip: bool
    warp_range: float | None

    @property
    def total_ly(self) -> float:
        return sum(leg.distance.ly for leg in self.legs)

    @property
    def estimate(self) -> bool:
        """The total includes a same-Region estimate."""
        return any(leg.distance.estimate for leg in self.legs)

    @property
    def jumps(self) -> int | None:
        return None if self.warp_range is None else sum(leg.jumps for leg in self.legs)


def _ly(a: Place, b: Place) -> float:
    return distance(a.address, b.address).ly


def nearest_first(start: Place, stops: list[Place]) -> list[Place]:
    """Greedy order: always the nearest Stop left; a tie goes to the lower address."""
    left, order, here = list(stops), [], start
    while left:
        here = min(left, key=lambda p: (_ly(here, p), address_key(p.address)))
        left.remove(here)
        order.append(here)
    return order


def two_opt(order: list[Place]) -> list[Place]:
    """Reverse any stretch that shortens the Route; the first point (and a closing one) stays put."""
    order = list(order)
    n = len(order)
    closed = n > 1 and order[0] is order[-1]
    end = n - 1 if closed else n
    improved = True
    while improved:
        improved = False
        for i in range(end - 2):
            for j in range(i + 2, end):
                after_j = order[j + 1] if j + 1 < n else None
                before = _ly(order[i], order[i + 1]) + (_ly(order[j], after_j) if after_j else 0)
                after = _ly(order[i], order[j]) + (_ly(order[i + 1], after_j) if after_j else 0)
                if before - after > 1e-6:
                    order[i + 1:j + 1] = reversed(order[i + 1:j + 1])
                    improved = True
    return order


def plan_route(start: Place, stops: list[Place], *, keep_order: bool = False, round_trip: bool = False,
               warp_range: float | None = None) -> Route:
    """Straight Legs from `start` through every Stop, all in one Galaxy.

    By default the Stops are ordered nearest-first, then untangled with 2-opt;
    `keep_order` visits them exactly as listed, a repeated Stop included; otherwise a
    Stop listed twice is visited once. `round_trip` returns to `start`.
    """
    seen, unique = set(), []
    for s in stops:
        key = (s.kind, s.name, s.address)
        if keep_order or key not in seen:
            seen.add(key)
            unique.append(s)
    if not unique:
        raise RouteError("A Route needs at least one Stop")
    away = [s for s in unique if s.address.galaxy != start.address.galaxy]
    if away:
        raise RouteError(f"A Route stays in one Galaxy: it starts in {start.address.galaxy_name}, but "
                         + "; ".join(f"{label(s)} is in {s.address.galaxy_name}" for s in away))
    if warp_range is not None and warp_range <= 0:
        raise RouteError("The Warp Range must be a positive number of light-years")
    order = [start, *(unique if keep_order else nearest_first(start, unique))]
    if round_trip:
        order.append(start)
    if not keep_order:
        order = two_opt(order)
    legs = []
    for a, b in pairwise(order):
        d = distance(a.address, b.address)
        legs.append(Leg(a, b, d, None if warp_range is None else warp_jumps(d, warp_range)))
    return Route(start, legs, round_trip, warp_range)


def biome_tour(save: Save, start: Place, flt: PlanetFilter, n: int, **route_opts) -> Route:
    """A Route whose Stops are the `n` discovered planets nearest `start` that match `flt`."""
    found = find_planets(save, start.address, flt, nearest=n)
    if not found.rows:
        raise RouteError(f"No discovered planet in {start.address.galaxy_name} matches those filters")
    return plan_route(start, [f.place for f in found.rows], **route_opts)
