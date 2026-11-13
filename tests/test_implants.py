"""
Implants Core Field: a memory attaches Implants by listing the ids of their
Implant Instructions in `implants` (ADR 0003 in the control plane).
"""

from pathlib import Path

import pytest

from copotron.core.schema import dump_frontmatter, parse_frontmatter
from copotron.core.validate import validate_file
from copotron.system_two.crystallize import update_memory_node


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
