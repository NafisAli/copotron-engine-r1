import pytest
from conftest import save_doc, write_save
from nmslib import locate


@pytest.mark.parametrize("name,expected", [
    ("save.hg", (1, "manual")), ("save2.hg", (1, "auto")), ("save3.hg", (2, "manual")),
    ("save30.hg", (15, "auto")), ("save1.hg", None), ("save31.hg", None), ("save02.hg", None),
    ("mf_save.hg", None), ("save.json", None),
])
def test_slot_mapping(name, expected):
    assert locate.parse_save_name(name) == expected


def test_newest_across_all_accounts(nms_root):
    other = nms_root.parent / "DefaultUser"
    other.mkdir()
    write_save(nms_root / "save.hg", save_doc(), 1000)
    newest = write_save(other / "save4.hg", save_doc(), 2000)
    pick = locate.resolve()
    assert pick.path == newest and pick.slot == 2 and pick.kind == "auto" and pick.account_kind == "gog"


def test_slot_takes_newest_of_manual_and_auto(nms_root):
    write_save(nms_root / "save3.hg", save_doc(), 1000)
    auto = write_save(nms_root / "save4.hg", save_doc(), 1500)
    write_save(nms_root / "save5.hg", save_doc(), 3000)
    assert locate.resolve(slot=2).path == auto
    with pytest.raises(locate.LocateError):
        locate.resolve(slot=9)


def test_env_file_pins_a_save_unless_slot_given(nms_root, monkeypatch):
    pinned = write_save(nms_root / "save.hg", save_doc(), 1000)
    write_save(nms_root / "save3.hg", save_doc(), 2000)
    monkeypatch.setenv("NMS_SAVE_PATH", str(pinned))
    assert locate.resolve().path == pinned
    assert locate.resolve(slot=2).slot == 2


def test_explicit_save_path_wins(nms_root, tmp_path):
    write_save(nms_root / "save.hg", save_doc(), 5000)
    elsewhere = write_save(tmp_path / "copy.hg", save_doc(), 1)
    pick = locate.resolve(save=str(elsewhere))
    assert pick.path == elsewhere and pick.slot is None
