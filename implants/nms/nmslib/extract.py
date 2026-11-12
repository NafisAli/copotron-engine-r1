"""Raw deobfuscated save JSON -> `model.Save`.

Handles three save layouts seen in the wild:
- pre-context saves (PlayerStateData at the root, no ActiveContext),
- BaseContext saves (ActiveContext "Main"),
- ExpeditionContext saves (ActiveContext "Expedition" or "Season").
"""

from __future__ import annotations

import collections
from collections.abc import Mapping
from pathlib import Path

from . import catalog
from .coords import Address
from .decode import read_save
from .locate import SaveFile
from .model import (
    BIOMES, Base, Container, Discovery, Planet, Player, Save, Ship, Slot, System,
)

GAME_MODES = {1: "Normal", 2: "Creative", 3: "Survival", 4: "Ambient", 5: "Permadeath", 6: "Seasonal"}

SHIP_KINDS = {
    "FIGHTER_PROC": "Fighter", "DROPSHIP_PROC": "Hauler", "SCIENTIFIC_PROC": "Explorer",
    "SHUTTLE_PROC": "Shuttle", "S-CLASS_PROC": "Exotic", "BIOSHIP_PROC": "Living Ship",
    "SAILSHIP_PROC": "Solar", "SENTINELSHIP_PROC": "Interceptor",
}

# VehicleOwnership index -> exocraft (game vehicle enum: Buggy, Bike, Truck,
# WheeledBike, Hovercraft, Submarine, Mech). Index 1 is an unused slot.
EXOCRAFT = ["Roamer", "Bike", "Colossus", "Pilgrim", "Nomad", "Nautilon", "Minotaur"]

# Single-grid containers outside Chest1-10: (save field, category, label).
# Each is its own category and is shown only when it holds items. ChestMagic's
# purpose is unknown, so it keeps the raw field name rather than a guessed one.
SINGLE_GRIDS = [
    ("CookingIngredientsInventory", "ingredients", "Ingredient Storage"),
    ("CorvetteStorageInventory", "corvette", "Corvette Storage"),
    ("RocketLockerInventory", "rocket-locker", "Rocket Locker"),
    ("FishPlatformInventory", "fishing-platform", "Fishing Platform"),
    ("FishBaitBoxInventory", "bait-box", "Bait Box"),
    ("FoodUnitInventory", "food-unit", "Food Unit"),
    ("GraveInventory", "grave", "Grave (dropped on death)"),
    ("ChestMagicInventory", "chest-magic", "ChestMagic"),
    ("ChestMagic2Inventory", "chest-magic", "ChestMagic2"),
]


def load(file: SaveFile) -> Save:
    return build(read_save(file.path), file)  # doc is a dict, or a lazy decode.Node view


def build(doc: Mapping, file: SaveFile) -> Save:
    warnings: list[str] = []
    ctx_name = doc.get("ActiveContext")
    if ctx_name is None and "PlayerStateData" in doc:
        ctx, context = doc, "main"  # pre-context layout
    elif ctx_name in ("Expedition", "Season"):
        ctx, context = doc.get("ExpeditionContext") or {}, "expedition"
    else:
        ctx, context = doc.get("BaseContext") or {}, "main"
    ps = ctx.get("PlayerStateData") or {}
    common = doc.get("CommonStateData") or {}

    records = (((doc.get("DiscoveryManagerData") or {}).get("DiscoveryData-v1") or {})
               .get("Store") or {}).get("Record") or []
    uid = file.account_uid or _majority_lid(records)

    ships = _ships(ps)
    current_ship = next((s for s in ships if s.is_current), None)
    player = Player(
        uid=uid,
        location=Address.from_universe_address(ps.get("UniverseAddress") or {}),
        previous_location=_previous(ps.get("PreviousUniverseAddress")),
        units=_u32(ps.get("Units")),
        nanites=_u32(ps.get("Nanites")),
        quicksilver=_u32(ps.get("Specials")),
        game_mode=_game_mode(ctx, ps),
        context=context,
        save_name=common.get("SaveName") or "",
        save_summary=ps.get("SaveSummary") or "",
        play_time_s=int(common.get("TotalPlayTime") or ps.get("TotalPlayTime") or 0),
        current_ship=current_ship,
        ships=ships,
        freighter_name=ps.get("PlayerFreighterName") or "",
    )
    pairs = _discoveries(records, uid, warnings)
    return Save(
        file=file,
        version=int(doc.get("Version") or 0),
        platform=doc.get("Platform") or "",
        player=player,
        containers=_containers(ps, ships),
        bases=_bases(ps.get("PersistentPlayerBases") or [], warnings),
        systems=_systems(pairs),
        discoveries=[d for d, _ in pairs],
        warnings=warnings,
    )


def load_path(path: str | Path) -> Save:
    from .locate import save_file
    return load(save_file(Path(path)))


# ---- player ------------------------------------------------------------------
def _u32(v) -> int:
    """Currencies are stored as signed ints; the game treats them as unsigned 32-bit."""
    return int(v or 0) & 0xFFFFFFFF


def _previous(ua) -> Address | None:
    if not ua:
        return None
    a = Address.from_universe_address(ua)
    return None if (a.voxel, a.system, a.planet, a.galaxy) == ((0, 0, 0), 0, 0, 0) else a


def _game_mode(ctx: dict, ps: dict) -> str:
    preset = ((ps.get("DifficultyState") or {}).get("Preset") or {}).get("DifficultyPresetType")
    if preset:
        return preset
    gm = ctx.get("GameMode")
    return GAME_MODES.get(gm, f"GameMode {gm}") if gm is not None else "Unknown"


def _ships(ps: dict) -> list[Ship]:
    primary = ps.get("PrimaryShip", 0)
    out = []
    for i, s in enumerate(ps.get("ShipOwnership") or []):
        filename = (s.get("Resource") or {}).get("Filename") or ""
        if not filename:
            continue  # empty ownership slot
        stem = filename.rsplit("/", 1)[-1].split(".", 1)[0]
        inv = s.get("Inventory") or {}
        out.append(Ship(
            index=i,
            name=(s.get("Name") or "").strip(),
            kind=SHIP_KINDS.get(stem, stem),
            inventory_class=((inv.get("Class") or {}).get("InventoryClass")) or "?",
            is_current=(i == primary),
        ))
    return out


def _majority_lid(records: list) -> str | None:
    lids = collections.Counter((r.get("OWS") or {}).get("LID") for r in records)
    lids.pop("", None)
    lids.pop(None, None)
    return lids.most_common(1)[0][0] if lids else None


# ---- inventory ---------------------------------------------------------------
def _slots(inv: dict) -> list[Slot]:
    out = []
    for s in inv.get("Slots") or []:
        raw_id = s.get("Id") or ""
        item_id = raw_id.lstrip("^")
        if not item_id or item_id.startswith("MAINT_"):
            continue  # MAINT_* are repair/maintenance task markers, not items
        idx = s.get("Index") or {}
        out.append(Slot(
            id=item_id,
            name=catalog.name_for(item_id),
            amount=int(s.get("Amount") or 0),
            max_amount=int(s.get("MaxAmount") or 0),
            item_type=((s.get("Type") or {}).get("InventoryType")) or "Product",
            damage_factor=float(s.get("DamageFactor") or 0.0),
            fully_installed=bool(s.get("FullyInstalled", True)),
            x=int(idx.get("X") or 0),
            y=int(idx.get("Y") or 0),
        ))
    return out


def _grid(category, owner, grid, inv, is_current=True) -> Container | None:
    if not isinstance(inv, Mapping):
        return None
    return Container(
        category=category, owner=owner, grid=grid,
        # Unlocked slots; grids without a ValidSlotIndices list are fully usable.
        capacity=len(inv.get("ValidSlotIndices") or [])
        or int(inv.get("Width") or 0) * int(inv.get("Height") or 0) * bool(inv.get("Slots")),
        slots=_slots(inv), is_current=is_current,
    )


def _owner_grids(category, owner, holder: dict, keys: tuple, is_current=True) -> list[Container]:
    """keys = (general, cargo, tech) field names; empty legacy cargo/tech grids are dropped."""
    out = []
    for grid, key in zip(("general", "cargo", "tech"), keys):
        c = _grid(category, owner, grid, holder.get(key), is_current)
        if c and (grid == "general" or c.capacity or c.slots):
            out.append(c)
    return out


def _containers(ps: dict, ships: list[Ship]) -> list[Container]:
    out: list[Container] = []
    out += _owner_grids("suit", "Exosuit", ps, ("Inventory", "Inventory_Cargo", "Inventory_TechOnly"))
    refiner = _personal_refiner(ps)
    if refiner:
        out.append(refiner)

    owned = ps.get("ShipOwnership") or []
    for ship in ships:
        out += _owner_grids("ship", ship.label, owned[ship.index],
                            ("Inventory", "Inventory_Cargo", "Inventory_TechOnly"), ship.is_current)
    if not ships:  # very old saves: only the top-level current ship grids
        out += _owner_grids("ship", "Starship", ps, ("ShipInventory", "", "ShipInventory_TechOnly"))

    tools = ps.get("Multitools") or []
    active = ps.get("ActiveMultioolIndex", 0)  # sic: the game's own key spelling
    found_tool = False
    for i, mt in enumerate(tools):
        filename = (mt.get("Resource") or {}).get("Filename") or ""
        if not filename:
            continue
        found_tool = True
        kind = "Sentinel Multi-tool" if "SENTINEL" in filename else "Multi-tool"
        label = (mt.get("Name") or "").strip() or f"{kind} #{i}"
        c = _grid("multitool", label, "general", mt.get("Store"), i == active)
        if c:
            out.append(c)
    if not found_tool:
        c = _grid("multitool", "Multi-tool", "general", ps.get("WeaponInventory"))
        if c:
            out.append(c)

    freighter_owned = bool((ps.get("CurrentFreighter") or {}).get("Filename"))
    fr = _owner_grids("freighter", ps.get("PlayerFreighterName") or "Freighter", ps,
                      ("FreighterInventory", "FreighterInventory_Cargo", "FreighterInventory_TechOnly"))
    if freighter_owned or any(c.slots for c in fr):
        out += fr

    for n in range(1, 11):
        c = _grid("storage", f"Storage {n - 1}", "general", ps.get(f"Chest{n}Inventory"))
        if c and c.slots:
            out.append(c)
    for key, category, label in SINGLE_GRIDS:
        c = _grid(category, label, "general", ps.get(key))
        if c and c.slots:
            out.append(c)

    for i, v in enumerate(ps.get("VehicleOwnership") or []):
        label = (v.get("Name") or "").strip() or (EXOCRAFT[i] if i < len(EXOCRAFT) else f"Exocraft #{i}")
        grids = _owner_grids("exocraft", label, v, ("Inventory", "Inventory_Cargo", "Inventory_TechOnly"))
        if any(c.slots for c in grids if c.grid != "tech"):  # every exocraft ships default tech
            out += grids
    return out


def _is_sentinel(key) -> bool:
    """The exosuit refiner's key: galactic address 0 at position (1,1,1,1)."""
    pos = key.get("Position") or []
    return _vp_int(key.get("GalacticAddress")) == 0 and len(pos) == 4 and all(float(p) == 1.0 for p in pos)


def _personal_refiner(ps: dict) -> Container | None:
    """The exosuit's Personal Refiner, shown even when empty; None when not installed.

    `PersonalMaintenanceInteractions[i]` pairs by index with `StoredInteractions[9]`
    key i. Only the exosuit refiner's key is reliable (#21): base, freighter,
    exocraft and corvette refiners can't be told from harvesters, so they are not read.
    """
    personal = ps.get("PersonalMaintenanceInteractions") or []
    stored = ps.get("StoredInteractions") or []
    keys = ((stored[9] or {}).get("Interactions") or []) if len(stored) > 9 else []
    i = next((i for i, k in enumerate(keys[:len(personal)]) if _is_sentinel(k)), None)
    if i is None:
        return None
    inv = personal[i].get("InventoryContainer") or {}
    width = int(inv.get("Width") or 0)

    def index(sl: Slot) -> int:  # slot 0 is fuel (a MAINT_ marker, not an item), 1 the output, 2+ inputs
        return sl.y * width + sl.x

    slots = sorted(_slots(inv), key=index)
    for sl in slots:
        sl.role = "output" if index(sl) == 1 else "input"
    fuel = next((s for s in inv.get("Slots") or [] if (s.get("Id") or "").lstrip("^").startswith("MAINT_FUEL")),
                None)  # Amount is a percentage (MaxAmount 100)
    c = _grid("refiner", "Exosuit", "general", inv)
    c.slots, c.name = slots, "Personal Refiner"
    c.fuel_pct = int(fuel.get("Amount") or 0) if fuel else None
    return c


# ---- bases and discoveries ---------------------------------------------------
# The player's own Base types (corvette = PlayerShipBase). ExternalPlanetBase holds
# other players' bases and expedition templates. Owner UID can't tell: legacy bases
# have an empty owner and the expedition freighter a placeholder one (#27).
MY_BASE_TYPES = {"HomePlanetBase", "FreighterBase", "PlayerShipBase"}


def _base_type(b) -> str | None:
    return (b.get("BaseType") or {}).get("PersistentBaseTypes") or None


def _is_my_base(b) -> bool:
    """A Base is the player's when its type is one of MY_BASE_TYPES, or it has none (legacy saves)."""
    kind = _base_type(b)
    return kind is None or kind in MY_BASE_TYPES


def _bases(raw: list, warnings: list[str]) -> list[Base]:
    out = []
    for i, b in enumerate(raw):
        try:
            address = Address.from_packed56(b.get("GalacticAddress"))
        except ValueError as e:
            warnings.append(f"base {i} ({b.get('Name')!r}): {e}")
            continue
        owner = b.get("Owner") or {}
        pos = b.get("Position") or [0.0, 0.0, 0.0]
        out.append(Base(
            name=(b.get("Name") or "").strip(),
            kind=_base_type(b) or "Unknown",
            address=address,
            position=(float(pos[0]), float(pos[1]), float(pos[2])),
            owner_uid=owner.get("UID") or "",
            owner_name=owner.get("USN") or "",
            is_mine=_is_my_base(b),
            last_update=int(b.get("LastUpdateTimestamp") or 0),
            object_count=len(b.get("Objects") or []),
        ))
    return out


def _discoveries(records: list, uid: str | None, warnings: list[str]) -> list[tuple[Discovery, list]]:
    """Each decoded record with its raw VP payload (seed, biome flags, ...)."""
    out = []
    for i, r in enumerate(records):
        dd = r.get("DD") or {}
        try:
            address = Address.from_packed56(dd.get("UA"))
        except ValueError as e:
            warnings.append(f"discovery {i}: {e}")
            continue
        ows = r.get("OWS") or {}
        out.append((Discovery(
            kind=dd.get("DT") or "Unknown",
            address=address,
            custom_name=((r.get("DM") or {}).get("CN") or None),
            discoverer=ows.get("USN") or None,
            discoverer_uid=ows.get("UID") or None,
            timestamp=int(ows.get("TS") or 0) or None,
            uploaded=bool((r.get("FL") or {}).get("U")),
            is_mine=bool(uid) and ows.get("UID") == uid,
        ), dd.get("VP") or []))
    return out


def _vp_int(v) -> int | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, str):
        try:
            return int(v[2:] if v[:2].lower() == "0x" else v, 16)
        except ValueError:
            return None
    return None


def _systems(pairs: list[tuple[Discovery, list]]) -> dict[tuple, System]:
    systems: dict[tuple, System] = {}

    def system_for(a: Address) -> System:
        key = a.system_key
        if key not in systems:
            systems[key] = System(
                address=Address(a.galaxy, a.x, a.y, a.z, a.system, 0),
                name=None, discoverer=None, discovered_at=None, is_mine=False)
        return systems[key]

    for d, _ in pairs:
        if d.kind == "SolarSystem":
            s = system_for(d.address)
            if s.discoverer is None:
                s.name, s.discoverer, s.discovered_at, s.is_mine = (
                    d.custom_name, d.discoverer, d.timestamp, d.is_mine)
    for d, vp in pairs:
        if d.kind != "Planet":
            continue
        s = system_for(d.address)
        if any(p.index == d.address.planet for p in s.planets):
            continue
        flags = _vp_int(vp[1]) if len(vp) > 1 else None
        biome = BIOMES[flags & 0xFFFF] if flags is not None and (flags & 0xFFFF) < len(BIOMES) else None
        s.planets.append(Planet(
            index=d.address.planet,
            biome=biome,
            infested=bool(flags is not None and (flags >> 16) & 1),
            name=d.custom_name,
            discoverer=d.discoverer,
            is_mine=d.is_mine,
            seed=_vp_int(vp[0]) if vp else None,
        ))
    for s in systems.values():
        s.planets.sort(key=lambda p: p.index)
    return systems
