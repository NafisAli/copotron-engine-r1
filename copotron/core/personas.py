"""
Persona Definition lookup: the one place that decides whether a persona
reference identifies a Persona Definition (a declarative memory tagged
`persona`). Write paths validate through `require_persona_definition`, the
audit classifies Dangling Personas through `diagnose_persona_reference`, and
retrieval resolves titles through `attach_persona_titles`.
"""

from enum import StrEnum
from pathlib import Path
from typing import Optional

from copotron.core.schema import MemorySchema, is_memory_id, parse_frontmatter
from copotron.core.vault import find_memory_file

PERSONA_DEFINITION_TYPE = "declarative"
PERSONA_DEFINITION_TAG = "persona"



class DanglingPersonaCase(StrEnum):
    """Why a persona reference identifies no Persona Definition. Values are stable report codes."""

    NOT_AN_ID = "not_an_id"
    UNKNOWN_ID = "unknown_id"
    # The id names a memory that is not declarative, not tagged `persona`,
    # cannot be parsed, or whose frontmatter id disagrees with its filename.
    NOT_A_PERSONA_DEFINITION = "not_a_persona_definition"


def _resolve_definition(
    vault_dir: Path, reference: str, memory_type: str, tag: str
) -> tuple[Optional[MemorySchema], Optional[DanglingPersonaCase], str]:
    """
    Resolve reference to the memory it identifies, provided that memory has
    memory_type and carries tag. Returns (memory, None, "") on success,
    otherwise (None, problem, reason): problem is the DanglingPersonaCase
    and reason says in words why reference identifies no definition.
    """
    if not is_memory_id(reference):
        return None, DanglingPersonaCase.NOT_AN_ID, "is not a memory id (expected 8 lower-case hex characters)"
    memory_file = find_memory_file(vault_dir, reference)
    if memory_file is None:
        return None, DanglingPersonaCase.UNKNOWN_ID, "does not identify an existing memory"
    try:
        memory = parse_frontmatter(memory_file)
    except Exception as e:
        return None, DanglingPersonaCase.NOT_A_PERSONA_DEFINITION, f"identifies a memory that cannot be parsed ({e})"
    if memory.id != reference or memory.type != memory_type or tag not in memory.tags:
        return None, DanglingPersonaCase.NOT_A_PERSONA_DEFINITION, f"identifies a memory that is not {memory_type} and tagged '{tag}'"
    return memory, None, ""


def find_persona_definition(vault_dir: Path, persona_id: str) -> Optional[MemorySchema]:
    """Return the Persona Definition that persona_id identifies, or None."""
    memory, _, _ = _resolve_definition(vault_dir, persona_id, PERSONA_DEFINITION_TYPE, PERSONA_DEFINITION_TAG)
    return memory


def diagnose_persona_reference(vault_dir: Path, persona_id: str) -> Optional[DanglingPersonaCase]:
    """
    Return None when persona_id identifies a Persona Definition, otherwise the
    DanglingPersonaCase saying why it does not.
    """
    _, problem, _ = _resolve_definition(vault_dir, persona_id, PERSONA_DEFINITION_TYPE, PERSONA_DEFINITION_TAG)
    return problem


def require_persona_definition(vault_dir: Path, persona_id: str) -> MemorySchema:
    """
    Write-path guard: return the Persona Definition persona_id identifies, or
    raise ValueError explaining why it does not identify one.
    """
    memory, _, reason = _resolve_definition(vault_dir, persona_id, PERSONA_DEFINITION_TYPE, PERSONA_DEFINITION_TAG)
    if memory is None:
        raise ValueError(
            f"persona {persona_id!r} {reason}. A persona must be the id of a Persona Definition: "
            f"a {PERSONA_DEFINITION_TYPE} memory tagged '{PERSONA_DEFINITION_TAG}'."
        )
    return memory


def attach_persona_titles(vault_dir: Path, records: list[dict]) -> list[dict]:
    """
    Set `inherited_persona_title` on each record (in place, and returned) to the
    title of the Persona Definition its `inherited_persona` identifies. A
    missing or Dangling Persona gets None, leaving `inherited_persona` as is:
    retrieval reports what the index holds and never fails over it. Each
    distinct reference is resolved once.
    """
    titles: dict[str, Optional[str]] = {}
    for record in records:
        reference = record.get("inherited_persona")
        if reference and reference not in titles:
            definition = find_persona_definition(vault_dir, reference)
            titles[reference] = definition.title if definition else None
        record["inherited_persona_title"] = titles.get(reference) if reference else None
    return records
