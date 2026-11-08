"""
Persona Definition lookup: the one place that decides whether a persona
reference identifies a Persona Definition (a declarative memory tagged
`persona`). Write paths validate through `require_persona_definition`; the
audit and retrieval are meant to reuse `find_persona_definition`.
"""

from pathlib import Path
from typing import Optional

from copotron.core.schema import MemorySchema, is_memory_id, parse_frontmatter
from copotron.core.vault import find_memory_file

PERSONA_DEFINITION_TYPE = "declarative"
PERSONA_DEFINITION_TAG = "persona"


def _resolve_definition(
    vault_dir: Path, reference: str, memory_type: str, tag: str
) -> tuple[Optional[MemorySchema], str]:
    """
    Resolve reference to the memory it identifies, provided that memory has
    memory_type and carries tag. Returns (memory, "") on success, otherwise
    (None, reason) where reason says why reference identifies no definition.
    """
    if not is_memory_id(reference):
        return None, "is not a memory id (expected 8 lower-case hex characters)"
    memory_file = find_memory_file(vault_dir, reference)
    if memory_file is None:
        return None, "does not identify an existing memory"
    try:
        memory = parse_frontmatter(memory_file)
    except Exception as e:
        return None, f"identifies a memory that cannot be parsed ({e})"
    if memory.id != reference or memory.type != memory_type or tag not in memory.tags:
        return None, f"identifies a memory that is not {memory_type} and tagged '{tag}'"
    return memory, ""


def find_persona_definition(vault_dir: Path, persona_id: str) -> Optional[MemorySchema]:
    """Return the Persona Definition that persona_id identifies, or None."""
    memory, _ = _resolve_definition(vault_dir, persona_id, PERSONA_DEFINITION_TYPE, PERSONA_DEFINITION_TAG)
    return memory


def require_persona_definition(vault_dir: Path, persona_id: str) -> MemorySchema:
    """
    Write-path guard: return the Persona Definition persona_id identifies, or
    raise ValueError explaining why it does not identify one.
    """
    memory, reason = _resolve_definition(vault_dir, persona_id, PERSONA_DEFINITION_TYPE, PERSONA_DEFINITION_TAG)
    if memory is None:
        raise ValueError(
            f"persona {persona_id!r} {reason}. A persona must be the id of a Persona Definition: "
            f"a {PERSONA_DEFINITION_TYPE} memory tagged '{PERSONA_DEFINITION_TAG}'."
        )
    return memory
