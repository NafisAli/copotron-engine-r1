"""The Save Delta: what changed in one slot between two Save Updates (#29).

A pure function of two `model.Save`s; it reads nothing else. Inventory and the
player's own Bases report both directions; Discoveries report only what is new.

- Inventory is totalled by name group across every Container, as `inventory
  --search`/`--have` total it, so moving a stack between Containers is no change.
  Cargo counts by amount; Technology counts installed slots, because its amount
  is a charge that drains with use.
- A Base is matched by type, Address and position, else by type and name, so a
  renamed Base and a freighter or corvette that moved with the player stay one
  Base. It is edited when its name, its parts or its last-update time changed.
"""

from __future__ import annotations

import collections
from dataclasses import dataclass, field

from . import atlas
from .coords import Address
from .inventory import aggregate, by_name
from .model import Base, Save, Slot

CURRENCIES = ("units", "nanites", "quicksilver")


@dataclass(frozen=True, slots=True)
class ItemChange:
    name: str | None  # None for an id the Item Catalog doesn't name
    ids: list[str]
    change: int
    total: int  # held after the Save Update

    @property
    def label(self) -> str:
        return self.name or self.ids[0]


@dataclass(frozen=True, slots=True)
class CurrencyChange:
    currency: str  # units | nanites | quicksilver
    change: int
    total: int


@dataclass(frozen=True, slots=True)
class NewPlace:
    """A Star System or planet the Save holds a Discovery for that it didn't before."""

    label: str
    name: str | None
    address: Address
    is_mine: bool
    biome: str | None = None  # planets only


@dataclass(frozen=True, slots=True)
class BaseChange:
    name: str
    kind: str
    address: Address
    part_count: int  # after the Save Update; before it, for a removed Base
    parts_change: int
    renamed_from: str | None  # edited and renamed only; "" when it had no name


@dataclass(frozen=True, slots=True)
class Move:
    before: Address
    after: Address
    label: str  # where the player is now


@dataclass(slots=True)
class SaveDelta:
    inventory: list[ItemChange] = field(default_factory=list)
    currencies: list[CurrencyChange] = field(default_factory=list)
    systems: list[NewPlace] = field(default_factory=list)
    planets: list[NewPlace] = field(default_factory=list)
    bases_added: list[BaseChange] = field(default_factory=list)
    bases_edited: list[BaseChange] = field(default_factory=list)
    bases_removed: list[BaseChange] = field(default_factory=list)
    location: Move | None = None
    game_mode: tuple[str, str] | None = None  # (before, after)

    @property
    def empty(self) -> bool:
        return not (self.inventory or self.currencies or self.systems or self.planets or self.bases_added
                    or self.bases_edited or self.bases_removed or self.location or self.game_mode)

    def to_json(self) -> dict:
        def place(p: NewPlace) -> dict:
            return {"label": p.label, "name": p.name, "is_mine": p.is_mine, "address": p.address.to_json(),
                    **({"biome": p.biome} if p.address.planet else {})}

        def base(b: BaseChange) -> dict:
            return {"name": b.name, "kind": b.kind, "address": b.address.to_json(), "part_count": b.part_count,
                    "parts_change": b.parts_change, "renamed_from": b.renamed_from}

        return {
            "inventory": [{"name": c.name, "ids": c.ids, "change": c.change, "total": c.total}
                          for c in self.inventory],
            "currencies": [{"currency": c.currency, "change": c.change, "total": c.total} for c in self.currencies],
            "discoveries": {"systems": [place(p) for p in self.systems], "planets": [place(p) for p in self.planets]},
            "bases": {"added": [base(b) for b in self.bases_added], "edited": [base(b) for b in self.bases_edited],
                      "removed": [base(b) for b in self.bases_removed]},
            "location": None if not self.location else {
                "label": self.location.label, "from": self.location.before.to_json(),
                "to": self.location.after.to_json()},
            "game_mode": None if not self.game_mode else {"from": self.game_mode[0], "to": self.game_mode[1]},
        }


def save_delta(before: Save, after: Save) -> SaveDelta:
    added, edited, removed = _bases(before.my_bases, after.my_bases)
    systems, planets = _discoveries(before, after)
    return SaveDelta(
        inventory=_inventory(before, after),
        currencies=[CurrencyChange(c, getattr(after.player, c) - getattr(before.player, c), getattr(after.player, c))
                    for c in CURRENCIES if getattr(after.player, c) != getattr(before.player, c)],
        systems=systems, planets=planets,
        bases_added=added, bases_edited=edited, bases_removed=removed,
        location=_move(before, after),
        game_mode=(before.player.game_mode, after.player.game_mode)
        if after.player.game_mode != before.player.game_mode else None,
    )


# ---- inventory -------------------------------------------------------------------
def _held(sl: Slot) -> int:
    return 1 if sl.is_tech else sl.amount


def _holdings(s: Save) -> dict[str, dict]:
    """Name group -> its row, every Container and stack counted."""
    return {r["name"] or r["ids"][0]: r for r in by_name(aggregate(s.containers, lambda _: True, _held))}


def _inventory(before: Save, after: Save) -> list[ItemChange]:
    old, new = _holdings(before), _holdings(after)
    out = []
    for key in sorted(old.keys() | new.keys(), key=str.lower):
        was, now = old.get(key), new.get(key)
        change = (now["total"] if now else 0) - (was["total"] if was else 0)
        if change:
            ids = sorted({*(was["ids"] if was else []), *(now["ids"] if now else [])})
            out.append(ItemChange((now or was)["name"], ids, change, now["total"] if now else 0))
    return out


# ---- Discoveries, location ---------------------------------------------------------
def _discoveries(before: Save, after: Save) -> tuple[list[NewPlace], list[NewPlace]]:
    systems, planets = [], []
    for key, s in after.systems.items():
        known = before.systems.get(key)
        if known is None:
            systems.append(NewPlace(atlas.label(atlas.Place("system", s.address, s.name, s)), s.name, s.address,
                                    s.is_mine))
        seen = {p.index for p in known.planets} if known else set()
        for p in s.planets:
            if p.index not in seen:
                place = atlas.planet_place(s, p)
                planets.append(NewPlace(atlas.label(place), p.name, place.address, p.is_mine, p.biome))
    return systems, planets


def _move(before: Save, after: Save) -> Move | None:
    a, b = before.player.location, after.player.location
    if (a.system_key, a.planet) == (b.system_key, b.planet):
        return None
    s = after.system_at(b)
    p = next((p for p in s.planets if p.index == b.planet), None) if s else None
    if p:
        place = atlas.planet_place(s, p)
    elif b.planet:
        place = atlas.Place("planet", b, None, s)
    else:
        place = atlas.Place("system", b, s.name if s else None, s)
    return Move(a, b, atlas.label(place))


# ---- Bases ------------------------------------------------------------------------------
def _change(b: Base, parts_change: int, renamed_from: str | None = None) -> BaseChange:
    return BaseChange(b.name, b.kind, b.address, b.part_count, parts_change, renamed_from)


def _bases(before: list[Base], after: list[Base]) -> tuple[list[BaseChange], list[BaseChange], list[BaseChange]]:
    left, rest, pairs = list(before), list(after), []
    for key in (lambda b: (b.kind, b.address, b.position), lambda b: (b.kind, b.name)):
        unmatched = []
        for b in rest:
            o = next((o for o in left if key(o) == key(b)), None)
            if o is None:
                unmatched.append(b)
            else:
                left.remove(o)
                pairs.append((o, b))
        rest = unmatched
    added = [_change(b, b.part_count) for b in rest]
    removed = [_change(o, -o.part_count) for o in left]
    edited = [_change(n, n.part_count - o.part_count, o.name if o.name != n.name else None)
              for o, n in pairs
              if o.name != n.name or o.last_update != n.last_update
              or collections.Counter(o.parts) != collections.Counter(n.parts)]
    return added, edited, removed
