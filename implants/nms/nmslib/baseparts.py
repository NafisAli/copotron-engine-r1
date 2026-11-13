"""Base-part categories: which function a placed Base Part serves, from the build menu.

`tools/build_catalog.py` writes each Base Part's build-menu Group/SubGroup pairs to
the bundled base-part group map (data/base_parts.json). This module maps them onto
a fixed list of functional categories (#30). A part with no functional group is
structural: walls, floors, rooms, decor, wires and pipes. The categories are a
presentation detail, not domain vocabulary; names still come from the catalog.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path

from . import catalog
from .extract import CHEST_PART

PATH = Path(__file__).parent / "data" / "base_parts.json"

CATEGORIES = ("power", "storage", "refining", "farming", "extraction", "travel",
              "terminals", "utility", "base_computer", "corvette_modules")

# A build-menu subgroup that holds one function names it. Subgroups not listed here
# (walls, floors, roofs, rooms, corridors, decor, furniture, wall art, corvette
# hull and fairings, legacy freighter rooms) are structural.
SUBGROUPS = {
    "POWERPOWER": "power", "POWERSWITCHES": "power",
    "TECHSTORAGE": "storage", "BIGGS_IN_STOR": "storage",
    "TECHFARMING": "farming", "FRE_PLANTS": "farming", "BIGGSFARMING": "farming",
    "FRE_BIO_SUB": "farming", "SPACE_BIO_SUB": "farming",
    "POWERINDUSTRY": "extraction",
    "PLANETEXOCRAFT": "travel",
    "TECHTEMINALS": "terminals",  # sic: the game's own spelling
    # Mixed subgroups: their default, refined per part below.
    "TECHTECH": "utility", "PLANETPORTABLE": "utility", "FRE_TECH_OTHER": "utility",
    "FRE_TECH_SUB": "utility", "SPACE_TECH_SUB": "utility",
    "FRE_IND_SUB": "utility", "SPACE_IND_SUB": "utility",
    "BIGGS_ENGINES": "corvette_modules", "BIGGS_EXTRA": "corvette_modules",
    "BIGGS_GENERATOR": "corvette_modules", "BIGGS_GUNS": "corvette_modules",
    "BIGGS_HAB": "corvette_modules", "BIGGS_WINGS": "corvette_modules",
    "BIGGS_INT_DEC": "corvette_modules",
}

# Parts whose function differs from their subgroup's: the build menu files a
# refiner, a teleporter and a save point together under "portable tech".
PARTS = {
    "BASE_FLAG": "base_computer", "SB_BEACON": "base_computer",
    "BUILD_REFINER1": "refining", "BUILD_REFINER2": "refining", "BUILD_REFINER3": "refining",
    "FRE_ROOM_REFINE": "refining", "B_WALL_TECH0": "refining",
    "BUILDHARVESTER": "extraction", "BUILDGASHARVEST": "extraction", "O2_HARVESTER": "extraction",
    "BUILDSEAHARVEST": "extraction", "FRE_ROOM_EXTR": "extraction",
    "BUILDLANDINGPAD": "travel", "S_LANDINGZONE": "travel", "SET_LZ": "travel", "SET_LZ_SHIPBUIL": "travel",
    "TELEPORTER": "travel", "TELEPORTER_F": "travel", "U_MINIPORTAL": "travel", "U_MINIPORTAL_CV": "travel",
    "FRE_ROOM_TELEPO": "travel", "FRE_ROOM_VEHICL": "travel", "GARAGE_FREIGHT": "travel",
    "FRE_ROOM_NPCSCI": "terminals", "FRE_ROOM_NPCBUI": "terminals", "FRE_ROOM_NPCVEH": "terminals",
    "FRE_ROOM_NPCWEA": "terminals", "FRE_ROOM_NPCFAR": "terminals", "FRE_ROOM_SHOP": "terminals",
    "BUILDANTIMATTER": "power",
    "BASECAPSULE": "utility", "NPCFRIGTERM": "utility", "FRE_ROOM_COOK": "utility",
    # empty expansion rooms: structural
    "FRE_ROOM_IND": None, "FRE_ROOM_IND1": None, "FRE_ROOM_BIO": None, "FRE_ROOM_TECH": None,
}

# Wiring and piping: structural, though the menu files them with the parts they connect.
WIRES = frozenset({"U_POWERLINE", "U_PIPELINE", "U_PORTALLINE"})


def category_of(part_id: str, groups: list) -> str | None:
    """One part's category from its [[Group, SubGroupName], ...]; None means structural.

    Every numbered storage chest (`CHEST_PART`, the rule the inventory's built
    chests use) is storage, in whichever menu it sits.
    """
    if part_id in WIRES:
        return None
    if CHEST_PART.fullmatch(part_id):
        return "storage"
    if part_id in PARTS:
        return PARTS[part_id]
    return next((SUBGROUPS[sub] for _, sub in groups if sub in SUBGROUPS), None)


@lru_cache(maxsize=1)
def _groups() -> dict[str, list]:
    return json.loads(PATH.read_text(encoding="utf-8"))["parts"]


def category(part_id: str) -> str | None:
    """A placed part's category from the bundled group map (`^` ignored); None means structural."""
    part_id = part_id.lstrip("^")
    return category_of(part_id, _groups().get(part_id, []))


def listing(parts: Iterable[str]) -> dict:
    """A Base's placed part ids -> {"structural": n, "groups": [{category, name, ids, count, chests?}]}.

    One group per name in a category (every id sharing the name counts), ordered
    by category, then most placed. A part the catalog can't name is never given
    a guessed one: it counts as structural, with walls, decor, wires and pipes.
    Storage groups of numbered chests carry `chests`, the n of the inventory's
    `Storage n` (Chest{n+1}Inventory). `structural` plus every `count` is the part count.
    """
    groups: dict[tuple[str, str], dict] = {}
    structural = 0
    for part_id in parts:
        name = catalog.name_for(part_id)
        kind = category(part_id) if name else None
        if kind is None:
            structural += 1
            continue
        g = groups.setdefault((kind, name), {"category": kind, "name": name, "ids": set(), "count": 0})
        g["ids"].add(part_id.lstrip("^"))
        g["count"] += 1
    out = []
    for g in sorted(groups.values(), key=lambda g: (CATEGORIES.index(g["category"]), -g["count"], g["name"].lower())):
        entry = {**g, "ids": sorted(g["ids"])}
        chests = sorted({int(m.group(1)) for i in g["ids"] if (m := CHEST_PART.fullmatch(i))})
        if g["category"] == "storage" and chests:
            entry["chests"] = chests
        out.append(entry)
    return {"structural": structural, "groups": out}


def matches(parts: list[str], query: str) -> list[dict]:
    """The listing's groups that `query` names, as [{category, name, ids, count}]; [] when none.

    A category key matches its whole category. An exact id (case-sensitive, as
    ids are upper-case) matches only that id. Otherwise the text matches every
    name group that contains it: a filter, so `refiner` finds every refiner
    without an ambiguity refusal. Collapsed parts (structural, decor, wires,
    unnamed) are never matched, as the listing never names them.
    """
    q = query.strip().lstrip("^")
    groups = listing(parts)["groups"]
    if q.lower() in CATEGORIES:
        hits = [g for g in groups if g["category"] == q.lower()]
    elif q in _groups() or q in catalog.items():
        n = sum(1 for p in parts if p.lstrip("^") == q)
        hits = [{**g, "ids": [q], "count": n} for g in groups if q in g["ids"]]
    else:
        hits = [g for g in groups if q.lower() in g["name"].lower()]
    return [{k: g[k] for k in ("category", "name", "ids", "count")} for g in hits]
