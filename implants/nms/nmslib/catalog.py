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
