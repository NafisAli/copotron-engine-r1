"""Save decoding, the extracted model, and the pinned --json schemas."""

import json
import struct

import nms
import pytest
from conftest import UID, base, refiner_state, save_doc, slot, write_save
from nmslib import catalog, decode, extract


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
                    ("salvage", "Base Salvage Capsule")]  # ChestMagic2's purpose is unknown: not read
    assert not any(c.category == "refiner" for c in s.containers)
    assert [c.owner for c in s.containers if c.category == "storage"] == ["Storage 3"]

    _, d, _ = run(capsys, "inventory", "--have", "Copper:659", "Oxygen:1", "--save", str(nms_root / "save.hg"))
    assert d["requirements"][0]["have"] == 664  # ingredients count toward requisitions
    assert d["requirements"][1]["locations"] == {"Base Salvage Capsule": 1}  # and so does salvage
    _, d, _ = run(capsys, "inventory", "salvage", "--save", str(nms_root / "save.hg"))
    assert [c["owner"] for c in d["containers"]] == ["Base Salvage Capsule"]
    with pytest.raises(SystemExit) as e:
        nms.main(["inventory", "chest-magic"])
    assert e.value.code == 2


# ---- storage chests: shown when built or holding items (#28) --------------------
@pytest.fixture
def chest_save(nms_root):
    def parts(*ids):
        return [{"ObjectID": f"^{i}", "Position": [0.0, 0.0, 0.0]} for i in ids]
    home = base("Home", "HomePlanetBase", "0x40050003AB8C07", UID)
    home["Objects"] = parts("BASE_FLAG", "CONTAINER0")
    freighter = base("Freighter", "FreighterBase", "0x40050003AB8C07", UID)
    freighter["Objects"] = parts("FRE_ROOM_STORE2")  # the Storage Room shares chest 2's inventory
    legacy = base("Old", None, "0x40050003AB8C07", "")
    del legacy["BaseType"]
    legacy["Objects"] = parts("S_CONTAINER7")
    visited = base("Visited", "ExternalPlanetBase", "0x40050003AB8C07", "999")
    visited["Objects"] = parts("CONTAINER5")  # another player's chest builds nothing of ours
    # Real saves allocate all ten grids. Chest4Inventory (Storage 3) holds Copper, with no container built.
    grids = {f"Chest{n}Inventory": {"ValidSlotIndices": [{}] * 50, "Slots": []} for n in (1, 2, 3, 6, 7, 8, 9, 10)}
    return write_save(nms_root / "save.hg",
                      save_doc(PersistentPlayerBases=[home, freighter, legacy, visited], **grids), 1000)


def test_a_storage_chest_is_shown_when_built_or_holding_items(chest_save):
    s = extract.load_path(chest_save)
    assert [(c.owner, c.built, len(c.slots)) for c in s.containers if c.category == "storage"] == [
        ("Storage 0", True, 0), ("Storage 2", True, 0), ("Storage 3", False, 1), ("Storage 7", True, 0)]


def test_storage_json_carries_built_and_text_marks_an_unbuilt_chest(chest_save, capsys):
    _, d, _ = run(capsys, "inventory", "storage")
    assert [(c["owner"], c["built"]) for c in d["containers"]] == [
        ("Storage 0", True), ("Storage 2", True), ("Storage 3", False), ("Storage 7", True)]
    _, d, _ = run(capsys, "inventory")
    assert set(next(c for c in d["containers"] if c["category"] == "storage")) == {
        "category", "owner", "grid", "is_current", "capacity", "used", "at_cap", "built"}
    assert nms.main(["inventory", "storage", "--save", str(chest_save)]) == 0
    out = capsys.readouterr().out.splitlines()
    assert "Storage 3 (no container built) — 1/50" in out and "Storage 0 — 0/50" in out


# ---- exocraft: shown when deployed or holding cargo (#28) ------------------------
@pytest.fixture
def exocraft_save(nms_root):
    def craft(location, *general, name=""):
        return {"Name": name, "Location": location,
                "Inventory": {"ValidSlotIndices": [{}] * 40, "Slots": list(general)},
                "Inventory_TechOnly": {"ValidSlotIndices": [{}] * 28,
                                       "Slots": [slot("^VEHICLE_ENGINE", 1, 1, "Technology")]}}
    tech = slot("^VEHICLE_LASER", 1, 1, "Technology")  # default tech sits in legacy general grids
    vehicles = [
        craft("0x209E00FF958E2E"),  # Roamer: deployed (geobay address) and empty
        craft(4523395107528624, name="Zippy"),  # Nomad: deployed, renamed
        craft(0, tech),  # Colossus: never deployed, default tech only
        craft("0x0"),  # Pilgrim: never deployed, empty
        craft(0, slot("^FUEL1", 5, 250)),  # Dragonfly: can't be deployed, but cargo was left in it
        craft(0), craft(0),
    ]
    return write_save(nms_root / "save.hg", save_doc(VehicleOwnership=vehicles), 1000)


def test_an_exocraft_is_shown_when_deployed_or_holding_cargo(exocraft_save):
    s = extract.load_path(exocraft_save)
    shown = [(c.owner, c.exocraft_type, c.deployed) for c in s.containers
             if c.category == "exocraft" and c.grid == "general"]
    assert shown == [("Roamer", "Roamer", True), ("Zippy (Nomad)", "Nomad", True),
                     ("Dragonfly", "Dragonfly", False)]


def test_exocraft_json_carries_type_and_deployed_and_text_marks_undeployed(exocraft_save, capsys):
    _, d, _ = run(capsys, "inventory", "exocraft")
    general = [c for c in d["containers"] if c["grid"] == "general"]
    assert [(c["owner"], c["type"], c["deployed"]) for c in general] == [
        ("Roamer", "Roamer", True), ("Zippy (Nomad)", "Nomad", True), ("Dragonfly", "Dragonfly", False)]
    assert set(general[0]) == {"category", "owner", "grid", "is_current", "capacity", "used", "at_cap",
                               "type", "deployed", "items"}
    assert nms.main(["inventory", "--save", str(exocraft_save)]) == 0
    rows = [r for r in capsys.readouterr().out.splitlines() if r.startswith("exocraft")]
    assert any("Dragonfly (not deployed)" in r for r in rows)
    assert not any("not deployed" in r for r in rows if "Roamer" in r or "Zippy" in r)


def test_catalog_names_carried_base_parts_and_modular_parts(nms_root, capsys):
    chest = {"ValidSlotIndices": [{}] * 50, "Slots": [
        slot("^BUILD_REFINER1", 1, 5, "Product"), slot("^FOS_HEAD_BH", 1, 1, "Product")]}
    path = write_save(nms_root / "save.hg", save_doc(Chest1Inventory=chest), 1000)
    _, d, _ = run(capsys, "inventory", "storage", "--name", "Storage 0", "--save", str(path))
    assert [(i["id"], i["name"]) for i in d["containers"][0]["items"]] == [
        ("BUILD_REFINER1", "Portable Refiner"), ("FOS_HEAD_BH", "Longhorn Skull")]


# ---- the exosuit's Personal Refiner (#22) ---------------------------------------
REFINER_NOTE = ("The save doesn't reveal refiners in bases, on the freighter, in exocraft or on the corvette. "
                "Contents are as of the save; refining continues when the game loads.")


@pytest.fixture
def refiner_save(nms_root):
    working = refiner_state(slot("^MAINT_FUEL1", 40, 100, "Technology", x=0), slot("^SPACEGUNK4", 54, 9999, x=2),
                            slot("^SPACEGUNK2", 150, 9999, x=1))  # list order is not slot order
    return write_save(nms_root / "save.hg", save_doc(**working), 1000)


def test_the_personal_refiner_is_the_entry_keyed_by_the_sentinel(refiner_save):
    s = extract.load_path(refiner_save)
    [r] = [c for c in s.containers if c.category == "refiner"]
    assert (r.owner, r.label, r.fuel_pct) == ("Exosuit", "Personal Refiner", 40)
    assert [(x.name, x.amount, x.role) for x in r.slots] == [("Runaway Mould", 150, "output"),
                                                             ("Living Slime", 54, "input")]  # slot order


def test_an_empty_personal_refiner_is_still_shown(nms_root):
    doc = save_doc(**refiner_state(slot("^MAINT_FUEL1", 8, 100, "Technology"),
                                   slot("^MAINT_REFINER", 0, 100, "Technology", x=1)))
    s = extract.load_path(write_save(nms_root / "save.hg", doc, 1000))
    [r] = [c for c in s.containers if c.category == "refiner"]
    assert (r.fuel_pct, r.slots) == (8, [])


def test_no_sentinel_key_means_no_refiner(nms_root):
    planet = {"GalacticAddress": "0x210300FCA77448", "Value": 1, "Position": [1.0, 1.0, 1.0, 1.0]}
    doc = save_doc(**refiner_state(slot("^MAINT_FUEL1", 54, 100, "Technology"), slot("^LAND1", 448, 9999, x=1),
                                   keys=[planet] * 3))  # fuel plus material, but a planet key: a harvester
    s = extract.load_path(write_save(nms_root / "save.hg", doc, 1000))
    assert not any(c.category == "refiner" for c in s.containers)


def test_inventory_refiner_schema_labels_slots_and_notes_the_unreadable_refiners(refiner_save, capsys):
    code, d, _ = run(capsys, "inventory", "refiner")
    assert code == 0 and d["notes"] == ["Only the exosuit's Personal Refiner can be read. " + REFINER_NOTE]
    [c] = d["containers"]
    assert set(c) == {"category", "owner", "grid", "is_current", "capacity", "used", "at_cap", "name",
                      "fuel_pct", "items"}
    assert (c["owner"], c["name"], c["fuel_pct"]) == ("Exosuit", "Personal Refiner", 40)
    assert [(i["id"], i["role"]) for i in c["items"]] == [("SPACEGUNK2", "output"), ("SPACEGUNK4", "input")]
    assert set(c["items"][0]) == {"id", "name", "amount", "max_amount", "type", "at_cap", "damage_factor",
                                  "fully_installed", "x", "y", "role"}


def test_inventory_refiner_text_shows_fuel_output_and_inputs(refiner_save, capsys):
    assert nms.main(["inventory", "refiner", "--save", str(refiner_save)]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "Personal Refiner — Fuel 40%", "  Output: Runaway Mould ×150", "  Input: Living Slime ×54",
        "Note      Only the exosuit's Personal Refiner can be read. " + REFINER_NOTE]


def test_without_a_personal_refiner_the_note_says_none_is_installed(save_path, capsys):
    _, d, _ = run(capsys, "inventory", "refiner")
    assert d["containers"] == [] and d["notes"] == ["No Personal Refiner installed. " + REFINER_NOTE]


def test_refiner_contents_count_toward_search_and_have_but_fuel_never_does(refiner_save, capsys):
    _, d, _ = run(capsys, "inventory", "--search", "slime")
    assert d["items"][0]["locations"] == {"Personal Refiner": 54}
    code, d, _ = run(capsys, "inventory", "--have", "Runaway Mould:150")
    assert code == 0 and d["requirements"][0]["locations"] == {"Personal Refiner": 150}
    _, d, _ = run(capsys, "inventory")
    assert d["notes"] == []  # the refiner note belongs to `inventory refiner` only
    assert [c["owner"] for c in d["containers"] if c["category"] == "refiner"] == ["Exosuit"]


def test_a_base_is_mine_by_its_base_type_not_its_owner(nms_root):
    legacy = base("Old", None, "0x40050003AB8C07", "")
    del legacy["BaseType"]  # pre-BaseType saves: every persisted base was the player's
    bases = [
        base("Home", "HomePlanetBase", "0x40050003AB8C07", ""),  # legacy bases have an empty owner
        base("Expedition freighter", "FreighterBase", "0x40050003AB8C07", "placeholder"),
        base("Corvette", "PlayerShipBase", "0x40050003AB8C07", UID),
        legacy,
        base("Template", "ExternalPlanetBase", "0x40050003AB8C07", UID),  # an expedition template
        base("Visited", "ExternalPlanetBase", "0x40050003AB8C07", "999"),
    ]
    s = extract.load_path(write_save(nms_root / "save.hg", save_doc(PersistentPlayerBases=bases), 1000))
    assert [b.name for b in s.my_bases] == ["Home", "Expedition freighter", "Corvette", "Old"]


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


# ---- Game Data Snapshot staleness (#26) ----------------------------------------
def stale_doc(ahead=2):
    """A Save whose base version (Version % 512) is `ahead` of the snapshot's."""
    doc = save_doc()
    doc["Version"] = 9 * 512 + catalog.snapshot()["save_base_version"] + ahead
    return doc


def test_a_save_newer_than_the_game_data_adds_one_note_to_every_save_command(nms_root, capsys):
    built = catalog.snapshot()["save_base_version"]
    write_save(nms_root / "save.hg", stale_doc(), 1000)
    note = (f"Game data built for save version {built}; this save is {built + 2}. Some items may show "
            "raw ids and some fields may be missing until the game data is refreshed.")
    for argv in (["status"], ["inventory"], ["inventory", "suit"], ["inventory", "--search", "copper"],
                 ["inventory", "--have", "Copper:1"], ["bases"], ["bases", "home"]):
        assert run(capsys, *argv)[1]["notes"] == [note], argv
    assert run(capsys, "convert", "0EA4:007D:05BD:005F")[1]["notes"] == []  # reads no Save


def test_the_staleness_note_is_the_final_stdout_line_in_text(nms_root, capsys):
    write_save(nms_root / "save.hg", stale_doc(), 1000)
    assert nms.main(["status"]) == 0
    out = capsys.readouterr()
    assert out.out.splitlines()[-1].startswith("Note      Game data built for save version")
    assert out.err == ""


def test_saves_lists_the_slots_ahead_of_the_game_data_unless_quick(nms_root, capsys):
    built = catalog.snapshot()["save_base_version"]
    write_save(nms_root / "save3.hg", stale_doc(), 1000)  # slot 2
    write_save(nms_root / "save9.hg", stale_doc(1), 900)  # slot 5
    write_save(nms_root / "save5.hg", save_doc(), 800)  # slot 3, current
    _, d, _ = run(capsys, "saves")
    assert d["notes"] == [f"Game data built for save version {built}; slots 2, 5 are newer. Some items "
                          "may show raw ids and some fields may be missing until the game data is refreshed."]
    assert run(capsys, "saves", "--quick")[1]["notes"] == []  # decodes nothing
