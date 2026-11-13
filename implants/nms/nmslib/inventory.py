"""Inventory totals by id and by name group, over the model's Containers.

`inventory --search`/`--have` and `watch`'s Save Delta all total this way: a
name stands for every id that shares it (#25); an unnamed id stays its own group.
"""

from __future__ import annotations

import collections
from collections.abc import Callable, Iterable

from .model import Container, Slot


def aggregate(cs: Iterable[Container], keep: Callable[[Slot], bool]) -> dict[str, dict]:
    """Per-id totals of the kept stacks, with the amount held in each Container."""
    totals: dict[str, dict] = {}
    for c in cs:
        for x in c.slots:
            if not keep(x):
                continue
            t = totals.setdefault(x.id, {"id": x.id, "name": x.name, "type": x.item_type,
                                         "total": 0, "locations": collections.Counter()})
            t["total"] += x.amount
            t["locations"][c.label] += x.amount
    return totals


def by_name(totals: dict[str, dict]) -> list[dict]:
    """Per-id totals -> one row per name group (an unnamed id stays its own row)."""
    rows: dict[str, dict] = {}
    for t in totals.values():
        r = rows.setdefault(t["name"] or t["id"], {"ids": [], "name": t["name"], "types": set(), "total": 0,
                                                   "locations": collections.Counter()})
        r["ids"].append(t["id"])
        r["types"].add(t["type"])
        r["total"] += t["total"]
        r["locations"].update(t["locations"])
    return [{"ids": sorted(r["ids"]), "name": r["name"],
             "type": r["types"].pop() if len(r["types"]) == 1 else "Mixed",
             "total": r["total"], "locations": r["locations"]} for r in rows.values()]
