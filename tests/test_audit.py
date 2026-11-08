import json
from pathlib import Path
from typing import Optional

import pytest

from copotron.cli import main
from copotron.system_two.audit import audit_vault_health


def _write_memory(
    vault_dir: Path,
    memory_id: str,
    title: str,
    memory_type: str = "declarative",
    tags: Optional[list[str]] = None,
    persona: Optional[str] = None,
):
    persona_line = f"persona: '{persona}'\n" if persona is not None else ""
    content = (
        "---\n"
        f"id: '{memory_id}'\n"
        f"title: {title}\n"
        "date: '2026-09-01'\n"
        "summary: Test memory.\n"
        f"type: {memory_type}\n"
        "status: active\n"
        "parents: ['00000000']\n"
        f"tags: [{', '.join(tags or [])}]\n"
        f"{persona_line}"
        "---\n\n"
        f"# {title}\n"
    )
    slug = title.lower().replace(" ", "-")
    (vault_dir / f"{memory_id}-{slug}.md").write_text(content, encoding="utf-8")


@pytest.fixture
def vault(tmp_path):
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    _write_memory(vault_dir, "00000000", "Root", tags=["root"])
    _write_memory(vault_dir, "c19b60a6", "Aegis Null", tags=["persona", "aegis-null"])
    return vault_dir


def _dangling(vault_dir: Path) -> list[dict]:
    return audit_vault_health(vault_dir=vault_dir, check_semantic=False)["dangling_personas"]


def test_reports_persona_that_is_not_an_id(vault):
    _write_memory(vault, "11111111", "Legacy Note", persona="aegis-null")

    assert _dangling(vault) == [
        {"id": "11111111", "title": "Legacy Note", "persona": "aegis-null", "problem": "not_an_id"}
    ]


def test_reports_persona_id_that_does_not_exist(vault):
    _write_memory(vault, "11111111", "Stale Note", persona="deadbeef")

    assert _dangling(vault) == [
        {"id": "11111111", "title": "Stale Note", "persona": "deadbeef", "problem": "unknown_id"}
    ]


@pytest.mark.parametrize(
    "memory_type, tags",
    [
        ("declarative", ["sensors"]),  # declarative but not tagged persona
        ("procedural", ["persona"]),  # tagged persona but not declarative
    ],
)
def test_reports_persona_id_that_is_not_a_persona_definition(vault, memory_type, tags):
    _write_memory(vault, "a1b2c3d4", "Some Memory", memory_type=memory_type, tags=tags)
    _write_memory(vault, "11111111", "Misattributed Note", persona="a1b2c3d4")

    assert _dangling(vault) == [
        {
            "id": "11111111",
            "title": "Misattributed Note",
            "persona": "a1b2c3d4",
            "problem": "not_a_persona_definition",
        }
    ]


def test_valid_persona_reference_and_no_persona_produce_no_findings(vault):
    _write_memory(vault, "11111111", "Attributed Note", persona="c19b60a6")
    _write_memory(vault, "22222222", "Plain Note")

    assert _dangling(vault) == []


def test_dangling_persona_makes_vault_unhealthy(vault):
    _write_memory(vault, "11111111", "Legacy Note", persona="aegis-null")

    assert audit_vault_health(vault_dir=vault, check_semantic=False)["healthy"] is False


def test_syntax_only_json_report_lists_dangling_personas(vault, monkeypatch, capsys):
    monkeypatch.setenv("VAULT_PATH", str(vault))
    _write_memory(vault, "11111111", "Legacy Note", persona="aegis-null")

    assert main(["audit", "--syntax-only", "--json"]) == 0

    report = json.loads(capsys.readouterr().out)
    assert report["dangling_personas"] == [
        {"id": "11111111", "title": "Legacy Note", "persona": "aegis-null", "problem": "not_an_id"}
    ]


def test_syntax_only_text_report_lists_dangling_personas(vault, monkeypatch, capsys):
    monkeypatch.setenv("VAULT_PATH", str(vault))
    _write_memory(vault, "11111111", "Legacy Note", persona="aegis-null")

    assert main(["audit", "--syntax-only"]) == 0

    out = capsys.readouterr().out
    assert "Dangling Personas: 1" in out
    assert "[11111111] Legacy Note -> persona 'aegis-null' (not_an_id)" in out
