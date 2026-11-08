"""
Persona Definition lookup: the one place that decides whether a persona
reference identifies a Persona Definition (a declarative memory tagged
`persona`). Write-path validation, the audit and retrieval all go through
`find_persona_definition`.
"""

import re
from pathlib import Path
from typing import Optional

from copotron.core.schema import MemorySchema, parse_frontmatter
from copotron.core.vault import find_memory_file

MEMORY_ID_PATTERN = re.compile(r"^[0-9a-f]{8}$")

PERSONA_DEFINITION_TYPE = "declarative"
PERSONA_DEFINITION_TAG = "persona"


def is_memory_id(value: object) -> bool:
    """True when value has the shape of a memory identifier (8 lower-case hex characters)."""
    return isinstance(value, str) and bool(MEMORY_ID_PATTERN.match(value))


def _find_definition(vault_dir: Path, reference: object, memory_type: str, tag: str) -> Optional[MemorySchema]:
    """
    Resolve reference to the memory it identifies, provided that memory has
    memory_type and carries tag. Returns None for anything else: a reference
    that is not an identifier, an unknown identifier, an unreadable memory,
    or a memory of the wrong type or tags.
    """
    if not is_memory_id(reference):
        return None
    memory_file = find_memory_file(vault_dir, reference)
    if memory_file is None:
        return None
    try:
        memory = parse_frontmatter(memory_file)
    except Exception:
        return None
    if memory.id != reference or memory.type != memory_type or tag not in memory.tags:
        return None
    return memory


def find_persona_definition(vault_dir: Path, persona_id: object) -> Optional[MemorySchema]:
    """Return the Persona Definition that persona_id identifies, or None."""
    return _find_definition(vault_dir, persona_id, PERSONA_DEFINITION_TYPE, PERSONA_DEFINITION_TAG)


def require_persona_definition(vault_dir: Path, persona_id: object) -> MemorySchema:
    """
    Write-path guard: return the Persona Definition persona_id identifies, or
    raise ValueError explaining why it does not identify one.
    """
    definition = find_persona_definition(vault_dir, persona_id)
    if definition is not None:
        return definition
    if not is_memory_id(persona_id):
        reason = "is not a memory id (expected 8 lower-case hex characters)"
    elif find_memory_file(vault_dir, persona_id) is None:
        reason = "does not identify an existing memory"
    else:
        reason = f"identifies a memory that is not {PERSONA_DEFINITION_TYPE} and tagged '{PERSONA_DEFINITION_TAG}'"
    raise ValueError(
        f"persona {persona_id!r} {reason}. A persona must be the id of a Persona Definition: "
        f"a {PERSONA_DEFINITION_TYPE} memory tagged '{PERSONA_DEFINITION_TAG}'."
    )
