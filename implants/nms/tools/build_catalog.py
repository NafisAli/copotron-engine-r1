# /// script
# requires-python = ">=3.12"
# dependencies = ["hgpaktool==1.1.3", "lz4>=4.3"]
# ///
"""Dev-time refresh of the Game Data Snapshot: nmslib/data/items.json, base_parts.json and mapping.json.

Never run by the implant. All three files come from ONE pinned MBINCompiler release
(a tag plus a SHA-256 per asset, below), so they always describe the same game data:

  1. Download MBINCompiler.exe, mapping.json and report.json for the pinned tag
     and check each against its SHA-256. A mismatch refuses the build.
  2. COPY the two PAKs that hold the tables out of the game dir into --work. The
     install is only ever read, never extracted in place.
  3. Unpack the item tables, `basebuildingobjectstable` and the English locale with
     the pinned hgpaktool.
  4. Run `MBINCompiler convert` WITHOUT -q. Any "File not recognized" (a template
     GUID this compiler does not know) refuses the build: a mismatched compiler
     still exits 0 and silently drops items.
  5. Join each table row (ID -> NameLower|Name -> English) and merge it over the
     current snapshot. Ids missing from the build are kept and marked stale. A
     build more than 10% smaller is refused. Write each Base Part's build-menu
     Group/SubGroup pairs to the base-part group map (#30); names stay in items.json.
  6. Lay the release mapping.json over the bundled merged mapping (no key dropped).
  7. Record provenance in the snapshot header, including the highest save base
     version (`Version % 512`) among the local saves, for the staleness check.

    uv run implants/nms/tools/build_catalog.py --work %TEMP%/nms-catalog \\
        [--game "E:/SteamLibrary/steamapps/common/No Man's Sky"]

To move to a newer release: list /releases (not /releases/latest: every release
is published as a prerelease, so "latest" lags). Take the newest tag, then pin
that tag and the `digest` of each of its assets below.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

MBINCOMPILER_TAG = "v7.10.0-pre1"
MBINCOMPILER_ASSETS = {  # asset -> SHA-256 (the GitHub release `digest`)
    "MBINCompiler.exe": "035c5645753be3cced709b9f1bdcd73d25ea9c5e2f06a438dba45a38d11f9b41",
    "mapping.json": "677ce606579831996be4c858ac4193959190958604c4f460eb560dc1e1d6c626",
    "report.json": "cacbf53416e50d73423c787913e4dc3e59c1c27cd8947798d9966d0ff4d18f52",
}
RELEASE_URL = "https://github.com/monkeyman192/MBINCompiler/releases/download/{tag}/{asset}"
HGPAKTOOL = "hgpaktool==1.1.3"
DEFAULT_GAME = Path("C:/Program Files (x86)/Steam/steamapps/common/No Man's Sky")
PAKS = ["NMSARC.MetadataEtc.pak", "NMSARC.Precache.pak"]
IMPLANT = Path(__file__).resolve().parent.parent
DATA = IMPLANT / "nmslib" / "data"

# Every table uses the GcProductTable template or one the same join reads
# (ID -> NameLower|Name locale key -> English). Entries are {name} only.
TABLES = [
    "nms_reality_gcsubstancetable",
    "nms_reality_gcproducttable",
    "nms_reality_gctechnologytable",
    "nms_reality_gcproceduraltechnologytable",
    "nms_basepartproducts",  # Base Parts (#19)
    "nms_modularcustomisationproducts",  # modular ship and skull parts (#25)
]
# The build menu: each Base Part's Group/SubGroup pairs. The implant maps them onto
# its fixed categories (nmslib/baseparts.py); names still come from the tables above.
BASE_PART_TABLE = "basebuildingobjectstable"
TAG = re.compile(r"<[^>]*>")
MBIN_NAME = re.compile(r"[\w.-]+\.mbin", re.IGNORECASE)
NOT_RECOGNIZED = "File not recognized"


class BuildRefused(Exception):
    """The build would write a wrong or shrunken snapshot; nothing is written."""


# ---- MBINCompiler gate -----------------------------------------------------------
def check_convert_output(output: str) -> None:
    """Refuse when MBINCompiler did not recognise a file's template GUID.

    A mismatched compiler only warns and still exits 0 (v6.11 on 7.x files
    dropped 3.9% of items), so `convert` runs without -q and this scans its output.
    """
    bad, last = [], None
    for line in output.splitlines():
        names = MBIN_NAME.findall(line)
        if names:
            last = names[-1]
        if NOT_RECOGNIZED in line:
            bad.append(names[-1] if names else last or line.strip())
    if bad:
        raise BuildRefused(f"MBINCompiler does not match the game files ({NOT_RECOGNIZED}): "
                           + ", ".join(dict.fromkeys(bad)))


# ---- catalog tables ---------------------------------------------------------------
def _props(el) -> dict:
    return {c.get("name"): c.get("value") for c in el if c.tag == "Property"}


def _rows(path: Path):
    table = ET.parse(path).getroot().find("Property")
    return [] if table is None else [_props(row) for row in table]


def parse(mxml_dir: Path) -> tuple[dict, dict]:
    """Converted MXML -> ({id: {"name"}}, stats). Ids without an English name are left out."""
    locale: dict[str, str] = {}
    for f in sorted(mxml_dir.rglob("nms_*_english.MXML")):
        for p in _rows(f):
            if p.get("Id") and p.get("English"):
                locale[p["Id"]] = TAG.sub("", p["English"]).strip()
    items: dict[str, dict] = {}
    found: dict[str, int] = {}
    missing = []
    for stem in TABLES:
        files = sorted(mxml_dir.rglob(f"{stem}.MXML"))
        if not files:
            missing.append(stem)
            continue
        named = 0
        for f in files:
            for p in _rows(f):
                item_id = p.get("ID")
                name = locale.get(p.get("NameLower") or "") or locale.get(p.get("Name") or "")
                if item_id and name and item_id not in items:
                    items[item_id] = {"name": name}
                    named += 1
        found[stem] = named
    if missing:
        raise BuildRefused(f"tables missing from the extraction: {', '.join(missing)}")
    return items, {"locale_keys": len(locale), "tables": found}


def parse_base_parts(mxml_dir: Path) -> dict[str, list[list[str]]]:
    """Converted `basebuildingobjectstable` -> {part id: [[Group, SubGroupName], ...]}.

    Every entry is kept, also one with no group (it counts as structural), so the
    map lists every Base Part the game knows. A missing or empty table refuses the build.
    """
    files = sorted(mxml_dir.rglob(f"{BASE_PART_TABLE}.MXML"))
    if not files:
        raise BuildRefused(f"table missing from the extraction: {BASE_PART_TABLE}")
    objects = next((p for p in ET.parse(files[0]).getroot() if p.get("name") == "Objects"), None)
    parts: dict[str, list[list[str]]] = {}
    for row in [] if objects is None else objects:
        props = {c.get("name"): c for c in row if c.tag == "Property"}
        part_id = props.get("ID").get("value") if "ID" in props else None
        if not part_id or part_id in parts:
            continue
        groups = props.get("Groups")
        parts[part_id] = [[g.get("Group") or "", g.get("SubGroupName") or ""]
                          for g in (_props(e) for e in ([] if groups is None else groups))]
    if not parts:
        raise BuildRefused(f"no entries in {BASE_PART_TABLE}")
    return parts


def merge(old: dict, fresh: dict) -> dict:
    """Fresh rows win; ids missing from this build are kept, marked stale, so old saves still resolve.

    A build more than 10% smaller than the current snapshot is refused: that is
    what a broken extraction or a mismatched compiler looks like.
    """
    refuse_shrink(old, fresh, "items")
    kept = {k: {"name": v["name"], "stale": True} for k, v in old.items() if k not in fresh}
    return dict(sorted({**kept, **fresh}.items()))


def merge_base_parts(old: dict, fresh: dict) -> dict:
    """The same rule for the base-part group map: fresh groups win, dropped parts keep theirs."""
    refuse_shrink(old, fresh, "base parts")
    return dict(sorted({**old, **fresh}.items()))


def refuse_shrink(old: dict, fresh: dict, what: str) -> None:
    if old and len(fresh) < 0.9 * len(old):
        raise BuildRefused(f"the build has {len(fresh)} {what} against {len(old)} in the current snapshot")


def save_base_version(versions) -> int:
    """Highest save base version (`Version % 512`, libNOM.io) among the local saves.

    Every game-mode and season offset is a multiple of 512, so the remainder is
    the base version whatever the mode. A save above this is newer than the snapshot.
    """
    bases = [v % 512 for v in versions]
    if not bases:
        raise BuildRefused("no local save found to record the save base version from")
    return max(bases)


# ---- key mapping ---------------------------------------------------------------
def overlay_mapping(merged: dict, release: dict, tag: str, sha256: str) -> dict:
    """Lay a release `mapping.json` over the bundled merged mapping.

    The release wins on conflicts and no key is dropped: upstream has removed
    keys before (`bQN`, v6.40), and old saves still carry them. The savewizard
    fixups are kept as they are.

    The release hashes field names to 3 chars, so two classes can share a key
    (`NE3` is both GcPlayerStateData.ShipShield and a solar-system flag). The
    name listed first (player state is hashed first) stays the key's name, and
    the others become `aliases`, which the lazy lookup also resolves.
    """
    release_keys: dict[str, str] = {}
    aliases = {k: list(v) for k, v in merged.get("aliases", {}).items()}
    for e in release["Mapping"]:
        key, name = e["Key"], e["Value"]
        first = release_keys.setdefault(key, name)
        if name != first and name not in aliases.setdefault(key, []):
            aliases[key].append(name)
    return {
        "libMBIN_version": release["libMBIN_version"],
        "mbincompiler_tag": tag,
        "mapping_sha256": sha256,
        "sources": {
            "keys": [f"MBINCompiler {tag} mapping.json", "previous merged mapping (keys the release lacks)"],
            "fixups": "mapping_savewizard.json (renames applied after lookup)",
        },
        "keys": {**merged["keys"], **release_keys},
        "aliases": {k: v for k, v in sorted(aliases.items()) if v},
        "fixups": merged["fixups"],
    }


# ---- provenance -------------------------------------------------------------------
def installed_build(manifest: str) -> dict:
    """The installed BuildID and branch from `appmanifest_275850.acf` (Valve KeyValues).

    Only the top-level `buildid` is the installed build. The branch listing
    further down carries newer builds that are available but not installed.
    """
    out = {"game_buildid": None, "game_branch": "public"}
    stack: list[str] = []
    pending = None
    for line in manifest.splitlines():
        s = line.strip()
        if s == "{":
            stack.append(pending or "")
            continue
        if s == "}":
            if stack:
                stack.pop()
            continue
        words = re.findall(r'"([^"]*)"', s)
        if len(words) == 1:
            pending = words[0]  # a block name; its "{" is on the next line
        elif len(words) == 2:
            key, value = words
            if stack == ["AppState"] and key == "buildid":
                out["game_buildid"] = value
            elif stack == ["AppState", "MountedConfig"] and key == "BetaKey" and value:
                out["game_branch"] = value
    return out


def verify_sha256(path: Path, expected: str) -> None:
    got = hashlib.sha256(path.read_bytes()).hexdigest()
    if got != expected:
        raise BuildRefused(f"{path.name}: SHA-256 {got} does not match the pinned {expected}")


# ---- the build (I/O) -------------------------------------------------------------
def fetch_release(dest: Path) -> dict[str, Path]:
    dest.mkdir(parents=True, exist_ok=True)
    out = {}
    for asset, sha in MBINCOMPILER_ASSETS.items():
        path = dest / asset
        if not path.exists():
            urllib.request.urlretrieve(RELEASE_URL.format(tag=MBINCOMPILER_TAG, asset=asset), path)
        verify_sha256(path, sha)
        out[asset] = path
    return out


def extraction_filters() -> list[str]:
    return ([f"*REALITY/TABLES/{t}.mbin" for t in [*TABLES, BASE_PART_TABLE]]
            + ["*LANGUAGE/nms_*_english.mbin"])


def extract(game: Path, work: Path, mbincompiler: Path) -> Path:
    banks, out = work / "banks", work / "extracted"
    shutil.rmtree(banks, ignore_errors=True)
    shutil.rmtree(out, ignore_errors=True)
    banks.mkdir(parents=True)
    for pak in PAKS:
        shutil.copy2(game / "GAMEDATA" / "PCBANKS" / pak, banks / pak)  # the install is only read
    cmd = ["uvx", "-q", "--from", HGPAKTOOL, "hgpaktool", "-U", "-O", str(out)]
    for f in extraction_filters():
        cmd += ["-f", f]
    subprocess.run(cmd + [str(banks / p) for p in PAKS], check=True)
    shutil.rmtree(banks)
    run = subprocess.run([str(mbincompiler), "convert", "-y", str(out)],  # no -q: the gate reads the output
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(run.stdout.strip())
    check_convert_output(run.stdout + run.stderr)
    if run.returncode:
        raise BuildRefused(f"MBINCompiler exited {run.returncode}: {run.stderr.strip()[:500]}")
    return out


def local_save_versions() -> list[int]:
    """Root `Version` of every save in every account under the NMS save root."""
    sys.path.insert(0, str(IMPLANT))
    from nmslib import decode, locate

    root = locate.default_root()
    env = locate.env_save_path()
    if env and Path(env).expanduser().is_dir():
        root = Path(env).expanduser()
    versions = []
    for sf in locate.all_saves(root):
        try:
            versions.append(int(decode.read_save(sf.path).get("Version") or 0))
        except Exception as e:  # one unreadable save must not stop the build
            print(f"skipped {sf.path.name}: {e}", file=sys.stderr)
    return [v for v in versions if v]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--game", type=Path, default=DEFAULT_GAME, help="No Man's Sky install dir")
    ap.add_argument("--work", type=Path, required=True, help="scratch dir for the release, PAK copies and MXML")
    a = ap.parse_args(argv)
    items_path, mapping_path, parts_path = DATA / "items.json", DATA / "mapping.json", DATA / "base_parts.json"
    try:
        release = fetch_release(a.work / MBINCOMPILER_TAG)
        mxml = extract(a.game, a.work, release["MBINCompiler.exe"])
        fresh, stats = parse(mxml)
        items = merge(json.loads(items_path.read_text("utf-8"))["items"], fresh)
        fresh_parts = parse_base_parts(mxml)
        parts = merge_base_parts(json.loads(parts_path.read_text("utf-8"))["parts"] if parts_path.exists() else {},
                                 fresh_parts)
        report = json.loads(release["report.json"].read_text("utf-8"))
        mapping = overlay_mapping(json.loads(mapping_path.read_text("utf-8")),
                                  json.loads(release["mapping.json"].read_text("utf-8")),
                                  MBINCOMPILER_TAG, MBINCOMPILER_ASSETS["mapping.json"])
        manifest = a.game.parent.parent / "appmanifest_275850.acf"
        snapshot = {
            "built": date.today().isoformat(),
            "source": "game PAKs via hgpaktool + MBINCompiler",
            "mbincompiler_tag": MBINCOMPILER_TAG,
            "mbincompiler_sha256": MBINCOMPILER_ASSETS["MBINCompiler.exe"],
            "libmbin_version": mapping["libMBIN_version"],
            "tested_buildid": report.get("version"),
            **installed_build(manifest.read_text("utf-8") if manifest.exists() else ""),
            "save_base_version": save_base_version(local_save_versions()),
            "count": len(items),
            "kept_stale": len(items) - len(fresh),
            **stats,
        }
        parts_snapshot = {**{k: snapshot[k] for k in ("built", "source", "mbincompiler_tag", "mbincompiler_sha256")},
                          "table": BASE_PART_TABLE, "count": len(parts), "kept": len(parts) - len(fresh_parts)}
    except BuildRefused as e:
        print(f"refusing to write: {e}", file=sys.stderr)
        return 1
    items_path.write_text(json.dumps({"snapshot": snapshot, "items": items}, indent=0, ensure_ascii=False)
                          + "\n", "utf-8")
    parts_path.write_text(json.dumps({"snapshot": parts_snapshot, "parts": parts}, indent=0, ensure_ascii=False)
                          + "\n", "utf-8")
    mapping_path.write_text(json.dumps(mapping, indent=0, ensure_ascii=False) + "\n", "utf-8")
    print(f"wrote {len(items)} items ({len(fresh)} fresh, {snapshot['kept_stale']} kept stale), "
          f"{len(parts)} base parts and {len(mapping['keys'])} keys from {MBINCOMPILER_TAG}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
