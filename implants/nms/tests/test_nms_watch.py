"""watch: one flushed line per Save Update, polled without real sleeps (#29)."""

import re
import shutil

import nms
import pytest
from conftest import save_doc, write_save


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
