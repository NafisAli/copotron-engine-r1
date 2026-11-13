"""Find saves: accounts, slots, and which file a command reads.

Extracted from nms-copilot `nms-save/src/locate.rs`, plus the selection rules
settled by the command-set ticket: newest across *all* accounts by default,
`--save PATH` / `--slot N` per call, `NMS_SAVE_PATH` as the persistent override.
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

SAVE_RE = re.compile(r"^save([2-9]|[12]\d|30)?\.hg$")  # save.hg, save2.hg .. save30.hg


class LocateError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class SaveFile:
    path: Path
    account: str  # account folder name, e.g. st_7656..., DefaultUser
    slot: int | None  # 1..15; None for a file given by path that isn't save*.hg
    kind: str | None  # "manual" | "auto"
    modified: float

    @property
    def account_kind(self) -> str:
        return account_kind(self.account)

    @property
    def account_uid(self) -> str | None:
        """Platform user id, when the folder name carries one (Steam)."""
        return self.account[3:] if self.account.startswith("st_") else None

    def to_json(self) -> dict:
        return {
            "path": str(self.path),
            "account": self.account,
            "account_kind": self.account_kind,
            "slot": self.slot,
            "kind": self.kind,
            "modified": iso(self.modified),
        }


def iso(ts: float | int | None) -> str | None:
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def account_kind(name: str) -> str:
    if name == "DefaultUser":
        return "gog"
    if name.startswith("st_") and name[3:].isdigit():
        return "steam"
    return "unknown"


def parse_save_name(name: str) -> tuple[int, str] | None:
    """save.hg -> slot 1 manual, save2.hg -> slot 1 auto, save3.hg -> slot 2 manual, ..."""
    m = SAVE_RE.match(name)
    if not m:
        return None
    n = int(m.group(1) or 1)
    return (n + 1) // 2, ("manual" if n % 2 == 1 else "auto")


def default_root() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming")) / "HelloGames/NMS"
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/HelloGames/NMS"
    return Path.home() / (
        ".local/share/Steam/steamapps/compatdata/275850/pfx/drive_c/users/steamuser/AppData/Roaming/HelloGames/NMS"
    )


def save_file(path: Path, account: str | None = None) -> SaveFile:
    parsed = parse_save_name(path.name)
    return SaveFile(
        path=path,
        account=account or path.parent.name,
        slot=parsed[0] if parsed else None,
        kind=parsed[1] if parsed else None,
        modified=path.stat().st_mtime,
    )


def list_saves(account_dir: Path) -> list[SaveFile]:
    """Every save file in one account folder, newest first."""
    out = [
        save_file(p, account_dir.name)
        for p in account_dir.iterdir()
        if p.is_file() and parse_save_name(p.name)
    ]
    return sorted(out, key=lambda s: -s.modified)


def account_dirs(root: Path) -> list[Path]:
    """Account folders under an NMS root; a root that itself holds saves counts as one."""
    if not root.is_dir():
        raise LocateError(f"NMS save directory not found: {root}")
    if any(parse_save_name(p.name) for p in root.iterdir() if p.is_file()):
        return [root]
    dirs = sorted(p for p in root.iterdir() if p.is_dir() and any(
        parse_save_name(q.name) for q in p.iterdir() if q.is_file()))
    if not dirs:
        raise LocateError(f"no account folders with saves in {root}")
    return dirs


def all_saves(root: Path) -> list[SaveFile]:
    out = [s for d in account_dirs(root) for s in list_saves(d)]
    return sorted(out, key=lambda s: -s.modified)


def env_save_path() -> str | None:
    """NMS_SAVE_PATH from the environment, else from the engine's machine-local .env."""
    if os.environ.get("NMS_SAVE_PATH"):
        return os.environ["NMS_SAVE_PATH"]
    env_file = Path(__file__).resolve().parents[3] / ".env"  # <engine>/implants/nms/nmslib
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip() == "NMS_SAVE_PATH":
                return value.strip().strip("'\"") or None
    return None


def search_root() -> Path:
    """The folder the selection rules search: NMS_SAVE_PATH (its folder, when it names a
    file), else the platform default. An NMS_SAVE_PATH that does not exist is an error."""
    env = env_save_path()
    if not env:
        return default_root()
    p = Path(env).expanduser()
    if p.is_file():
        return p.parent
    if p.is_dir():
        return p
    raise LocateError(f"NMS_SAVE_PATH does not exist: {p}")


def resolve(save: str | None = None, slot: int | None = None) -> SaveFile:
    """Pick the file a command reads: the newest of `candidates`."""
    return candidates(save, slot)[0]


def candidates(save: str | None = None, slot: int | None = None) -> list[SaveFile]:
    """Every file the selection rules allow, newest first; never empty.

    --save PATH wins. Otherwise the search root is NMS_SAVE_PATH (a file pins that
    file unless --slot is given; a folder replaces the default root), else the
    platform default. --slot N keeps that slot's manual/auto files across all
    accounts; no flags keeps every save under the root.
    """
    if save:
        p = Path(save).expanduser()
        if not p.is_file():
            raise LocateError(f"save file not found: {p}")
        return [save_file(p)]
    env = env_save_path()
    if env and slot is None and Path(env).expanduser().is_file():
        return [save_file(Path(env).expanduser())]
    root = search_root()
    saves = all_saves(root)
    if slot is not None:
        saves = [s for s in saves if s.slot == slot]
        if not saves:
            raise LocateError(f"no save in slot {slot} under {root}")
    return saves
