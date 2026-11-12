"""Save decoding, the extracted model, and the pinned --json schemas."""

import json
import struct

import nms
import pytest
from conftest import UID, save_doc, slot, write_save
from nmslib import decode, extract


@pytest.fixture
def save_path(nms_root):
    return write_save(nms_root / "save3.hg", save_doc(), 1000)


def run(capsys, *argv):
    code = nms.main([*argv, "--json"])
    out = capsys.readouterr()
    return code, (json.loads(out.out) if out.out else None), out.err


# ---- decode ------------------------------------------------------------------
def test_plaintext_with_nul_padding_passes_through():
    assert decode.decode_bytes(b'{"Version": 1}\0\0\0') == {"Version": 1}


def test_obfuscated_keys_are_mapped():
    keys, _ = decode._mapping()
    obf = {v: k for k, v in keys.items()}
    doc = {"F2P": 1, obf["ActiveContext"]: "Main"}
    assert decode.decode_bytes(json.dumps(doc).encode())["ActiveContext"] == "Main"


def test_obfuscated_keys_resolve_through_objects_lists_and_fixups():
    keys, fixups = decode._mapping()
    obf = {fixups.get(v, v): k for k, v in keys.items()}
    doc = {"F2P": 4746, obf["BaseContext"]: {obf["PlayerStateData"]: {
        obf["Multitools"]: [{obf["Name"]: "Lance"}], "unmapped": 1}}}
    root = decode.decode_bytes(json.dumps(doc).encode())
    ps = root["BaseContext"]["PlayerStateData"]
    assert root["Version"] == 4746
    assert ps["Multitools"][0]["Name"] == "Lance"  # MultiTools fixup applied
    assert ps.get("unmapped") == 1 and ps.get("Units") is None and "Multitools" in ps


def test_a_key_hashed_to_two_names_is_read_by_either_name():
    keys, _ = decode._mapping()
    obf = {v: k for k, v in keys.items()}
    doc = {"F2P": 4746, obf["PlayerStateData"]: {"V86": {obf["Slots"]: [7]}, "NE3": 200},
           "attrs": {"NE3": True}}
    root = decode.decode_bytes(json.dumps(doc).encode())
    ps = root["PlayerStateData"]
    assert ps["RocketLockerInventory"]["Slots"][0] == 7  # V86 is not FireteamSessionCount here
    assert ps["ShipShield"] == 200 and root["attrs"]["AllowedToBePurpleWithoutAccess"] is True


def test_lz4_blocks_decode():
    lz4 = pytest.importorskip("lz4.block")
    body = json.dumps({"Version": 1, "pad": "x" * 0x90000}).encode()
    raw = b""
    for i in range(0, len(body), 0x80000):
        chunk = lz4.compress(body[i:i + 0x80000], store_size=False)
        raw += struct.pack("<IIII", decode.BLOCK_MAGIC, len(chunk), len(body[i:i + 0x80000]), 0) + chunk
    assert decode.decode_bytes(raw)["Version"] == 1


def test_bad_magic_is_a_decode_error():
    pytest.importorskip("lz4.block")
    with pytest.raises(decode.SaveDecodeError, match="magic"):
        decode.decode_bytes(b"\x00" * 16)


# ---- model -------------------------------------------------------------------
def test_model_from_main_context(save_path):
    s = extract.load_path(save_path)
    p = s.player
    assert p.uid == UID and p.context == "main" and p.game_mode == "Survival"
    assert p.units == 0xFFFFFFFF and p.previous_location is None
    assert p.current_ship.name == "Boundary Herald" and p.current_ship.kind == "Fighter"
    assert [sh.kind for sh in p.ships] == ["Shuttle", "Fighter"]  # empty ownership slot skipped

    suit = next(c for c in s.containers if c.category == "suit" and c.grid == "general")
    assert suit.capacity == 26  # unlocked slots, not 10x12
    assert [x.id for x in suit.slots] == ["YELLOW2", "YELLOW2", "FUEL1", "NOT_A_REAL_ITEM"]  # MAINT_ dropped
    assert suit.slots[3].name is None  # unknown ids are never guessed
    assert not any(c.owner == "Exosuit" and c.grid == "cargo" for c in s.containers)  # empty legacy grid
    assert [c.owner for c in s.containers if c.category == "storage"] == ["Storage 3"]
    # only exocraft holding cargo count; every exocraft carries default tech
    assert [c.label for c in s.containers if c.category == "exocraft"] == ["Nautilon", "Nautilon (tech)"]

    assert [(b.name, b.is_mine) for b in s.bases] == [("Home", True), ("Visited", False)]
    system = s.system_at(p.location)
    assert system.name == "Testoria" and system.is_mine
    assert [(pl.index, pl.biome, pl.infested, pl.name) for pl in system.planets] == [
        (2, "Scorched", False, None), (3, "Radioactive", True, "Glowball")]


def test_single_grids_are_their_own_categories(nms_root, capsys):
    grid = lambda *slots: {"ValidSlotIndices": [{}] * 50, "Slots": list(slots)}  # noqa: E731
    doc = save_doc(
        CookingIngredientsInventory=grid(slot("^YELLOW2", 5, 500)),
        GraveInventory=grid(slot("^FUEL1", 20, 500)),
        ChestMagicInventory=grid(slot("^OXYGEN", 1, 500)),
        ChestMagic2Inventory=grid(slot("^OXYGEN", 2, 500)),
        FoodUnitInventory=grid(),  # empty: hidden
        PersonalMaintenanceInteractions=[{"InventoryContainer": grid(slot("^MAINT_TECH3", 50, 50))}],
    )
    s = extract.load_path(write_save(nms_root / "save.hg", doc, 1000))
    cats = [(c.category, c.label) for c in s.containers if c.category not in
            ("suit", "ship", "multitool", "storage", "exocraft")]
    assert cats == [("ingredients", "Ingredient Storage"), ("grave", "Grave (dropped on death)"),
                    ("chest-magic", "ChestMagic"), ("chest-magic", "ChestMagic2")]
    assert not any(c.category == "refiner" for c in s.containers)
    assert [c.owner for c in s.containers if c.category == "storage"] == ["Storage 3"]

    _, d, _ = run(capsys, "inventory", "--have", "Copper:659", "--save", str(nms_root / "save.hg"))
    assert d["requirements"][0]["have"] == 664  # ingredients count toward requisitions
    _, d, _ = run(capsys, "inventory", "chest-magic", "--save", str(nms_root / "save.hg"))
    assert [c["owner"] for c in d["containers"]] == ["ChestMagic", "ChestMagic2"]


def test_catalog_names_carried_base_parts_and_modular_parts(nms_root, capsys):
    chest = {"ValidSlotIndices": [{}] * 50, "Slots": [
        slot("^BUILD_REFINER1", 1, 5, "Product"), slot("^FOS_HEAD_BH", 1, 1, "Product")]}
    path = write_save(nms_root / "save.hg", save_doc(Chest1Inventory=chest), 1000)
    _, d, _ = run(capsys, "inventory", "storage", "--name", "Storage 0", "--save", str(path))
    assert [(i["id"], i["name"]) for i in d["containers"][0]["items"]] == [
        ("BUILD_REFINER1", "Portable Refiner"), ("FOS_HEAD_BH", "Longhorn Skull")]


def test_refiner_is_not_a_category(save_path, capsys):
    with pytest.raises(SystemExit) as e:
        nms.main(["inventory", "refiner"])
    assert e.value.code == 2


def test_expedition_context_is_read(nms_root):
    path = write_save(nms_root / "save.hg", save_doc(context="Season"), 1000)
    assert extract.load_path(path).player.context == "expedition"


def test_pre_context_layout_is_read(nms_root):
    doc = save_doc()
    legacy = {"Version": 4616, "PlayerStateData": doc["BaseContext"]["PlayerStateData"],
              "DiscoveryManagerData": doc["DiscoveryManagerData"]}
    s = extract.load_path(write_save(nms_root / "save.hg", legacy, 1000))
    assert s.player.context == "main" and s.player.game_mode == "Survival"


def test_bad_base_address_is_a_warning_not_a_crash(nms_root):
    doc = save_doc()
    doc["BaseContext"]["PlayerStateData"]["PersistentPlayerBases"][1]["GalacticAddress"] = "0xZZ"
    s = extract.load_path(write_save(nms_root / "save.hg", doc, 1000))
    assert len(s.bases) == 1 and s.warnings


# ---- --json schemas ----------------------------------------------------------
SAVE_KEYS = {"path", "account", "account_kind", "slot", "kind", "modified", "version", "save_name"}
ADDRESS_KEYS = {"galaxy", "galaxy_name", "glyphs", "glyph_emoji", "signal_booster", "galactic_address",
                "voxel", "system_index", "planet_index"}


def test_status_schema(save_path, capsys):
    code, d, _ = run(capsys, "status")
    assert code == 0
    assert set(d) == {"schema", "save", "context", "game_mode", "play_time_s", "summary", "location",
                      "currencies", "current_ship", "warnings", "notes"}
    assert d["schema"] == "nms.status/1" and d["notes"] == []
    assert set(d["save"]) == SAVE_KEYS
    assert set(d["location"]) == ADDRESS_KEYS | {"system_name", "planet_name", "planet_biome",
                                                 "distance_to_core_ly"}
    assert d["location"]["galaxy_name"] == "Eissentam" and d["location"]["system_name"] == "Testoria"
    assert set(d["currencies"]) == {"units", "nanites", "quicksilver"}
    assert d["current_ship"] == {"name": "Boundary Herald", "kind": "Fighter", "class": "B", "index": 1}


def test_inventory_summary_schema(save_path, capsys):
    code, d, _ = run(capsys, "inventory")
    assert code == 0 and d["mode"] == "summary"
    assert set(d) == {"schema", "save", "catalog", "mode", "containers", "notes"} and d["notes"] == []
    row = d["containers"][0]
    assert set(row) == {"category", "owner", "grid", "is_current", "capacity", "used", "at_cap"}
    assert (row["owner"], row["used"], row["capacity"], row["at_cap"]) == ("Exosuit", 4, 26, 1)


def test_inventory_category_schema(save_path, capsys):
    _, d, _ = run(capsys, "inventory", "ships")
    assert [c["owner"] for c in d["containers"] if c["grid"] == "general"] == ["Shuttle #0", "Boundary Herald"]
    item = d["containers"][0]["items"][0]
    assert set(item) == {"id", "name", "amount", "max_amount", "type", "at_cap", "damage_factor",
                         "fully_installed", "x", "y"}
    _, d, _ = run(capsys, "inventory", "ship")
    assert {c["owner"] for c in d["containers"]} == {"Boundary Herald"}


def test_inventory_search_totals_per_item(save_path, capsys):
    _, d, _ = run(capsys, "inventory", "--search", "copper")
    assert d["items"] == [{"ids": ["YELLOW2"], "name": "Copper", "type": "Substance", "total": 659,
                           "locations": {"Exosuit": 643, "Storage 3": 9, "Shuttle #0": 7}}]


def test_inventory_have_exit_code(save_path, capsys):
    code, d, _ = run(capsys, "inventory", "--have", "Copper:600", "FUEL1:400")
    assert code == 0 and d["all_met"]
    code, d, _ = run(capsys, "inventory", "--have", "Copper:700")
    assert code == 1 and d["requirements"][0]["short"] == 41
    assert set(d["requirements"][0]) == {"query", "ids", "name", "need", "have", "met", "short", "locations"}


# ---- name groups: every id sharing a name counts as that item (#25) ------------
@pytest.fixture
def group_save(nms_root):
    # Hyperdrive is a name shared by 9 catalog ids (ship tech, corvette part, upgrade modules).
    chest = {"ValidSlotIndices": [{}] * 50, "Slots": [
        slot("^HYPERDRIVE", 1, 1, "Technology"), slot("^CV_HYP2", 2, 5, "Product"),
        slot("^UP_HYP1#4242", 1, 1, "Product"), slot("^CHEST", 3, 10, "Product")]}
    return write_save(nms_root / "save.hg", save_doc(Chest1Inventory=chest), 1000)


def test_have_by_name_totals_every_id_that_shares_the_name(group_save, capsys):
    code, d, _ = run(capsys, "inventory", "--have", "Hyperdrive:4")
    r = d["requirements"][0]
    assert code == 0 and (r["have"], r["name"]) == (4, "Hyperdrive")
    assert r["ids"] == ["CV_HYP2", "CV_HYP3", "HYPERDRIVE", "UP_HYP0", "UP_HYP1", "UP_HYP2", "UP_HYP3",
                        "UP_HYP4", "UP_HYPX"]
    assert r["locations"] == {"Storage 0": 4}


def test_have_by_exact_id_counts_only_that_id(group_save, capsys):
    _, d, _ = run(capsys, "inventory", "--have", "HYPERDRIVE:1", "UP_HYP1:1", "fuel1:1")
    assert [(r["ids"], r["have"]) for r in d["requirements"]] == [
        (["HYPERDRIVE"], 1),  # upper-case is the id; "Hyperdrive" is the name group
        (["UP_HYP1"], 1),  # a seeded stack (UP_HYP1#4242) counts toward its base id
        (["FUEL1"], 465)]  # an id in any case, when no name matches (Exosuit 460 + Nautilon 5)


def test_a_substring_is_ambiguous_only_across_distinct_names(group_save, capsys):
    _, d, _ = run(capsys, "inventory", "--have", "storage contain:3")  # 11 ids, one name
    r = d["requirements"][0]
    assert (r["name"], r["have"], len(r["ids"])) == ("Storage Container", 3, 11)
    code, d, err = run(capsys, "inventory", "--have", "hyperdr:1")
    assert code == 2 and "ambiguous" in err and "Freighter Hyperdrive" in err


def test_search_totals_one_row_per_name(group_save, capsys):
    _, d, _ = run(capsys, "inventory", "--search", "hyperdrive")
    assert d["items"] == [{"ids": ["CV_HYP2", "HYPERDRIVE", "UP_HYP1#4242"], "name": "Hyperdrive",
                           "type": "Mixed", "total": 4, "locations": {"Storage 0": 4}}]
    assert nms.main(["inventory", "--search", "r", "--save", str(group_save)]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert "Hyperdrive ×4 (Storage 0 4)  [CV_HYP2, HYPERDRIVE, UP_HYP1#4242]" in lines
    assert "Copper ×659 (Exosuit 643, Storage 3 9, Shuttle #0 7)" in lines  # one id: none shown


def test_every_inventory_mode_carries_the_inventory_schema_and_notes(save_path, capsys):
    for argv in (["inventory"], ["inventory", "suit"], ["inventory", "--search", "copper"],
                 ["inventory", "--have", "Copper:1"]):
        d = run(capsys, *argv)[1]
        assert d["schema"] == "nms.inventory/1" and d["notes"] == []


def test_inventory_filters(save_path, capsys):
    _, d, _ = run(capsys, "inventory", "suit", "--tech")
    assert [i["id"] for c in d["containers"] for i in c["items"]] == ["JET1"]
    _, d, _ = run(capsys, "inventory", "suit", "--near-cap")
    assert [i["id"] for c in d["containers"] for i in c["items"]] == ["YELLOW2", "FUEL1"]


def test_bases_schema(save_path, capsys):
    _, d, _ = run(capsys, "bases")
    assert set(d) == {"schema", "save", "scope", "bases", "notes"} and d["notes"] == []
    assert d["scope"] == "mine" and [b["name"] for b in d["bases"]] == ["Home"]
    assert set(d["bases"][0]) == {"name", "kind", "address", "owner_uid", "owner_name", "is_mine",
                                  "last_update", "object_count", "distance_ly"}
    assert d["bases"][0]["distance_ly"] is None  # base in Euclid, player in Eissentam
    _, d, _ = run(capsys, "bases", "--all")
    assert len(d["bases"]) == 2
    _, d, _ = run(capsys, "bases", "home")
    assert set(d) == {"schema", "save", "base", "notes"} and d["schema"] == "nms.bases/1"
    assert d["base"]["name"] == "Home"


def test_convert_schema(capsys):
    code, d, _ = run(capsys, "convert", "0EA4:007D:05BD:005F", "--galaxy", "Eissentam", "--planet", "1")
    assert code == 0
    assert set(d) == ADDRESS_KEYS | {"schema", "input", "distance_to_core_ly", "is_black_hole",
                                     "is_atlas_interface", "notes"}
    assert d["notes"] == []  # convert reads no Save, so it never carries a note
    assert d["schema"] == "nms.convert/1"
    assert (d["glyphs"], d["galaxy"]) == ("105FFEDBE6A5", 9)


def test_saves_schema(save_path, capsys):
    _, d, _ = run(capsys, "saves")
    assert set(d) == {"schema", "root", "nms_save_path", "selected", "accounts", "notes"}
    assert d["schema"] == "nms.saves/1" and d["notes"] == []
    slot = d["accounts"][0]["slots"][0]
    assert set(slot) == {"slot", "manual", "auto", "newest", "selected", "mode", "context",
                         "play_time_s", "summary"}
    assert slot["slot"] == 2 and slot["selected"] and slot["mode"] == "Survival"


def test_bench_reports_timings_and_counts(save_path, capsys):
    code, d, _ = run(capsys, "bench")
    assert code == 0
    assert {"import", "read", "decode", "extract", "total_in_process"} <= set(d["timings_ms"])
    assert d["counts"]["slots"] > 0 and d["obfuscated"] is False


def test_errors_go_to_stderr_with_exit_2(nms_root, capsys):
    code, d, err = run(capsys, "status")  # no saves in the account folder
    assert code == 2 and d is None and err.startswith("nms: ")
    code, d, err = run(capsys, "find", "lush")
    assert code == 2 and "#14" in err
