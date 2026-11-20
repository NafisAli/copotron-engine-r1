"""
Insertion: give a vault an Implant by copying the Implant's instructions.md
into it as the Implant Instructions, a procedural memory carrying the
Implant's `implant_id` in its Open Tail, parented under a memory the user
chooses (spec §7, ADR 0003 in the control plane).
"""

import re
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
    available = list_implants(implants_dir)
    if name not in available:
        raise ValueError(
            f"{name!r} is not an Implant. Implants: {', '.join(available) or '(none)'}."
        )
    template, body = _read_template(implants_dir / name / TEMPLATE_FILENAME)
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
