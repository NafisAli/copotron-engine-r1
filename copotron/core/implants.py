"""
Implant Instructions lookup: the one place that decides whether an `implants`
reference identifies Implant Instructions, the procedural memory Insertion
creates, which carries its Implant's `implant_id` in the Open Tail. The indexer
leaves any other reference out of Inherited Implants, and the audit reports it
as a dangling implant link (ADR 0003 in the control plane).
"""

from collections.abc import Collection, Mapping
from enum import StrEnum
from typing import Any, Optional

from copotron.core.schema import is_memory_id

IMPLANT_INSTRUCTIONS_TYPE = "procedural"
IMPLANT_ID_KEY = "implant_id"


class DanglingImplantCase(StrEnum):
    """Why an implants reference identifies no Implant Instructions. Values are stable report codes."""

    NOT_AN_ID = "not_an_id"
    UNKNOWN_ID = "unknown_id"
    # The id names a memory that is not procedural or carries no implant_id.
    NOT_IMPLANT_INSTRUCTIONS = "not_implant_instructions"


def is_implant_instructions(memory_type: str, open_tail: Mapping[str, Any]) -> bool:
    """True when a memory of memory_type with open_tail is Implant Instructions."""
    implant_id = open_tail.get(IMPLANT_ID_KEY)
    return (
        memory_type == IMPLANT_INSTRUCTIONS_TYPE
        and implant_id is not None
        and str(implant_id).strip() != ""
    )


def attached_implants(implants: Collection[str], instructions_ids: Collection[str]) -> list[str]:
    """
    The references in a memory's implants that identify Implant Instructions,
    in order; instructions_ids holds the ids of every Implant Instructions memory.
    """
    return [reference for reference in implants if reference in instructions_ids]


def diagnose_implant_reference(
    reference: str, memory_ids: Collection[str], instructions_ids: Collection[str]
) -> Optional[DanglingImplantCase]:
    """
    Return None when reference identifies Implant Instructions, otherwise the
    DanglingImplantCase saying why it does not. memory_ids holds every memory
    id in the vault; instructions_ids the Implant Instructions among them.
    """
    if reference in instructions_ids:
        return None
    if not is_memory_id(reference):
        return DanglingImplantCase.NOT_AN_ID
    if reference not in memory_ids:
        return DanglingImplantCase.UNKNOWN_ID
    return DanglingImplantCase.NOT_IMPLANT_INSTRUCTIONS
