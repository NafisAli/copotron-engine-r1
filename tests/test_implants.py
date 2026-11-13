"""
Implants Core Field: a memory attaches Implants by listing the ids of their
Implant Instructions in `implants` (ADR 0003 in the control plane).
"""

from pathlib import Path
from typing import Optional

import pytest

from copotron.cli import main
from copotron.core.indexer import load_vault
from copotron.core.navigate import navigate
from copotron.core.schema import MemorySchema, dump_frontmatter, parse_frontmatter
from copotron.core.validate import validate_file
from copotron.system_two.crystallize import update_memory_node
from copotron.system_two.search import search_graph


def _write_raw(vault_dir: Path, memory_id: str, frontmatter_tail: str, title: str = "Memory") -> Path:
    content = (
        "---\n"
        f"id: '{memory_id}'\n"
        f"title: {title}\n"
        "date: '2026-09-01'\n"
        "summary: Test memory.\n"
        "type: declarative\n"
        "status: active\n"
        "parents: ['00000000']\n"
        f"{frontmatter_tail}"
        "---\n\n"
        f"# {title}\n"
    )
    path = vault_dir / f"{memory_id}-{title.lower().replace(' ', '-')}.md"
    path.write_text(content, encoding="utf-8")
    return path


# ---------------------------------------------------------
# Schema & validator
# ---------------------------------------------------------

def test_implants_is_a_core_field_not_open_tail(tmp_path):
    path = _write_raw(tmp_path, "11111111", "implants: ['4f2a9c1e', 'b7d3e8a0']\n")

    memory = parse_frontmatter(path)

    assert memory.implants == ["4f2a9c1e", "b7d3e8a0"]
    assert "implants" not in (memory.model_extra or {})


def test_memory_without_implants_has_none(tmp_path):
    path = _write_raw(tmp_path, "11111111", "")

    assert parse_frontmatter(path).implants == []


@pytest.mark.parametrize(
    "yaml_value, expected",
    [
        ("null", []),
        ("'4f2a9c1e'", ["4f2a9c1e"]),  # a single id
        ("[12345678]", ["12345678"]),  # an all-digit id YAML reads as an int
        ("[' 4f2a9c1e ']", ["4f2a9c1e"]),
    ],
)
def test_implants_coerces_like_parents(tmp_path, yaml_value, expected):
    path = _write_raw(tmp_path, "11111111", f"implants: {yaml_value}\n")

    assert parse_frontmatter(path).implants == expected


def test_implants_keeps_references_that_are_not_ids(tmp_path):
    """Reads stay lenient: a reference that isn't an id parses, and the audit reports it."""
    path = _write_raw(tmp_path, "11111111", "implants: ['nms']\n")

    assert parse_frontmatter(path).implants == ["nms"]
    assert validate_file(path, silent=True) is True


@pytest.mark.parametrize(
    "yaml_value",
    [
        "{nms: 4f2a9c1e}",  # a mapping, not a list
        "[[4f2a9c1e]]",  # a nested list
        "[{id: 4f2a9c1e}]",  # a mapping entry
        "[true]",
    ],
)
def test_validator_rejects_implants_that_are_not_a_list_of_ids(tmp_path, yaml_value):
    path = _write_raw(tmp_path, "11111111", f"implants: {yaml_value}\n")

    assert validate_file(path, silent=True) is False


def test_dump_omits_empty_implants(tmp_path):
    """Memories without attachments keep their frontmatter free of an empty implants key."""
    path = _write_raw(tmp_path, "11111111", "")

    assert "implants" not in dump_frontmatter(parse_frontmatter(path), "")


def test_dump_round_trips_implants(tmp_path):
    path = _write_raw(tmp_path, "11111111", "implants: ['4f2a9c1e']\n")
    path.write_text(dump_frontmatter(parse_frontmatter(path), "# Memory\n"), encoding="utf-8")

    assert parse_frontmatter(path).implants == ["4f2a9c1e"]


def test_update_keeps_existing_implants(tmp_path):
    vault = tmp_path
    _write_raw(vault, "00000000", "", title="Root")
    path = _write_raw(vault, "11111111", "implants: ['4f2a9c1e']\n", title="Campaign")

    result = update_memory_node(vault, path, summary="A new summary.")

    assert parse_frontmatter(result["file_path"]).implants == ["4f2a9c1e"]


# ---------------------------------------------------------
# Inherited Implants
# ---------------------------------------------------------

NMS = "4f2a9c1e"  # Implant Instructions ids
HUE = "b7d3e8a0"


def _write_memory(
    vault_dir: Path,
    memory_id: str,
    title: str,
    parents: list[str],
    implants: Optional[list[str]] = None,
    memory_type: str = "declarative",
    implant_id: Optional[str] = None,
) -> Path:
    extra = {"implant_id": implant_id} if implant_id is not None else {}
    memory = MemorySchema(
        id=memory_id,
        title=title,
        date="2026-09-01",
        summary=f"Summary for {title}",
        type=memory_type,
        status="active",
        parents=parents,
        implants=implants or [],
        **extra,
    )
    path = vault_dir / f"{memory_id}-{title.lower().replace(' ', '-')}.md"
    path.write_text(dump_frontmatter(memory, f"# {title}\n"), encoding="utf-8")
    return path


def _write_instructions(vault_dir: Path, memory_id: str, title: str, parent: str, implant_id: str) -> Path:
    return _write_memory(vault_dir, memory_id, title, [parent], memory_type="procedural", implant_id=implant_id)


@pytest.fixture
def implant_vault(tmp_path, monkeypatch):
    """
    Root
    ├── Gaming (implants NMS) ── NMS Instructions
    │   └── Campaign ──┐
    └── Home (implants HUE) ── HUE Instructions
        └── Lights ────┴── Shared Session (child of Campaign and Lights)
    """
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setenv("VAULT_PATH", str(vault))
    _write_memory(vault, "00000000", "Root", [])
    _write_memory(vault, "0000000a", "Gaming", ["00000000"], implants=[NMS])
    _write_memory(vault, "0000000b", "Home", ["00000000"], implants=[HUE])
    _write_instructions(vault, NMS, "NMS Instructions", "0000000a", implant_id="9c0d1e2f")
    _write_instructions(vault, HUE, "HUE Instructions", "0000000b", implant_id="3a4b5c6d")
    _write_memory(vault, "0000000c", "Campaign", ["0000000a"])
    _write_memory(vault, "0000000d", "Lights", ["0000000b"])
    _write_memory(vault, "0000000e", "Shared Session", ["0000000c", "0000000d"])
    return vault


def test_memory_inherits_implants_attached_to_an_ancestor(implant_vault):
    graph = load_vault(implant_vault, silent=True)

    assert graph["0000000a"]["inherited_implants"] == [NMS]
    assert graph["0000000c"]["inherited_implants"] == [NMS]


def test_inherited_implants_are_the_union_over_every_ancestor(implant_vault):
    graph = load_vault(implant_vault, silent=True)

    assert graph["0000000e"]["inherited_implants"] == sorted([NMS, HUE])


def test_own_implants_add_to_inherited_ones_rather_than_override(implant_vault):
    _write_memory(implant_vault, "0000000c", "Campaign", ["0000000a"], implants=[HUE])

    graph = load_vault(implant_vault, silent=True)

    assert graph["0000000c"]["inherited_implants"] == sorted([NMS, HUE])


def test_memory_with_no_attached_ancestor_inherits_no_implants(implant_vault):
    graph = load_vault(implant_vault, silent=True)

    assert graph["00000000"]["inherited_implants"] == []
    assert graph["00000000"]["implants"] == []


def test_inherited_implants_survive_an_unchanged_reindex(implant_vault):
    load_vault(implant_vault, silent=True)

    graph = load_vault(implant_vault, silent=True)  # every memory is a cache hit

    assert graph["0000000a"]["implants"] == [NMS]
    assert graph["0000000e"]["inherited_implants"] == sorted([NMS, HUE])


def test_implants_are_not_kept_in_the_open_tail(implant_vault):
    graph = load_vault(implant_vault, silent=True)

    assert "implants" not in graph["0000000a"]["open_tail"]


def test_memories_in_and_below_a_cycle_inherit_the_union_of_their_ancestors(tmp_path, capsys):
    vault = tmp_path / "cycle_vault"
    vault.mkdir()
    _write_memory(vault, "00000000", "Root", [], implants=[NMS])
    _write_instructions(vault, NMS, "NMS Instructions", "00000000", implant_id="9c0d1e2f")
    _write_instructions(vault, HUE, "HUE Instructions", "00000000", implant_id="3a4b5c6d")
    # F and G form a cycle below Root; G attaches HUE; H hangs below the cycle.
    _write_memory(vault, "0000000f", "Cycle F", ["00000000", "00000010"])
    _write_memory(vault, "00000010", "Cycle G", ["0000000f"], implants=[HUE])
    _write_memory(vault, "00000011", "Below Cycle", ["0000000f"])

    graph = load_vault(vault, silent=True)

    assert "Cycle detected" in capsys.readouterr().err
    assert graph["0000000f"]["inherited_implants"] == sorted([NMS, HUE])
    assert graph["00000010"]["inherited_implants"] == sorted([NMS, HUE])
    assert graph["00000011"]["inherited_implants"] == sorted([NMS, HUE])


# ---------------------------------------------------------
# Dangling implant links
# ---------------------------------------------------------

@pytest.mark.parametrize(
    "reference",
    [
        "nms",  # a name, not an id
        "deadbeef",  # no such memory
        "0000000c",  # a memory that is not Implant Instructions (declarative)
        "00000020",  # procedural, but carries no implant_id
    ],
)
def test_dangling_implant_links_are_left_out_of_inheritance(implant_vault, reference):
    _write_memory(implant_vault, "00000020", "Plain Procedure", ["00000000"], memory_type="procedural")
    _write_memory(implant_vault, "0000000a", "Gaming", ["00000000"], implants=[NMS, reference])

    graph = load_vault(implant_vault, silent=True)

    assert graph["0000000a"]["implants"] == [NMS, reference]  # the field itself is kept as written
    assert graph["0000000a"]["inherited_implants"] == [NMS]
    assert graph["0000000c"]["inherited_implants"] == [NMS]


def test_implant_link_dangles_once_its_instructions_lose_their_implant_id(implant_vault):
    load_vault(implant_vault, silent=True)
    _write_memory(implant_vault, NMS, "NMS Instructions", ["0000000a"], memory_type="procedural")

    graph = load_vault(implant_vault, silent=True)  # only the instructions changed

    assert graph["0000000c"]["inherited_implants"] == []
    assert graph["0000000e"]["inherited_implants"] == [HUE]


# ---------------------------------------------------------
# Retrieval: navigate and search
# ---------------------------------------------------------

def _by_id(results: list[dict]) -> dict[str, dict]:
    return {r["id"]: r for r in results}


def test_navigate_returns_inherited_implants_beside_inherited_persona(implant_vault):
    load_vault(implant_vault, silent=True)

    down = _by_id(navigate("0000000c", "down", print_output=False))
    up = _by_id(navigate("0000000e", "up", print_output=False))

    assert down["0000000e"]["inherited_implants"] == sorted([NMS, HUE])
    assert down["0000000e"]["inherited_persona"] is None
    assert up["0000000c"]["inherited_implants"] == [NMS]
    assert up["0000000d"]["inherited_implants"] == [HUE]


def test_search_returns_inherited_implants(implant_vault):
    load_vault(implant_vault, silent=True)

    by_id = _by_id(search_graph(query="0000000e 00000000", print_output=False))
    by_text = _by_id(search_graph(query="Campaign", print_output=False))
    by_filter = _by_id(search_graph(memory_type="declarative", print_output=False))

    assert by_id["0000000e"]["inherited_implants"] == sorted([NMS, HUE])
    assert by_id["00000000"]["inherited_implants"] == []
    assert by_text["0000000c"]["inherited_implants"] == [NMS]
    assert by_filter["0000000d"]["inherited_implants"] == [HUE]


def test_retrieval_follows_an_attachment_added_to_an_ancestor(implant_vault):
    load_vault(implant_vault, silent=True)
    _write_memory(implant_vault, "00000000", "Root", [], implants=[HUE])

    load_vault(implant_vault, silent=True)  # Campaign itself is unchanged

    assert _by_id(navigate("0000000a", "down", print_output=False))["0000000c"]["inherited_implants"] == sorted([NMS, HUE])


def test_text_output_names_inherited_implants(implant_vault, capsys):
    load_vault(implant_vault, silent=True)

    assert main(["navigate", "0000000c", "--direction", "down"]) == 0
    navigate_out = capsys.readouterr().out
    assert main(["search", "Lights"]) == 0
    search_out = capsys.readouterr().out

    assert f"[0000000e] (declarative, active) Shared Session  · implants: {NMS}, {HUE}" in navigate_out
    assert f"[0000000d] (declarative, active) Lights  · implants: {HUE}" in search_out


def test_text_output_omits_implants_when_none_are_inherited(implant_vault, capsys):
    load_vault(implant_vault, silent=True)

    assert main(["search", "00000000"]) == 0

    assert "implants:" not in capsys.readouterr().out
