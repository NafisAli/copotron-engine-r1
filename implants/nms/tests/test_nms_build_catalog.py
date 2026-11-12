"""The dev-time snapshot build (tools/build_catalog.py), without the game or MBINCompiler."""

import importlib.util
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parents[1] / "tools" / "build_catalog.py"
_spec = importlib.util.spec_from_file_location("build_catalog", TOOL)
bc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bc)


# ---- key mapping ---------------------------------------------------------------
def test_release_mapping_is_laid_over_the_merged_mapping_without_dropping_keys():
    merged = {"libMBIN_version": "6.11.0.1", "keys": {"F2P": "Version", "bQN": "ActiveSpaceBattleLevel",
                                                      "old": "LegacyOnly"},
              "fixups": {"MultiTools": "Multitools"}}
    release = {"libMBIN_version": "7.10.0.1", "Mapping": [
        {"Key": "F2P", "Value": "Version"}, {"Key": "new", "Value": "AddedIn710"},
        {"Key": "old", "Value": "RenamedUpstream"}]}
    out = bc.overlay_mapping(merged, release, tag="v7.10.0-pre1", sha256="ab" * 32)
    assert out["keys"] == {"F2P": "Version", "bQN": "ActiveSpaceBattleLevel",  # kept: removed upstream
                           "old": "RenamedUpstream",  # the release wins
                           "new": "AddedIn710"}
    assert out["fixups"] == {"MultiTools": "Multitools"}
    assert out["libMBIN_version"] == "7.10.0.1"
    assert (out["mbincompiler_tag"], out["mapping_sha256"]) == ("v7.10.0-pre1", "ab" * 32)


# ---- MBINCompiler gate -----------------------------------------------------------
def test_a_mismatched_compiler_warning_refuses_the_write():
    ok = "Converting nms_reality_gcproducttable.MBIN\nConverted 2 files\n"
    bc.check_convert_output(ok)  # no exception
    bad = ("Converting nms_reality_gcsubstancetable.MBIN\n"
           "[WARN]: nms_reality_gcsubstancetable.MBIN: File not recognized. "
           "You may need to use an older (or newer) version of MBINCompiler\n")
    with pytest.raises(bc.BuildRefused, match="nms_reality_gcsubstancetable"):
        bc.check_convert_output(bad)


# ---- catalog tables ---------------------------------------------------------------
def write_table(root: Path, stem: str, rows: list[tuple[str, str]]) -> None:
    """MXML shaped like MBINCompiler 7.10's GcProductTable output: (ID, NameLower key)."""
    body = "".join(
        f'\t\t<Property name="Table" value="GcProductData" _id="{i}">\n'
        f'\t\t\t<Property name="ID" value="{i}" />\n'
        f'\t\t\t<Property name="Name" value="{k.removesuffix("_L")}" />\n'
        f'\t\t\t<Property name="NameLower" value="{k}" />\n\t\t</Property>\n' for i, k in rows)
    path = root / "metadata" / "reality" / "tables" / f"{stem}.MXML"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('<?xml version="1.0" encoding="utf-8"?>\n'
                    "<!--File created using MBINCompiler version (7.10.0.1)-->\n"
                    f'<Data template="cGcProductTable">\n\t<Property name="Table">\n{body}\t</Property>\n</Data>\n',
                    encoding="utf-8")


def write_locale(root: Path, entries: dict[str, str]) -> None:
    body = "".join(
        f'\t\t<Property name="Table" value="TkLocalisationEntry" _id="{k}">\n'
        f'\t\t\t<Property name="Id" value="{k}" />\n'
        f'\t\t\t<Property name="English" value="{v}" />\n\t\t</Property>\n' for k, v in entries.items())
    path = root / "language" / "nms_loc1_english.MXML"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'<?xml version="1.0" encoding="utf-8"?>\n<Data template="cTkLocalisationTable">\n'
                    f'\t<Property name="Table">\n{body}\t</Property>\n</Data>\n', encoding="utf-8")


@pytest.fixture
def mxml(tmp_path):
    rows = {
        "nms_reality_gcsubstancetable": [("YELLOW2", "UI_YELLOW2_L")],
        "nms_reality_gcproducttable": [("CASING", "UI_CASING_L")],
        "nms_reality_gctechnologytable": [("HYPERDRIVE", "UI_HYPER_L")],
        "nms_reality_gcproceduraltechnologytable": [("UP_SHLD4", "UI_SHLD_L")],
        "nms_basepartproducts": [("BUILD_REFINER1", "UI_REFINER_L"), ("B_MAG_1X1", "UI_NOWHERE_L")],
        "nms_modularcustomisationproducts": [("FOS_HEAD_BH", "UI_SKULL_L")],
    }
    for stem, r in rows.items():
        write_table(tmp_path, stem, r)
    write_locale(tmp_path, {"UI_YELLOW2_L": "Copper", "UI_CASING_L": "Casing", "UI_HYPER_L": "Hyperdrive",
                            "UI_SHLD_L": "Shield Upgrade", "UI_REFINER_L": "&lt;STELLAR&gt;Medium Refiner&lt;&gt;",
                            "UI_SKULL_L": "Ancient Skull"})
    return tmp_path


def test_catalog_names_products_base_parts_and_modular_parts(mxml):
    items, stats = bc.parse(mxml)
    assert items == {
        "YELLOW2": {"name": "Copper"}, "CASING": {"name": "Casing"}, "HYPERDRIVE": {"name": "Hyperdrive"},
        "UP_SHLD4": {"name": "Shield Upgrade"},
        "BUILD_REFINER1": {"name": "Medium Refiner"},  # markup stripped
        "FOS_HEAD_BH": {"name": "Ancient Skull"},
    }  # B_MAG_1X1 has no English name: left out, never guessed
    assert stats["tables"]["nms_basepartproducts"] == 1


def test_a_missing_table_refuses_the_write(mxml):
    next(mxml.rglob("nms_modularcustomisationproducts.MXML")).unlink()
    with pytest.raises(bc.BuildRefused, match="nms_modularcustomisationproducts"):
        bc.parse(mxml)


# ---- merge and provenance -----------------------------------------------------------
def test_ids_missing_from_a_new_build_are_kept_as_stale():
    old = {"A": {"name": "Alpha"}, "GONE": {"name": "Gone"}, "BACK": {"name": "Back", "stale": True}}
    fresh = {"A": {"name": "Alpha Prime"}, "BACK": {"name": "Back"}, **{f"N{i}": {"name": "n"} for i in range(5)}}
    merged = bc.merge(old, fresh)
    assert merged["A"] == {"name": "Alpha Prime"}
    assert merged["GONE"] == {"name": "Gone", "stale": True}
    assert merged["BACK"] == {"name": "Back"}


def test_a_build_that_shrinks_by_more_than_a_tenth_is_refused():
    old = {f"I{i}": {"name": "x"} for i in range(100)}
    bc.merge(old, {f"I{i}": {"name": "x"} for i in range(90)})  # exactly 10% fewer: allowed
    with pytest.raises(bc.BuildRefused, match="89"):
        bc.merge(old, {f"I{i}": {"name": "x"} for i in range(89)})


def test_save_base_version_is_the_highest_version_mod_512():
    # 4746 = base 138 (Normal, Nov 2026); 4616 = Feb 2018; 5762 = base 130 in another game mode
    assert bc.save_base_version([4616, 4746, 4738 + 2 * 512]) == 138
    with pytest.raises(bc.BuildRefused):
        bc.save_base_version([])


MANIFEST = '''"AppState"
{
\t"appid"\t\t"275850"
\t"buildid"\t\t"26463810"
\t"MountedConfig"
\t{
\t\t"language"\t\t"english"
\t\t"BetaKey"\t\t"experimental"
\t}
\t"PrivateDepots"
\t{
\t\t"branches"
\t\t{
\t\t\t"experimental"
\t\t\t{
\t\t\t\t"buildid"\t\t"26540378"
\t\t\t}
\t\t}
\t}
}
'''


def test_installed_build_is_read_from_the_steam_manifest_not_the_newer_branch_build():
    assert bc.installed_build(MANIFEST) == {"game_buildid": "26463810", "game_branch": "experimental"}
    public = MANIFEST.replace('\t\t"BetaKey"\t\t"experimental"\n', "")
    assert bc.installed_build(public)["game_branch"] == "public"


def test_a_download_that_does_not_match_its_pinned_hash_is_refused(tmp_path):
    f = tmp_path / "mapping.json"
    f.write_bytes(b"{}")
    bc.verify_sha256(f, "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a")
    with pytest.raises(bc.BuildRefused, match="mapping.json"):
        bc.verify_sha256(f, "0" * 64)
