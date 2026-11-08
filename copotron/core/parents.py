"""
Parent rule for writes: every memory except the Root names at least one
existing parent, so a write never produces an Orphan. Write paths validate
through `require_parents`. Reads and indexing stay lenient: existing Orphans
and missing parents are reported by the audit, not refused.
"""

from pathlib import Path
from typing import Collection, List

from copotron.core.schema import ROOT_ID, is_memory_id
from copotron.core.vault import find_memory_file


def require_parents(
    vault_dir: Path, memory_id: str, parents: List[str], batch_ids: Collection[str] = ()
) -> None:
    """
    Write-path guard: raise ValueError when writing memory_id with parents
    would make it an Orphan (a non-Root memory with no parents), or when a
    parent is not a memory id, is the memory itself, or does not exist.
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
        if parent not in batch_ids and find_memory_file(vault_dir, parent) is None:
            raise ValueError(
                f"memory {memory_id!r} names parent {parent!r}, which does not identify an existing memory."
            )
