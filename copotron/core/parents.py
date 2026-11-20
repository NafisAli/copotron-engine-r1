"""
Parent rule for writes: every memory except the Root names at least one
existing parent, so a write never produces an Orphan, and no parent is
Implant Instructions, which never have children. Write paths validate
through `require_parents`. Reads and indexing stay lenient: existing Orphans,
missing parents and children of Implant Instructions are reported by the
audit, not refused.
"""

from pathlib import Path
from typing import Collection, List

from copotron.core.implants import is_implant_instructions
from copotron.core.schema import ROOT_ID, is_memory_id, parse_frontmatter
from copotron.core.vault import find_memory_file


def require_parents(
    vault_dir: Path, memory_id: str, parents: List[str], batch_ids: Collection[str] = ()
) -> None:
    """
    Write-path guard: raise ValueError when writing memory_id with parents
    would make it an Orphan (a non-Root memory with no parents), or when a
    parent is not a memory id, is the memory itself, does not exist, or is
    Implant Instructions.
    batch_ids are the memories a manifest batch writes; they count as existing.
    """
    if not parents and memory_id != ROOT_ID:
        raise ValueError(
            f"memory {memory_id!r} has no parents, which would make it an Orphan. Every memory except "
            f"the Root ({ROOT_ID}) needs a parent: pass --parents <id> or --auto-parent."
        )
    for parent in parents:
        parent = str(parent).strip()
        if not is_memory_id(parent):
            raise ValueError(
                f"memory {memory_id!r} names parent {parent!r}, which is not a memory id "
                f"(expected 8 lower-case hex characters)."
            )
        if parent == memory_id:
            raise ValueError(f"memory {memory_id!r} names itself as its own parent.")
        parent_file = find_memory_file(vault_dir, parent)
        if parent_file is None:
            if parent in batch_ids:
                continue
            raise ValueError(
                f"memory {memory_id!r} names parent {parent!r}, which does not identify an existing memory."
            )
        if _is_implant_instructions_file(parent_file):
            raise ValueError(
                f"memory {memory_id!r} names parent {parent!r}, which is Implant Instructions. Implant "
                f"Instructions never have children: put the memory beneath a memory the Implant is attached to."
            )


def _is_implant_instructions_file(memory_file: Path) -> bool:
    """True when memory_file parses as Implant Instructions; an unparseable file is not."""
    try:
        memory = parse_frontmatter(memory_file)
    except Exception:
        return False
    return is_implant_instructions(memory.type, memory.model_extra or {})
