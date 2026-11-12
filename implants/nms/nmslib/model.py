"""The save model every command reads. `extract.load()` builds one `Save`.

This module is the contract between the save engine and its consumers. The
Discovery Atlas (find/route/system) consumes `Save.systems`, `Save.bases` and
`Save.player.location`; it must not reach into the raw save JSON.

Identity rules
--------------
- A star system is identified by `Address.system_key`
  (galaxy, voxel x, y, z, system index). Planet index is not part of it.
- A planet is identified by (system_key, planet index).
- A discovery is "mine" when its owner UID is the player's UID.
- A base is "mine" when its type is the player's own (home planet, freighter,
  corvette) or it has no type (legacy saves); its owner UID is not reliable.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .coords import Address
from .locate import SaveFile, iso

BIOMES = [
    "Lush", "Toxic", "Scorched", "Radioactive", "Frozen", "Barren", "Dead", "Weird",
    "Red", "Green", "Blue", None, "Swamp", "Lava", "Waterworld", "GasGiant",
]  # index 11 is the game's unused "Test" biome


# ---- player ------------------------------------------------------------------
@dataclass(slots=True)
class Ship:
    index: int  # position in ShipOwnership
    name: str  # player-given name, "" if unnamed
    kind: str  # Fighter, Hauler, Explorer, Shuttle, Exotic, Solar, Living, Sentinel, Corvette, ...
    inventory_class: str  # S/A/B/C
    is_current: bool

    @property
    def label(self) -> str:
        return self.name or f"{self.kind} #{self.index}"


@dataclass(slots=True)
class Player:
    uid: str | None
    location: Address
    previous_location: Address | None
    units: int
    nanites: int
    quicksilver: int
    game_mode: str  # difficulty preset (Normal, Survival, Permadeath, Creative, Relaxed, Custom, ...)
    context: str  # "main" | "expedition"
    save_name: str
    save_summary: str  # the game's own one-liner, e.g. "Aboard Mitosh Station Sigma"
    play_time_s: int
    current_ship: Ship | None
    ships: list[Ship]
    freighter_name: str


# ---- inventory ---------------------------------------------------------------
@dataclass(slots=True)
class Slot:
    id: str  # game id without the leading "^", e.g. "FUEL1", "UP_SHLD4#35337"
    name: str | None  # catalog name; None when the id is not in the catalog
    amount: int
    max_amount: int
    item_type: str  # Substance | Product | Technology
    damage_factor: float
    fully_installed: bool
    x: int
    y: int
    role: str | None = None  # refiner slots only: "output" | "input"

    @property
    def is_tech(self) -> bool:
        return self.item_type == "Technology"

    @property
    def at_cap(self) -> bool:
        return not self.is_tech and self.max_amount > 1 and self.amount >= self.max_amount

    def near_cap(self, ratio: float = 0.9) -> bool:
        return not self.is_tech and self.max_amount > 1 and self.amount >= self.max_amount * ratio

    @property
    def display(self) -> str:
        return self.name or self.id


@dataclass(slots=True)
class Container:
    """One slot grid. Owners with separate grids (suit, ship) yield several."""

    # suit | refiner | ship | multitool | freighter | storage | exocraft | ingredients | corvette |
    # rocket-locker | fishing-platform | bait-box | food-unit | grave | chest-magic
    category: str
    owner: str  # "Exosuit", ship label, "Storage 3", "Nautilon", ...
    grid: str  # general | cargo | tech
    capacity: int  # unlocked slots (len ValidSlotIndices), not width x height
    slots: list[Slot]
    is_current: bool = True  # current ship / multitool; always True for single-owner categories
    name: str | None = None  # a container named apart from its owner: "Personal Refiner" (owner Exosuit)
    fuel_pct: int | None = None  # refiner only; fuel is a container value, never an item

    @property
    def label(self) -> str:
        if self.name:
            return self.name
        return self.owner if self.grid == "general" else f"{self.owner} ({self.grid})"


# ---- places ------------------------------------------------------------------
@dataclass(slots=True)
class Base:
    name: str
    kind: str  # HomePlanetBase | FreighterBase | ExternalPlanetBase | PlayerShipBase (corvette) | ...
    address: Address
    position: tuple[float, float, float]
    owner_uid: str
    owner_name: str
    is_mine: bool
    last_update: int  # unix seconds
    object_count: int

    def to_json(self) -> dict:
        return {
            "name": self.name,
            "kind": self.kind,
            "address": self.address.to_json(),
            "owner_uid": self.owner_uid,
            "owner_name": self.owner_name,
            "is_mine": self.is_mine,
            "last_update": iso(self.last_update),
            "object_count": self.object_count,
        }


@dataclass(slots=True)
class Discovery:
    """One raw discovery record, decoded. Kept for consumers that need the long tail."""

    kind: str  # SolarSystem | Planet | Sector | Animal | Flora | Mineral | ...
    address: Address
    custom_name: str | None
    discoverer: str | None  # username; None when the record has none
    discoverer_uid: str | None
    timestamp: int | None
    uploaded: bool
    is_mine: bool


@dataclass(slots=True)
class Planet:
    index: int
    biome: str | None
    infested: bool
    name: str | None  # custom (uploaded) name; None when never named
    discoverer: str | None
    is_mine: bool
    seed: int | None


@dataclass(slots=True)
class System:
    address: Address  # planet index 0
    name: str | None
    discoverer: str | None
    discovered_at: int | None
    is_mine: bool
    planets: list[Planet] = field(default_factory=list)


@dataclass(slots=True)
class Save:
    file: SaveFile
    version: int
    platform: str
    player: Player
    containers: list[Container]
    bases: list[Base]  # every base the save holds, mine and visited
    systems: dict[tuple, System]  # keyed by Address.system_key
    discoveries: list[Discovery]
    warnings: list[str] = field(default_factory=list)  # tolerated decode problems

    @property
    def base_version(self) -> int:
        """The game's save format version (`Version % 512`), compared with the Game Data Snapshot's."""
        return self.version % 512

    @property
    def my_bases(self) -> list[Base]:
        return [b for b in self.bases if b.is_mine]

    def system_at(self, address: Address) -> System | None:
        return self.systems.get(address.system_key)
