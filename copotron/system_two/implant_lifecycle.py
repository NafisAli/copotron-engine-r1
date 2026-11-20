"""
The Implant lifecycle in a vault (spec §7, ADR 0003 in the control plane).

Insertion copies an Implant's instructions.md into the vault as the Implant
Instructions, a procedural memory carrying the Implant's `implant_id` in its
Open Tail, parented under a memory the user chooses. `run` starts an Implant's
entry point only when the vault holds its Implant Instructions. Implant
Removal deletes the Implant Instructions and every attachment to them.
Detachment ends one attachment, moving the Implant Instructions beneath the
oldest remaining attachment when it takes their last parent.
"""

import re
import subprocess
from pathlib import Path
from typing import Any, Dict

import yaml

from copotron.core.implants import IMPLANT_ID_KEY, IMPLANT_INSTRUCTIONS_TYPE, is_implant_instructions
from copotron.core.schema import dump_frontmatter, is_memory_id, parse_frontmatter, parse_frontmatter_and_body
from copotron.core.vault import atomic_write_text, find_memory_file
from copotron.system_two.crystallize import create_memory_node, sync_index

TEMPLATE_FILENAME = "instructions.md"
_TEMPLATE_RE = re.compile(r"\A---\r?\n(.*?)^---[ \t]*\r?\n?(.*)\Z", re.DOTALL | re.MULTILINE)


def engine_implants_dir() -> Path:
    """The engine repo's top-level implants/ folder, where every Implant's source lives."""
    return Path(__file__).resolve().parents[2] / "implants"


def list_implants(implants_dir: Path) -> list[str]:
    """Names of the Implants under implants_dir: the folders holding an instructions.md."""
    if not implants_dir.is_dir():
        return []
    return sorted(p.parent.name for p in implants_dir.glob(f"*/{TEMPLATE_FILENAME}") if p.is_file())


def _read_template(template_path: Path) -> tuple[Dict[str, Any], str]:
    """
    Split an instructions.md template into its frontmatter mapping and body,
    raising ValueError when it lacks a title or a well-formed implant_id.
    """
    match = _TEMPLATE_RE.match(template_path.read_text(encoding="utf-8-sig"))
    frontmatter = yaml.safe_load(match.group(1)) if match else None
    if not isinstance(frontmatter, dict):
        raise ValueError(f"{template_path} has no YAML frontmatter.")
    if not str(frontmatter.get("title") or "").strip():
        raise ValueError(f"{template_path} has no title.")
    if not is_memory_id(str(frontmatter.get(IMPLANT_ID_KEY, ""))):
        raise ValueError(
            f"{template_path} has implant_id {frontmatter.get(IMPLANT_ID_KEY)!r}; "
            f"it must be 8 lower-case hex characters."
        )
    return frontmatter, match.group(2).lstrip("\r\n")


def insert_implant(vault_dir: Path, implants_dir: Path, name: str, attach: str) -> Dict[str, Any]:
    """
    Insert the Implant `name` (a folder under implants_dir) into vault_dir,
    parenting its Implant Instructions under the memory `attach`.
    """
    template, body = _load_implant(implants_dir, name)
    attach_file = find_memory_file(vault_dir, attach) if is_memory_id(attach) else None
    if attach_file is None:
        raise ValueError(f"--attach {attach!r} does not identify an existing memory.")
    try:
        parse_frontmatter(attach_file)
    except Exception as e:
        raise ValueError(f"--attach {attach!r} identifies a memory that cannot be parsed ({e}).") from e
    implant_id = str(template[IMPLANT_ID_KEY])
    existing = _find_implant_instructions(vault_dir, implant_id)
    if existing:
        raise ValueError(
            f"implant {name!r} (implant_id {implant_id}) is already in this vault as Implant Instructions "
            f"{', '.join(existing)}. Re-insertion is not supported yet; add that id to a memory's "
            f"implants to attach it somewhere else."
        )
    created = create_memory_node(
        vault_dir=vault_dir,
        title=template["title"],
        memory_type=IMPLANT_INSTRUCTIONS_TYPE,
        summary=str(template.get("summary") or ""),
        body=body,
        parents=[attach],
        tags=template.get("tags") or [],
        extra_fields={IMPLANT_ID_KEY: implant_id},
    )
    _add_attachment(vault_dir, attach, created["id"])
    sync_index(vault_dir, quiet=True)
    return created


def run_implant(vault_dir: Path, implants_dir: Path, name: str, args: list[str]) -> int:
    """
    Start the Implant `name`'s entry point with args, provided vault_dir holds
    its Implant Instructions, and return the entry point's exit code.
    """
    template, _ = _load_implant(implants_dir, name)
    implant_id = str(template[IMPLANT_ID_KEY])
    if not _find_implant_instructions(vault_dir, implant_id):
        raise ValueError(
            f"this vault holds no Implant Instructions for {name!r} (implant_id {implant_id}). "
            f"Insert it first: copotron implant insert {name} --attach <memory-id>"
        )
    entry_point = implants_dir / name / f"{name}.py"
    if not entry_point.is_file():
        raise ValueError(f"Implant {name!r} has no entry point: {entry_point} does not exist.")
    # stdin, stdout and stderr are the Implant's own; uv resolves the entry
    # point's inline script dependencies.
    return subprocess.run(["uv", "run", str(entry_point), *args], cwd=implants_dir.parent).returncode


def remove_implant(vault_dir: Path, implants_dir: Path, target: str) -> Dict[str, Any]:
    """
    Implant Removal: delete the Implant Instructions that `target` identifies
    and remove their id from every memory's implants.
    """
    instructions_id = _resolve_implant_instructions(vault_dir, implants_dir, target)
    instructions_file = find_memory_file(vault_dir, instructions_id)
    title = parse_frontmatter(instructions_file).title
    memories = _parse_memories(vault_dir)
    children = [memory.id for _, memory, _ in memories if instructions_id in memory.parents]
    if children:
        raise ValueError(
            f"Implant Instructions {instructions_id} have children ({', '.join(children)}), which a hand edit "
            f"must have left: Implant Instructions never have children. Give each child another parent "
            f"first; removal never orphans or moves a memory."
        )
    detached_from = []
    for memory_file, memory, body in memories:
        if instructions_id in memory.implants:
            implants = [i for i in memory.implants if i != instructions_id]
            atomic_write_text(memory_file, dump_frontmatter(memory.model_copy(update={"implants": implants}), body))
            detached_from.append(memory.id)
    instructions_file.unlink()
    sync_index(vault_dir, quiet=True)
    return {"id": instructions_id, "title": title, "detached_from": detached_from}


def detach_implant(vault_dir: Path, implants_dir: Path, target: str, from_memory: str) -> Dict[str, Any]:
    """
    Detachment: end from_memory's attachment to the Implant Instructions that
    `target` identifies.
    """
    instructions_id = _resolve_implant_instructions(vault_dir, implants_dir, target)
    attached = [m for _, m, _ in _parse_memories(vault_dir) if instructions_id in m.implants]
    if from_memory not in {m.id for m in attached}:
        raise ValueError(
            f"--from {from_memory!r}: Implant Instructions {instructions_id} are not attached to that memory. "
            f"Attached to: {', '.join(m.id for m in attached) or '(none)'}."
        )
    remaining = [m for m in attached if m.id not in (from_memory, instructions_id)]
    if not remaining:
        removed = remove_implant(vault_dir, implants_dir, instructions_id)
        return {
            "id": instructions_id,
            "title": removed["title"],
            "detached_from": from_memory,
            "parents": [],
            "removed": True,
        }
    instructions_file = find_memory_file(vault_dir, instructions_id)
    instructions, instructions_body = parse_frontmatter_and_body(instructions_file)
    from_file = find_memory_file(vault_dir, from_memory)
    memory, body = parse_frontmatter_and_body(from_file)
    implants = [i for i in memory.implants if i != instructions_id]
    atomic_write_text(from_file, dump_frontmatter(memory.model_copy(update={"implants": implants}), body))
    parents = [p for p in instructions.parents if p != from_memory]
    if not parents:
        # Attachments carry no timestamp, so the oldest is the attaching memory with the earliest date.
        parents = [min(remaining, key=lambda m: (str(m.date), m.id)).id]
    if parents != instructions.parents:
        instructions = instructions.model_copy(update={"parents": parents})
        atomic_write_text(instructions_file, dump_frontmatter(instructions, instructions_body))
    sync_index(vault_dir, quiet=True)
    return {
        "id": instructions_id,
        "title": instructions.title,
        "detached_from": from_memory,
        "parents": instructions.parents,
        "removed": False,
    }


def _parse_memories(vault_dir: Path) -> list[tuple[Path, Any, str]]:
    """(file, frontmatter, body) of every memory in vault_dir that parses. Unparseable files are skipped."""
    memories = []
    for memory_file in sorted(vault_dir.glob("*.md")):
        try:
            memory, body = parse_frontmatter_and_body(memory_file)
        except Exception:
            continue
        memories.append((memory_file, memory, body))
    return memories


def _resolve_implant_instructions(vault_dir: Path, implants_dir: Path, target: str) -> str:
    """
    The id of the Implant Instructions that target names: either their own
    memory id, or the name of an Implant whose Implant Instructions the vault holds.
    """
    if is_memory_id(target) and find_memory_file(vault_dir, target) is not None:
        if not _is_implant_instructions_id(vault_dir, target):
            raise ValueError(f"memory {target!r} is not Implant Instructions, so it names no Implant.")
        return target
    template, _ = _load_implant(implants_dir, target)
    implant_id = str(template[IMPLANT_ID_KEY])
    found = _find_implant_instructions(vault_dir, implant_id)
    if not found:
        raise ValueError(f"this vault holds no Implant Instructions for {target!r} (implant_id {implant_id}).")
    if len(found) > 1:
        raise ValueError(
            f"this vault holds {len(found)} Implant Instructions for {target!r} (implant_id {implant_id}): "
            f"{', '.join(found)}. Name the one to act on by its id."
        )
    return found[0]


def _is_implant_instructions_id(vault_dir: Path, memory_id: str) -> bool:
    """True when memory_id identifies a parseable Implant Instructions memory in vault_dir."""
    memory_file = find_memory_file(vault_dir, memory_id)
    if memory_file is None:
        return False
    try:
        memory = parse_frontmatter(memory_file)
    except Exception:
        return False
    return is_implant_instructions(memory.type, memory.model_extra or {})


def _load_implant(implants_dir: Path, name: str) -> tuple[Dict[str, Any], str]:
    """The frontmatter and body of the Implant `name`'s template, refusing a name that is no Implant."""
    available = list_implants(implants_dir)
    if name not in available:
        raise ValueError(
            f"{name!r} is not an Implant. Implants: {', '.join(available) or '(none)'}."
        )
    return _read_template(implants_dir / name / TEMPLATE_FILENAME)


def _find_implant_instructions(vault_dir: Path, implant_id: str) -> list[str]:
    """Ids of the Implant Instructions in vault_dir that carry implant_id. Unparseable files are skipped."""
    found = []
    for memory_file in sorted(vault_dir.glob("*.md")):
        try:
            memory = parse_frontmatter(memory_file)
        except Exception:
            continue
        open_tail = memory.model_extra or {}
        if is_implant_instructions(memory.type, open_tail) and str(open_tail[IMPLANT_ID_KEY]) == implant_id:
            found.append(memory.id)
    return found


def _add_attachment(vault_dir: Path, memory_id: str, instructions_id: str) -> None:
    """Append instructions_id to the implants of memory_id, leaving the rest of the memory as is."""
    memory_file = find_memory_file(vault_dir, memory_id)
    memory, body = parse_frontmatter_and_body(memory_file)
    if instructions_id not in memory.implants:
        memory = memory.model_copy(update={"implants": [*memory.implants, instructions_id]})
    atomic_write_text(memory_file, dump_frontmatter(memory, body))
