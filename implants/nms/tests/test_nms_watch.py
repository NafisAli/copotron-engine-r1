"""watch: one flushed line per Save Update, polled without real sleeps (#29)."""

import json
import os
import re
import shutil

import nms
import pytest
from conftest import save_doc, slot, write_save
from nmslib import catalog, watch as w
from nmslib.coords import Address


class FakeTime:
    """The clock and sleep `watch` polls with; `writes[n]` runs while sleeping before poll n.

    Each poll is one `--interval` later, so a write before poll n settles at poll n + 1.
    """

    def __init__(self, writes=None):
        self.now = 0.0
        self.polls = 0
        self.writes = dict(writes or {})

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds
        self.polls += 1
        action = self.writes.pop(self.polls, None)
        if action:
            action()


@pytest.fixture
def fake_time(monkeypatch):
    def install(writes=None) -> FakeTime:
        t = FakeTime(writes)
        monkeypatch.setattr(nms, "watch_clock", t.clock)
        monkeypatch.setattr(nms, "watch_sleep", t.sleep)
        return t
    return install


def watch(capsys, *argv) -> tuple[int, list[str], str]:
    """Run watch to its idle exit (1 minute, 5 s polls): exit code, stdout lines, stderr."""
    code = nms.main(["watch", "--idle-exit", "1", *argv])
    out = capsys.readouterr()
    return code, out.out.splitlines(), out.err


def touch(path, mtime, doc=None):
    """The game writing one Save: its .hg file, then its mf_ manifest."""
    return lambda: (write_save(path, doc or save_doc(), mtime),
                    write_save(path.with_name("mf_" + path.name), {}, mtime))


LINE = re.compile(r"^\[nms watch\] Save updated: slot (\d+) \((\S+)\) at \d\d:\d\d:\d\d")


def updates(lines: list[str]) -> list[tuple[int, str]]:
    """(slot, file) of each Save Update line; every stdout line must be one."""
    out = []
    for line in lines:
        m = LINE.match(line)
        assert m, line
        out.append((int(m.group(1)), m.group(2)))
    return out


# ---- first slice: one line per Save Update -----------------------------------
def test_one_line_per_save_update_and_none_while_nothing_changes(nms_root, fake_time, capsys):
    save = write_save(nms_root / "save3.hg", save_doc(), 1000)
    t = fake_time({2: touch(save, 2000)})
    code, lines, err = watch(capsys)
    assert code == 0 and updates(lines) == [(2, "save3.hg")]
    assert t.now >= 60  # it stopped only after a minute without an update


def test_a_write_that_is_still_changing_reports_once_it_settles(nms_root, fake_time, capsys):
    save = write_save(nms_root / "save.hg", save_doc(), 1000)
    fake_time({2: touch(save, 2000), 3: touch(save, 2001), 4: touch(save, 2002)})
    assert updates(watch(capsys)[1]) == [(1, "save.hg")]


def test_the_manifest_written_a_poll_later_is_the_same_save_update(nms_root, fake_time, capsys):
    save = write_save(nms_root / "save.hg", save_doc(), 1000)
    mf = nms_root / "mf_save.hg"
    fake_time({2: lambda: write_save(save, save_doc(), 2000), 3: lambda: write_save(mf, {}, 2000)})
    assert updates(watch(capsys)[1]) == [(1, "save.hg")]


def test_slots_written_together_report_one_line_each_oldest_first(nms_root, fake_time, capsys):
    a = write_save(nms_root / "save3.hg", save_doc(), 1000)
    b = write_save(nms_root / "save5.hg", save_doc(), 900)
    fake_time({2: lambda: (touch(b, 2001)(), touch(a, 2000)())})
    assert updates(watch(capsys)[1]) == [(2, "save3.hg"), (3, "save5.hg")]


def test_the_manual_save_and_autosave_of_one_slot_are_two_save_updates(nms_root, fake_time, capsys):
    manual = write_save(nms_root / "save3.hg", save_doc(), 1000)
    auto = write_save(nms_root / "save4.hg", save_doc(), 900)
    fake_time({2: lambda: (touch(manual, 2000)(), touch(auto, 2001)())})
    assert updates(watch(capsys)[1]) == [(2, "save3.hg"), (2, "save4.hg")]


def test_a_new_save_file_is_a_save_update(nms_root, fake_time, capsys):
    write_save(nms_root / "save.hg", save_doc(), 1000)
    fake_time({2: touch(nms_root / "save7.hg", 2000)})
    assert updates(watch(capsys)[1]) == [(4, "save7.hg")]


def test_every_line_is_flushed_as_it_is_printed(nms_root, fake_time, monkeypatch):
    save = write_save(nms_root / "save.hg", save_doc(), 1000)
    fake_time({2: touch(save, 2000)})
    flushed = []
    real_print = print

    def spy(*a, **k):
        if k.get("file") is None:  # stdout only; stderr has its own lines
            flushed.append(k.get("flush"))
        real_print(*a, **k)
    monkeypatch.setattr("builtins.print", spy)
    nms.main(["watch", "--idle-exit", "1"])
    assert flushed == [True]


def test_startup_and_stopping_go_to_stderr(nms_root, fake_time, capsys):
    write_save(nms_root / "save.hg", save_doc(), 1000)
    fake_time()
    code, lines, err = watch(capsys)
    assert code == 0 and lines == []
    assert "watching" in err and "every 5s" in err and "no Save Update for 1 min" in err


def test_idle_exit_counts_from_the_last_save_update(nms_root, fake_time, capsys):
    save = write_save(nms_root / "save.hg", save_doc(), 1000)
    t = fake_time({10: touch(save, 2000)})  # settles at poll 11, 55 s in
    code, lines, _ = watch(capsys)
    assert code == 0 and len(lines) == 1 and t.now == pytest.approx(55 + 60)


def test_interval_sets_the_polling_period(nms_root, fake_time, capsys):
    write_save(nms_root / "save.hg", save_doc(), 1000)
    t = fake_time()
    watch(capsys, "--interval", "20")
    assert t.polls == 3 and t.now == 60


def test_the_save_directory_going_missing_is_fatal(nms_root, fake_time, capsys):
    write_save(nms_root / "save.hg", save_doc(), 1000)
    fake_time({3: lambda: shutil.rmtree(nms_root.parent)})
    code, lines, err = watch(capsys)
    assert code == 2 and lines == [] and err.splitlines()[-1].startswith("nms: ")


def test_no_save_to_watch_is_fatal(nms_root, fake_time, capsys):
    fake_time()
    code, lines, err = watch(capsys)
    assert code == 2 and lines == [] and err.startswith("nms: ")


def test_slot_narrows_the_watch_to_that_slot(nms_root, fake_time, capsys):
    a = write_save(nms_root / "save.hg", save_doc(), 1000)
    b = write_save(nms_root / "save3.hg", save_doc(), 1000)
    fake_time({2: lambda: (touch(a, 2000)(), touch(b, 2000)())})
    assert updates(watch(capsys, "--slot", "2")[1]) == [(2, "save3.hg")]


def test_save_narrows_the_watch_to_that_file(nms_root, fake_time, capsys):
    a = write_save(nms_root / "save.hg", save_doc(), 1000)
    b = write_save(nms_root / "save2.hg", save_doc(), 1000)
    fake_time({2: lambda: (touch(a, 2000)(), touch(b, 2000)())})
    assert updates(watch(capsys, "--save", str(b))[1]) == [(1, "save2.hg")]


def test_every_account_under_the_root_is_watched_and_named(nms_root, fake_time, capsys):
    write_save(nms_root / "save.hg", save_doc(), 1000)
    gog = nms_root.parent / "DefaultUser"
    gog.mkdir()
    other = write_save(gog / "save.hg", save_doc(), 900)
    fake_time({2: touch(other, 2000)})
    assert updates(watch(capsys)[1]) == [(1, "DefaultUser/save.hg")]


# ---- second slice: the Save Delta on every line ------------------------------------------
def doc(units=100, **ps):
    return save_doc(Units=units, **ps)


def delta(line: str) -> list[str]:
    """The segments after the header: the Save Delta, then any notes."""
    return line.split(" | ")[1:]


def test_the_newest_save_is_the_baseline_at_startup(nms_root, fake_time, capsys):
    write_save(nms_root / "save.hg", doc(), 900)
    save = write_save(nms_root / "save3.hg", doc(units=5000), 1000)
    fake_time({2: touch(save, 2000, doc(units=3800))})
    code, lines, err = watch(capsys)
    assert code == 0 and [delta(x) for x in lines] == [["-1,200 Units"]]
    assert "baseline slot 2 (save3.hg)" in err


def test_a_slots_first_save_update_has_no_baseline_and_becomes_it(nms_root, fake_time, capsys):
    write_save(nms_root / "save.hg", doc(), 1000)
    other = write_save(nms_root / "save3.hg", doc(), 900)
    fake_time({2: touch(other, 2000, doc(units=500)), 4: touch(other, 3000, doc(units=700))})
    assert [delta(x) for x in watch(capsys)[1]] == [["no baseline"], ["+200 Units"]]


def test_an_unchanged_save_update_is_still_a_line(nms_root, fake_time, capsys):
    save = write_save(nms_root / "save.hg", doc(), 1000)
    fake_time({2: touch(save, 2000, doc())})
    assert [delta(x) for x in watch(capsys)[1]] == [["no changes"]]


def test_the_autosave_after_the_manual_save_is_compared_with_it(nms_root, fake_time, capsys):
    manual = write_save(nms_root / "save3.hg", doc(), 1000)
    auto = write_save(nms_root / "save4.hg", doc(), 900)
    fake_time({2: lambda: (touch(manual, 2000, doc(units=600))(), touch(auto, 2001, doc(units=600))())})
    assert [delta(x) for x in watch(capsys)[1]] == [["+500 Units"], ["no changes"]]


def test_each_account_keeps_its_own_baselines(nms_root, fake_time, capsys):
    write_save(nms_root / "save.hg", doc(), 1000)
    gog = nms_root.parent / "DefaultUser"
    gog.mkdir()
    other = write_save(gog / "save.hg", doc(units=9), 900)
    fake_time({2: touch(other, 2000, doc(units=9))})
    assert [delta(x) for x in watch(capsys)[1]] == [["no baseline"]]  # never compared with st_'s slot 1


def test_inventory_changes_read_by_name_with_the_new_total(nms_root, fake_time, capsys):
    chest = lambda n: {"ValidSlotIndices": [{}] * 50, "Slots": [slot("^YELLOW2", n, 500)]}  # noqa: E731
    save = write_save(nms_root / "save.hg", doc(Chest1Inventory=chest(9)), 1000)
    fake_time({2: touch(save, 2000, doc(Chest1Inventory=chest(129)))})
    copper = catalog.name_for("YELLOW2")
    assert [delta(x) for x in watch(capsys)[1]] == [[f"+120 {copper} (788)"]]  # 650 carried + 9 in Storage 0


def garble(path, mtime):
    """A save the decoder can't read: neither JSON nor LZ4 blocks."""
    path.write_bytes(b"not a save")
    os.utime(path, (mtime, mtime))


def test_an_unreadable_save_is_a_warning_and_keeps_the_baseline(nms_root, fake_time, capsys):
    save = write_save(nms_root / "save.hg", doc(), 1000)
    fake_time({2: lambda: garble(save, 2000),
               4: touch(save, 3000, doc(units=150))})
    code, lines, err = watch(capsys)
    assert code == 0 and [delta(x) for x in lines] == [["+50 Units"]]
    assert "warning: slot 1 (save.hg) unreadable" in err


def test_a_stale_game_data_snapshot_appends_one_note(nms_root, fake_time, capsys):
    stale = doc()
    stale["Version"] = 9 * 512 + catalog.snapshot()["save_base_version"] + 1
    save = write_save(nms_root / "save.hg", stale, 1000)
    fake_time({2: touch(save, 2000, stale)})
    (line,) = watch(capsys)[1]
    assert delta(line)[0] == "no changes" and delta(line)[1].startswith("Note: Game data built for save version")


def test_the_text_line_reads_every_kind_of_change():
    a = Address(0, 1, 2, 3, 4, 2)
    planets = [w.NewPlace(f"Ekoxim planet {i}", None, a, True, "Lush") for i in range(1, 6)]
    d = w.SaveDelta(
        inventory=[w.ItemChange("Chromatic Metal", ["PLANT_POOP"], 120, 512)],
        currencies=[w.CurrencyChange("units", -1200, 50)],
        systems=[w.NewPlace("Ekoxim", "Ekoxim", a, True)], planets=planets,
        bases_added=[w.BaseChange("Camp", "HomePlanetBase", a, 1, 1, None)],
        bases_edited=[w.BaseChange("Home", "HomePlanetBase", a, 9, -1, "Old Home")],
        bases_removed=[w.BaseChange("", "HomePlanetBase", a, 0, 0, None)],
        location=w.Move(a, a, "Ekoxim IV"), game_mode=("Normal", "Survival"))
    assert nms.delta_text(d) == [
        "+120 Chromatic Metal (512)", "-1,200 Units", "new system: Ekoxim",
        "new planets: Ekoxim planet 1 (Lush), Ekoxim planet 2 (Lush), Ekoxim planet 3 (Lush) +2 more",
        "base added: Camp (+1 part)", "base edited: Home (renamed from Old Home, -1 part)", "base removed: (unnamed)",
        "moved to Ekoxim IV", "game mode: Normal → Survival"]


def test_naming_an_unnamed_base_reads_renamed_from_unnamed():
    a = Address(0, 1, 2, 3, 4, 2)
    d = w.SaveDelta(bases_edited=[w.BaseChange("Lakeside", "HomePlanetBase", a, 3, 0, "")])
    assert nms.delta_text(d) == ["base edited: Lakeside (renamed from (unnamed))"]


# ---- --json: nms.watch/1 --------------------------------------------------------------------
CHANGES = {"inventory", "currencies", "discoveries", "bases", "location", "game_mode"}


def json_lines(capsys, *argv) -> list[dict]:
    code, lines, _ = watch(capsys, "--json", *argv)
    assert code == 0
    return [json.loads(x) for x in lines]  # one document per line


def test_watch_schema(nms_root, fake_time, capsys):
    save = write_save(nms_root / "save3.hg", doc(), 1000)
    fake_time({2: touch(save, 2000, doc(units=40))})
    (d,) = json_lines(capsys)
    assert set(d) == {"schema", "event", "slot", "account", "kind", "path", "modified", "baseline", "changes",
                      "notes"}
    assert (d["schema"], d["event"], d["slot"], d["kind"], d["baseline"], d["notes"]) == (
        "nms.watch/1", "save_updated", 2, "manual", True, [])
    assert d["path"] == str(save) and d["modified"].endswith("Z")
    assert set(d["changes"]) == CHANGES
    assert d["changes"]["currencies"] == [{"currency": "units", "change": -60, "total": 40}]
    assert d["changes"]["discoveries"] == {"systems": [], "planets": []}
    assert d["changes"]["bases"] == {"added": [], "edited": [], "removed": []}
    assert (d["changes"]["inventory"], d["changes"]["location"], d["changes"]["game_mode"]) == ([], None, None)


def test_watch_json_without_a_baseline_has_no_changes(nms_root, fake_time, capsys):
    write_save(nms_root / "save.hg", doc(), 1000)
    other = write_save(nms_root / "save3.hg", doc(), 900)
    fake_time({2: touch(other, 2000)})
    (d,) = json_lines(capsys)
    assert d["baseline"] is False and d["changes"] is None and d["notes"] == []


def test_watch_json_carries_the_staleness_note(nms_root, fake_time, capsys):
    stale = doc()
    stale["Version"] = 9 * 512 + catalog.snapshot()["save_base_version"] + 1
    save = write_save(nms_root / "save.hg", stale, 1000)
    fake_time({2: touch(save, 2000, stale)})
    (d,) = json_lines(capsys)
    assert len(d["notes"]) == 1 and d["notes"][0].startswith("Game data built for save version")
