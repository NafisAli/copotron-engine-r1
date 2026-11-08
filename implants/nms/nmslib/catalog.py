"""Item-name catalog: game id -> display name, from a bundled datamined snapshot.

Source: npm `assistantapps-nomanssky-info` (developerDetails GameId joined with
json/en names). Unknown ids return None and print raw: names are never guessed.
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
    c = _catalog()
    return {"source": c["source"], **c["meta"]}


def name_for(item_id: str) -> str | None:
    """Exact id, else the base id of a seeded procedural item (`UP_SHLD4#35337`)."""
    item_id = item_id.lstrip("^")
    hit = items().get(item_id)
    if hit is None and "#" in item_id:
        hit = items().get(item_id.split("#", 1)[0])
    return hit["name"] if hit else None
