# /// script
# requires-python = ">=3.12"
# dependencies = ["lz4>=4.3", "orjson>=3.10"]
# ///
"""No Man's Sky implant: read-only, deterministic queries over a save.

    uv run implants/nms/nms.py <command> [--json] [--save PATH | --slot N]

Commands: status, inventory, bases, convert, saves (find, route, system: see the
Discovery Atlas ticket). Text by default, one JSON document with --json.
Each JSON document names its shape in `schema` (nms.<command>/1) and carries a
`notes` array of advice (`[]` when none; final `Note` lines in text). Errors go to
stderr. Exit codes: 0 ok, 1 requisition short (inventory --have),
2 error or bad usage.
"""

from __future__ import annotations

import time

T_START = time.perf_counter()  # bench: import cost is part of the budget

import argparse  # noqa: E402
import collections  # noqa: E402
import json  # noqa: E402
import sys  # noqa: E402
from collections.abc import Sequence  # noqa: E402
from pathlib import Path  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))

from nmslib import catalog, decode, extract, locate  # noqa: E402
from nmslib.coords import SAME_REGION_LY, Address, parse_galaxy  # noqa: E402
from nmslib.decode import SaveDecodeError  # noqa: E402
from nmslib.model import Container, Save, Slot  # noqa: E402

T_IMPORTED = time.perf_counter()

SCHEMA_VERSION = 1  # every --json shape is pinned by the tests; a breaking change bumps it

CATEGORIES = [
    "suit", "ship", "ships", "multitool", "freighter", "storage", "exocraft",
    "ingredients", "corvette", "rocket-locker", "fishing-platform", "bait-box", "food-unit",
    "grave", "chest-magic",
]


class Fail(Exception):
    pass


# ---- helpers -----------------------------------------------------------------
def emit(args, data: dict, text: list[str], schema: str | None = None, notes: Sequence[str] = ()) -> None:
    """Text, or one JSON document whose `schema` (`nms.<command>/<version>`) names its shape.

    `notes` is advice about the tool, not a fault in the Save (that is `warnings`):
    an always-present array in JSON, and final `Note` lines on stdout in text.
    """
    if args.json:
        doc = {"schema": f"nms.{schema}/{SCHEMA_VERSION}", **data, "notes": list(notes)} if schema else data
        print(json.dumps(doc, ensure_ascii=False, indent=2))
    else:
        print("\n".join([*text, *(f"Note      {n}" for n in notes)]))


def load(args) -> Save:
    return extract.load(locate.resolve(args.save, args.slot))


def save_ref(s: Save) -> dict:
    return {**s.file.to_json(), "version": s.version, "save_name": s.player.save_name}


def ly(v: float | None) -> str:
    if v is None:
        return "other galaxy"
    if v == SAME_REGION_LY:
        return f"~{v:,.0f} ly (same region)"
    return f"{v:,.0f} ly"


def hours(seconds: int) -> str:
    h, m = divmod(seconds // 60, 60)
    return f"{h}h {m:02d}m"


def file_line(s: Save) -> str:
    f = s.file
    where = f"slot {f.slot} {f.kind}" if f.slot else "file"
    return f"{where} · {f.path.name} · {local(f.modified)} · {f.account} ({f.account_kind})"


def local(ts: float) -> str:
    from datetime import datetime
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


def planet_label(s: Save, a: Address) -> tuple[str | None, str | None, str | None]:
    """(system name, planet name, planet biome) from the save's own discoveries."""
    sysm = s.system_at(a)
    if not sysm:
        return None, None, None
    p = next((p for p in sysm.planets if p.index == a.planet), None)
    return sysm.name, (p.name if p else None), (p.biome if p else None)


# ---- status ------------------------------------------------------------------
def cmd_status(args) -> int:
    s = load(args)
    p = s.player
    a = p.location
    sys_name, planet_name, biome = planet_label(s, a)
    ship = p.current_ship
    data = {
        "save": save_ref(s),
        "context": p.context,
        "game_mode": p.game_mode,
        "play_time_s": p.play_time_s,
        "summary": p.save_summary,
        "location": {
            **a.to_json(),
            "system_name": sys_name,
            "planet_name": planet_name,
            "planet_biome": biome,
            "distance_to_core_ly": round(a.distance_to_core_ly),
        },
        "currencies": {"units": p.units, "nanites": p.nanites, "quicksilver": p.quicksilver},
        "current_ship": None if not ship else {
            "name": ship.name or None, "kind": ship.kind, "class": ship.inventory_class, "index": ship.index},
        "warnings": s.warnings,
    }
    place = " · ".join(x for x in [
        sys_name and f"system {sys_name}", f"planet {a.planet}" + (f" {planet_name}" if planet_name else "")
        + (f" ({biome})" if biome else ""),
    ] if x)
    text = [
        f"Save      {file_line(s)}",
        f"Mode      {p.game_mode} · {p.context} context · played {hours(p.play_time_s)}",
        f"Where     {p.save_summary or '-'}",
        f"Galaxy    {a.galaxy_name} (#{a.galaxy + 1}) · {place}",
        f"Glyphs    {a.glyphs}  {a.glyph_emoji}",
        f"Booster   {a.signal_booster} · voxel {a.x},{a.y},{a.z} · {ly(a.distance_to_core_ly)} to core",
        f"Wallet    {p.units:,} units · {p.nanites:,} nanites · {p.quicksilver:,} quicksilver",
        f"Ship      " + (f"{ship.name or 'unnamed'} ({ship.kind}, {ship.inventory_class}-class)" if ship else "-"),
    ]
    text += [f"Warning   {w}" for w in s.warnings]
    emit(args, data, text, "status")
    return 0


# ---- inventory ---------------------------------------------------------------
def slot_json(sl: Slot) -> dict:
    return {
        "id": sl.id, "name": sl.name, "amount": sl.amount, "max_amount": sl.max_amount,
        "type": sl.item_type, "at_cap": sl.at_cap, "damage_factor": sl.damage_factor,
        "fully_installed": sl.fully_installed, "x": sl.x, "y": sl.y,
    }


def container_json(c: Container, slots: list[Slot] | None = None) -> dict:
    slots = c.slots if slots is None else slots
    return {
        "category": c.category, "owner": c.owner, "grid": c.grid, "is_current": c.is_current,
        "capacity": c.capacity, "used": len(c.slots),
        "at_cap": sum(1 for x in c.slots if x.at_cap),
    }


def slot_filter(args):
    def keep(sl: Slot) -> bool:
        if args.tech and not sl.is_tech:
            return False
        if args.cargo and sl.is_tech:
            return False
        if args.near_cap and not sl.near_cap():
            return False
        return True
    return keep


def select_containers(s: Save, category: str | None, name: str | None) -> list[Container]:
    cs = s.containers
    if category == "ship":
        cs = [c for c in cs if c.category == "ship" and c.is_current]
    elif category == "ships":
        cs = [c for c in cs if c.category == "ship"]
    elif category:
        cs = [c for c in cs if c.category == category]
    if name:
        cs = [c for c in cs if name.lower() in c.owner.lower()]
    return cs


def cmd_inventory(args) -> int:
    if args.tech and args.cargo:
        raise Fail("--tech and --cargo are mutually exclusive")
    if args.name and args.category not in ("ships", "multitool", "storage", "exocraft", None):
        raise Fail("--name applies to ships, multitool, storage and exocraft")
    s = load(args)
    keep = slot_filter(args)
    cs = select_containers(s, args.category, args.name)
    base = {"save": save_ref(s), "catalog": catalog.snapshot()["libmbin_version"]}

    if args.have:
        return inventory_have(args, s, cs, keep, base)
    if args.search:
        return inventory_search(args, cs, keep, base)
    if args.category:
        return inventory_list(args, cs, keep, base)

    filtered = args.tech or args.cargo or args.near_cap
    rows, data_rows = [], []
    for c in cs:
        sel = [x for x in c.slots if keep(x)]
        if filtered and not sel:
            continue
        cap = sum(1 for x in c.slots if x.at_cap)
        cur = "" if c.is_current or c.category not in ("ship", "multitool") else "  (stored)"
        rows.append(f"{c.category:<16} {c.label:<28} {len(c.slots):>3}/{c.capacity:<3}"
                    + (f"  {cap} at cap" if cap else "") + (f"  {len(sel)} match" if filtered else "") + cur)
        data_rows.append({**container_json(c), **({"matching": len(sel)} if filtered else {})})
    emit(args, {**base, "mode": "summary", "containers": data_rows}, rows or ["(no containers)"], "inventory")
    return 0


def inventory_list(args, cs, keep, base) -> int:
    text, out = [], []
    for c in cs:
        sel = [x for x in c.slots if keep(x)]
        if not sel and (args.tech or args.cargo or args.near_cap):
            continue
        out.append({**container_json(c), "items": [slot_json(x) for x in sel]})
        text.append(f"{c.label} — {len(c.slots)}/{c.capacity}" + ("" if c.is_current else " (stored)"))
        for section, items in (("cargo", [x for x in sel if not x.is_tech]), ("tech", [x for x in sel if x.is_tech])):
            if not items:
                continue
            text.append(f"  {section}:")
            for x in sorted(items, key=lambda x: x.display.lower()):
                amt = "" if x.is_tech else f" ×{x.amount}" + (f"/{x.max_amount}" if x.max_amount > 1 else "")
                flags = (" [cap]" if x.at_cap else "") + (" [damaged]" if x.is_tech and x.damage_factor > 0 else "") \
                    + ("" if x.fully_installed else " [not installed]")
                raw = "" if x.name is None else f"  ({x.id})"
                text.append(f"    {x.display}{amt}{flags}{raw}")
        if not sel:
            text.append("  (empty)")
    emit(args, {**base, "mode": "category", "category": args.category, "containers": out},
         text or [f"(no {args.category} containers)"], "inventory")
    return 0


def aggregate(cs, keep) -> dict[str, dict]:
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


def fmt_item(t: dict) -> str:
    where = ", ".join(f"{k} {v}" for k, v in t["locations"].most_common())
    ids = f"  [{', '.join(t['ids'])}]" if len(t["ids"]) > 1 else ""
    return f"{t['name'] or t['ids'][0]} ×{t['total']} ({where}){ids}"


def inventory_search(args, cs, keep, base) -> int:
    q = args.search.lower()
    hits = [t for t in by_name(aggregate(cs, keep))
            if any(q in i.lower() for i in t["ids"]) or (t["name"] and q in t["name"].lower())]
    hits.sort(key=lambda t: (t["name"] or t["ids"][0]).lower())
    data = {**base, "mode": "search", "query": args.search,
            "items": [{**t, "locations": dict(t["locations"].most_common())} for t in hits]}
    emit(args, data, [fmt_item(t) for t in hits] or [f"no items match {args.search!r}"], "inventory")
    return 0


def resolve_item(query: str, totals: dict[str, dict]) -> tuple[list[str], str | None]:
    """Item query -> (ids, name); ([], None) when nothing matches.

    An exact id resolves to that one id. Ids are upper-case and may equal a name
    (`HYPERDRIVE`), so the id must match case-sensitively; an exact name, in any
    case, resolves to its whole name group. An id in another case comes next.
    A substring is ambiguous only when it matches more than one distinct name;
    otherwise it resolves to that name's group.
    """
    q = query.lstrip("^")
    known = [*catalog.items(), *totals]
    if q in known:
        return [q], catalog.name_for(q)
    if catalog.group(q):
        ids = catalog.group(q)
        return ids, catalog.name_for(ids[0])
    ql = q.lower()
    for item_id in known:
        if item_id.lower() == ql:
            return [item_id], catalog.name_for(item_id)
    hits = sorted(n for n in catalog.names() if ql in n.lower())
    if len(hits) > 1:
        raise Fail(f"{query!r} is ambiguous: {', '.join(hits[:8])}" + (" ..." if len(hits) > 8 else ""))
    return (catalog.group(hits[0]), hits[0]) if hits else ([], None)


def stacks_of(ids: list[str], totals: dict[str, dict]) -> tuple[int, collections.Counter]:
    """Total and per-location amounts of every stack whose id, or base id, is in `ids`."""
    want = set(ids)
    total, where = 0, collections.Counter()
    for t in totals.values():
        if t["id"] in want or catalog.base_id(t["id"]) in want:
            total += t["total"]
            where.update(t["locations"])
    return total, where


def inventory_have(args, s, cs, keep, base) -> int:
    totals = aggregate(cs, keep)
    reqs, text = [], []
    for spec in args.have:
        item, sep, n = spec.rpartition(":")
        if not sep or not n.isdigit() or not item:
            raise Fail(f"--have expects ITEM:N, got {spec!r}")
        need = int(n)
        ids, name = resolve_item(item, totals)
        if not ids:
            raise Fail(f"unknown item {item!r} (not in catalog or inventory)")
        have, where_n = stacks_of(ids, totals)
        met = have >= need
        reqs.append({"query": item, "ids": ids, "name": name, "need": need, "have": have,
                     "met": met, "short": max(0, need - have), "locations": dict(where_n)})
        where = ", ".join(f"{k} {v}" for k, v in where_n.most_common()) or "none"
        text.append(f"{'ok   ' if met else 'SHORT'} {name or ids[0]}: {have}/{need}"
                    + ("" if met else f" (need {need - have} more)") + f"  [{where}]")
    all_met = all(r["met"] for r in reqs)
    emit(args, {**base, "mode": "have", "all_met": all_met, "requirements": reqs}, text, "inventory")
    return 0 if all_met else 1


# ---- bases -------------------------------------------------------------------
def cmd_bases(args) -> int:
    s = load(args)
    here = s.player.location
    pool = s.bases if args.all else s.my_bases
    if args.name:
        matches = [b for b in pool if args.name.lower() in b.name.lower()]
        exact = [b for b in matches if b.name.lower() == args.name.lower()]
        matches = exact or matches
        if not matches:
            raise Fail(f"no {'' if args.all else 'own '}base matches {args.name!r}"
                       + ("" if args.all else " (try --all for visited bases)"))
        if len(matches) > 1:
            raise Fail(f"{args.name!r} matches {len(matches)} bases: "
                       + ", ".join(b.name or "(unnamed)" for b in matches[:8]))
        b = matches[0]
        a = b.address
        d = here.distance_ly(a)
        sys_name, planet_name, biome = planet_label(s, a)
        data = {"save": save_ref(s), "base": {**b.to_json(), "distance_ly": None if d is None else round(d),
                "system_name": sys_name, "planet_name": planet_name, "planet_biome": biome}}
        text = [
            f"{b.name or '(unnamed)'} — {b.kind}" + ("" if b.is_mine else f" · owner {b.owner_name or b.owner_uid}"),
            f"Galaxy    {a.galaxy_name} (#{a.galaxy + 1}) · planet {a.planet}"
            + (f" {planet_name}" if planet_name else "") + (f" ({biome})" if biome else "")
            + (f" · system {sys_name}" if sys_name else ""),
            f"Glyphs    {a.glyphs}  {a.glyph_emoji}",
            f"Booster   {a.signal_booster} · voxel {a.x},{a.y},{a.z}",
            f"Distance  {ly(d)} from you",
            f"Objects   {b.object_count} · last update {local(b.last_update) if b.last_update else '-'}",
        ]
        emit(args, data, text, "bases")
        return 0

    rows = sorted(pool, key=lambda b: (here.distance_ly(b.address) is None, here.distance_ly(b.address) or 0))
    data = {"save": save_ref(s), "scope": "all" if args.all else "mine",
            "bases": [{**b.to_json(), "distance_ly": None if here.distance_ly(b.address) is None
                       else round(here.distance_ly(b.address))} for b in rows]}
    text = [f"{(b.name or '(unnamed)')[:30]:<30} {b.kind:<18} {b.address.galaxy_name[:12]:<12} "
            f"{b.address.glyphs}  {ly(here.distance_ly(b.address)):>12}"
            + ("" if b.is_mine else f"  · {b.owner_name or '?'}") for b in rows]
    if not args.all:
        others = len(s.bases) - len(s.my_bases)
        if others:
            text.append(f"(+{others} visited bases from other players: --all)")
    emit(args, data, text or ["(no bases)"], "bases")
    return 0


# ---- convert -----------------------------------------------------------------
def parse_location(value: str, galaxy: int, planet: int | None, system: int | None) -> Address:
    v = value.strip()
    parts = v.split(":")
    if len(parts) == 4 and all(1 <= len(p) <= 4 for p in parts):
        return Address.from_signal_booster(v, galaxy, planet or 0)
    nums = v.replace(" ", "").split(",")
    if len(nums) == 3 and all(n.lstrip("-").isdigit() for n in nums):
        if system is None:
            raise Fail("voxel input needs --system N (solar system index)")
        x, y, z = (int(n) for n in nums)
        return Address(galaxy, x, y, z, system, planet or 0)
    a = Address.from_glyphs(v, galaxy)
    if planet is not None:
        a = Address(a.galaxy, a.x, a.y, a.z, a.system, planet)
    return a


def int_auto(text: str) -> int:
    return int(text, 0)


def cmd_convert(args) -> int:
    try:
        g = parse_galaxy(args.galaxy) if args.galaxy is not None else 0
        a = parse_location(args.value, g, args.planet, args.system)
    except ValueError as e:
        raise Fail(str(e)) from None
    data = {"input": args.value, **a.to_json(), "distance_to_core_ly": round(a.distance_to_core_ly),
            "is_black_hole": a.is_black_hole, "is_atlas_interface": a.is_atlas_interface}
    text = [
        f"Galaxy    {a.galaxy_name} (#{a.galaxy + 1}, index {a.galaxy})",
        f"Glyphs    {a.glyphs}  {a.glyph_emoji}",
        f"Address   {a.galactic_address}",
        f"Booster   {a.signal_booster}",
        f"Voxel     x={a.x} y={a.y} z={a.z} · system {a.system} (0x{a.system:03X}) · planet {a.planet}",
        f"Core      {ly(a.distance_to_core_ly)}"
        + (" · black hole" if a.is_black_hole else "") + (" · Atlas Interface" if a.is_atlas_interface else ""),
    ]
    emit(args, data, text, "convert")
    return 0


# ---- saves -------------------------------------------------------------------
def cmd_saves(args) -> int:
    root = locate.default_root()
    env = locate.env_save_path()
    if env and Path(env).expanduser().is_dir():
        root = Path(env).expanduser()
    elif env and Path(env).expanduser().is_file():
        root = Path(env).expanduser().parent
    try:
        selected = locate.resolve(None, None).path
    except locate.LocateError:
        selected = None
    accounts = []
    text = [f"Root      {root}" + (f"  (NMS_SAVE_PATH={env})" if env else "")]
    for d in locate.account_dirs(root):
        saves = locate.list_saves(d)
        slots = collections.defaultdict(dict)
        for sf in saves:
            slots[sf.slot][sf.kind] = sf
        acct = {"account": d.name, "kind": locate.account_kind(d.name), "slots": []}
        text.append(f"\n{d.name} ({acct['kind']})")
        text.append(f"  {'slot':<5}{'newest':<8}{'modified':<22}{'mode':<12}{'played':<10}summary")
        for n in sorted(slots, key=lambda n: -max(f.modified for f in slots[n].values())):
            newest = max(slots[n].values(), key=lambda f: f.modified)
            info = {"mode": None, "context": None, "play_time_s": None, "summary": None}
            if not args.quick:
                try:
                    sv = extract.load(newest)
                    info = {"mode": sv.player.game_mode, "context": sv.player.context,
                            "play_time_s": sv.player.play_time_s, "summary": sv.player.save_summary}
                except Exception as e:  # one unreadable slot must not hide the rest
                    info["summary"] = f"unreadable: {e}"
            acct["slots"].append({
                "slot": n,
                "manual": slots[n]["manual"].to_json() if "manual" in slots[n] else None,
                "auto": slots[n]["auto"].to_json() if "auto" in slots[n] else None,
                "newest": newest.kind, "selected": newest.path == selected, **info,
            })
            mark = "*" if newest.path == selected else " "
            mode = (info["mode"] or "") + ("/exp" if info["context"] == "expedition" else "")
            played = hours(info["play_time_s"]) if info["play_time_s"] is not None else ""
            text.append(f" {mark}{n:<5}{newest.kind:<8}{local(newest.modified):<22}"
                        f"{mode:<12}{played:<10}{info['summary'] or ''}")
        accounts.append(acct)
    text.append("\n* = read by default (newest overall). Pick another with --slot N.")
    emit(args, {"root": str(root), "nms_save_path": env, "selected": str(selected) if selected else None,
                "accounts": accounts}, text, "saves")
    return 0


# ---- bench (dev only) ----------------------------------------------------------
def cmd_bench(args) -> int:
    """Phase timings of one cold decode, to check the 250 ms wall budget by hand (#20)."""
    f = locate.resolve(args.save, args.slot)
    t0 = time.perf_counter()
    with open(f.path, "rb") as fh:  # read-only, always
        raw = fh.read()
    t1 = time.perf_counter()
    doc = decode.decode_bytes(raw)
    t2 = time.perf_counter()
    s = extract.build(doc, f)
    t3 = time.perf_counter()
    slots = [sl for c in s.containers for sl in c.slots]
    ms = {"import": T_IMPORTED - T_START, "read": t1 - t0, "decode": t2 - t1, "extract": t3 - t2,
          "total_in_process": t3 - T_START}
    data = {"save": save_ref(s), "bytes_on_disk": len(raw), "obfuscated": isinstance(doc, decode.Node),
            "timings_ms": {k: round(v * 1e3, 1) for k, v in ms.items()},
            "counts": {"containers": len(s.containers), "slots": len(slots),
                       "named_slots": sum(1 for sl in slots if sl.name), "bases": len(s.bases),
                       "systems": len(s.systems), "discoveries": len(s.discoveries)}}
    emit(args, data, [f"{k:<17} {v:>7.1f} ms" for k, v in data["timings_ms"].items()]
         + [f"{k:<17} {v:>7}" for k, v in data["counts"].items()])
    return 0


# ---- atlas commands (separate ticket) ---------------------------------------
def cmd_atlas(args) -> int:
    raise Fail(f"'{args.command}' is not implemented yet: it ships with the Discovery Atlas "
               "(copotron-engine-r1#14)")


# ---- argument parsing --------------------------------------------------------
def parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="one JSON document on stdout")
    pick = argparse.ArgumentParser(add_help=False)
    g = pick.add_mutually_exclusive_group()
    g.add_argument("--save", metavar="PATH", help="read this .hg file")
    g.add_argument("--slot", type=int, metavar="N", help="read the newest file of slot N (1-15)")

    p = argparse.ArgumentParser(prog="nms", description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("status", parents=[common, pick], help="location, wallet, mode, ship").set_defaults(fn=cmd_status)

    inv = sub.add_parser("inventory", parents=[common, pick], help="queryable inventory")
    inv.add_argument("category", nargs="?", choices=CATEGORIES)
    inv.add_argument("--name", help="filter owners by name (ships, multitool, storage, exocraft)")
    inv.add_argument("--search", metavar="TEXT", help="match item name or id, totalled per name")
    inv.add_argument("--have", nargs="+", metavar="ITEM:N",
                     help="requisition check by name (every id with that name) or exact id; exit 1 if short")
    inv.add_argument("--tech", action="store_true", help="technology only")
    inv.add_argument("--cargo", action="store_true", help="non-technology only")
    inv.add_argument("--near-cap", action="store_true", help="stacks at >= 90%% of max")
    inv.set_defaults(fn=cmd_inventory)

    b = sub.add_parser("bases", parents=[common, pick], help="your bases, or one in detail")
    b.add_argument("name", nargs="?")
    b.add_argument("--all", action="store_true", help="include other players' bases cached in the save")
    b.set_defaults(fn=cmd_bases)

    c = sub.add_parser("convert", parents=[common], help="glyphs / booster / address / voxel")
    c.add_argument("value", help="12 glyphs (hex, emoji or names), 0x address, XXXX:YYYY:ZZZZ:SSSS, or x,y,z")
    c.add_argument("--galaxy", help="index (0-255), #N (1-based) or name; default Euclid")
    c.add_argument("--planet", type=int, help="planet index (booster/voxel input, or override)")
    c.add_argument("--system", type=int_auto, help="solar system index, for x,y,z input")
    c.set_defaults(fn=cmd_convert)

    sv = sub.add_parser("saves", parents=[common], help="accounts and slots")
    sv.add_argument("--quick", action="store_true", help="skip reading each slot's summary")
    sv.set_defaults(fn=cmd_saves)

    sub.add_parser("bench", parents=[common, pick], help="(dev) decode timings for the 250 ms budget")         .set_defaults(fn=cmd_bench)

    for name in ("find", "route", "system"):
        a = sub.add_parser(name, parents=[common, pick], help="(Discovery Atlas, not yet)")
        a.add_argument("rest", nargs=argparse.REMAINDER)
        a.set_defaults(fn=cmd_atlas)
    return p


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")  # glyph emoji on Windows consoles
    args = parser().parse_args(argv)
    if not hasattr(args, "save"):
        args.save = args.slot = None
    try:
        return args.fn(args)
    except (Fail, locate.LocateError, SaveDecodeError) as e:
        print(f"nms: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
