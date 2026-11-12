"""Item Catalog: game id -> display name, from the bundled Game Data Snapshot.

Built from the game's own files by `tools/build_catalog.py` (dev time only):
the product, substance, technology, procedural-technology, base-part and modular
customisation tables, joined with the English locale. Entries are `{name}`,
plus `stale` for ids a later build no longer had. Unknown ids return None and
print raw: names are never guessed.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

PATH = Path(__file__).parent / "data" / "items.json"


@lru_cache(maxsize=1)
def _catalog() -> dict:
    return json.loads(PATH.read_text(encoding="utf-8"))


def items() -> dict[str, dict]:
    return _catalog()["items"]


@lru_cache(maxsize=1)
def _groups() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for item_id, meta in sorted(items().items()):
        out.setdefault(meta["name"].lower(), []).append(item_id)
    return out


def group(name: str) -> list[str]:
    """The name group: every catalog id with this name (case-insensitive), sorted.

    Many ids share a name (9 are "Hyperdrive": ship tech, corvette part and
    upgrade modules), so a name stands for all of them, never one picked at random.
    """
    return _groups().get(name.lower(), [])


def names() -> list[str]:
    """Every distinct item name in the catalog."""
    return [items()[ids[0]]["name"] for ids in _groups().values()]


def snapshot() -> dict:
    """Provenance header: MBINCompiler tag, libMBIN version, game build, save base version, ..."""
    return _catalog()["snapshot"]


def base_id(item_id: str) -> str:
    """`^UP_SHLD4#35337` -> `UP_SHLD4`: no caret, no procedural seed."""
    return item_id.lstrip("^").split("#", 1)[0]


def name_for(item_id: str) -> str | None:
    """Exact id, else the base id of a seeded procedural item (`UP_SHLD4#35337`)."""
    item_id = item_id.lstrip("^")
    hit = items().get(item_id) or items().get(base_id(item_id))
    return hit["name"] if hit else None
