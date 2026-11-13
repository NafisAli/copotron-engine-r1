"""Save Updates: when the game has finished writing a Save, found by polling (#29).

A Save Update is one `.hg` file whose write has settled: its modification time
and size, and its `mf_` manifest's, changed since the last Save Update and then
stayed the same for one more poll. The separate `.hg` and `mf_` writes are one
Save Update; a slot's manual save and autosave are two. Nothing is persisted:
the files seen at startup are the starting point, and every later change counts.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from .locate import SaveFile

Signature = tuple  # (mtime_ns, size) of the .hg file and of its manifest (None when absent)


def signature(path: Path) -> Signature | None:
    """None when the .hg file is gone."""
    try:
        st = path.stat()
    except FileNotFoundError:
        return None
    try:
        mf = path.with_name("mf_" + path.name).stat()
        manifest = (mf.st_mtime_ns, mf.st_size)
    except FileNotFoundError:
        manifest = None
    return st.st_mtime_ns, st.st_size, manifest


class Poller:
    """Turns successive listings of the watched files into settled Save Updates."""

    def __init__(self, listing: Callable[[], list[SaveFile]]):
        self.listing = listing  # the watched files now; raises when the save directory is gone
        self.seen: dict[Path, Signature] = {}  # as of startup or the last Save Update
        self.pending: dict[Path, Signature] = {}  # changed, waiting one poll to settle

    def start(self) -> list[SaveFile]:
        """Take the files as they are now as the starting point, without reporting them."""
        files = self.listing()
        self.seen = {f.path: sig for f in files if (sig := signature(f.path))}
        return files

    def poll(self) -> list[SaveFile]:
        """The Save Updates that settled since the last poll, oldest first."""
        settled = []
        for f in self.listing():
            sig = signature(f.path)
            if sig is None or sig == self.seen.get(f.path):
                self.pending.pop(f.path, None)
            elif self.pending.get(f.path) == sig:
                del self.pending[f.path]
                self.seen[f.path] = sig
                settled.append(f)
            else:
                self.pending[f.path] = sig
        return sorted(settled, key=lambda f: (f.modified, f.path.name))


def run(poller: Poller, on_update: Callable[[SaveFile], None], *, interval: float, idle_exit: float,
        clock: Callable[[], float], sleep: Callable[[float], None]) -> None:
    """Poll every `interval` seconds until `idle_exit` seconds pass without a Save Update."""
    last = clock()
    while True:
        sleep(interval)
        updates = poller.poll()
        for f in updates:
            on_update(f)
        now = clock()
        if updates:
            last = now
        elif now - last >= idle_exit:
            return
