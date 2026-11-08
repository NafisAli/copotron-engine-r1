import pytest
from pathlib import Path

from copotron.core.personas import find_persona_definition


def _write_memory(vault_dir: Path, memory_id: str, memory_type: str, tags: list[str], title: str = "Memory"):
    content = (
        "---\n"
        f"id: '{memory_id}'\n"
        f"title: {title}\n"
        "date: '2026-09-01'\n"
        "summary: Test memory.\n"
        f"type: {memory_type}\n"
        "status: active\n"
        "parents: ['00000000']\n"
        f"tags: [{', '.join(tags)}]\n"
        "---\n\n"
        f"# {title}\n"
    )
    (vault_dir / f"{memory_id}-{title.lower().replace(' ', '-')}.md").write_text(content, encoding="utf-8")


@pytest.fixture
def vault(tmp_path):
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    _write_memory(vault_dir, "00000000", "declarative", ["root"], title="Root")
    _write_memory(vault_dir, "c19b60a6", "declarative", ["persona", "aegis-null"], title="Aegis Null")
    _write_memory(vault_dir, "a1b2c3d4", "declarative", ["sensors"], title="Untagged Fact")
    _write_memory(vault_dir, "e5f6a7b8", "procedural", ["persona"], title="Tagged Procedure")
    return vault_dir


def test_finds_persona_definition_by_id(vault):
    definition = find_persona_definition(vault, "c19b60a6")

    assert definition is not None
    assert definition.id == "c19b60a6"
    assert definition.title == "Aegis Null"


@pytest.mark.parametrize(
    "reference",
    [
        "aegis-null",  # a free-text name, not an id
        "",
        "C19B60A6",  # ids are lower-case
        "deadbeef",  # unknown id
        "a1b2c3d4",  # declarative but not tagged persona
        "e5f6a7b8",  # tagged persona but not declarative
    ],
)
def test_returns_none_when_reference_is_not_a_persona_definition(vault, reference):
    assert find_persona_definition(vault, reference) is None
