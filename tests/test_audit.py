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
    implants: Optional[list[str]] = None,
    implant_id: Optional[str] = None,
):
    persona_line = f"persona: '{persona}'\n" if persona is not None else ""
    implants_line = f"implants: [{', '.join(repr(i) for i in implants)}]\n" if implants is not None else ""
    implant_id_line = f"implant_id: '{implant_id}'\n" if implant_id is not None else ""
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
        f"{implants_line}"
        f"{implant_id_line}"
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


# ---------------------------------------------------------
# Dangling implant links
# ---------------------------------------------------------

NMS_INSTRUCTIONS = "4f2a9c1e"


@pytest.fixture
def implant_vault(vault):
    _write_memory(vault, NMS_INSTRUCTIONS, "NMS Instructions", memory_type="procedural", implant_id="9c0d1e2f")
    _write_memory(vault, "a1b2c3d4", "Plain Procedure", memory_type="procedural")
    return vault


def _dangling_implant_links(vault_dir: Path) -> list[dict]:
    return audit_vault_health(vault_dir=vault_dir, check_semantic=False)["dangling_implant_links"]


@pytest.mark.parametrize(
    "reference, problem",
    [
        ("nms", "not_an_id"),
        ("deadbeef", "unknown_id"),
        ("a1b2c3d4", "not_implant_instructions"),  # procedural, but no implant_id
        ("c19b60a6", "not_implant_instructions"),  # a Persona Definition
    ],
)
def test_reports_implant_link_that_identifies_no_implant_instructions(implant_vault, reference, problem):
    _write_memory(implant_vault, "11111111", "Campaign", implants=[NMS_INSTRUCTIONS, reference])

    assert _dangling_implant_links(implant_vault) == [
        {"id": "11111111", "title": "Campaign", "implant": reference, "problem": problem}
    ]


def test_valid_implant_link_and_no_implants_produce_no_findings(implant_vault):
    _write_memory(implant_vault, "11111111", "Campaign", implants=[NMS_INSTRUCTIONS])
    _write_memory(implant_vault, "22222222", "Plain Note")

    report = audit_vault_health(vault_dir=implant_vault, check_semantic=False)

    assert report["dangling_implant_links"] == []
    assert report["healthy"] is True


def test_dangling_implant_link_makes_vault_unhealthy(implant_vault):
    _write_memory(implant_vault, "11111111", "Campaign", implants=["deadbeef"])

    assert audit_vault_health(vault_dir=implant_vault, check_semantic=False)["healthy"] is False


def test_syntax_only_json_report_lists_dangling_implant_links(implant_vault, monkeypatch, capsys):
    monkeypatch.setenv("VAULT_PATH", str(implant_vault))
    _write_memory(implant_vault, "11111111", "Campaign", implants=["deadbeef"])

    assert main(["audit", "--syntax-only", "--json"]) == 0

    report = json.loads(capsys.readouterr().out)
    assert report["dangling_implant_links"] == [
        {"id": "11111111", "title": "Campaign", "implant": "deadbeef", "problem": "unknown_id"}
    ]


def test_syntax_only_text_report_lists_dangling_implant_links(implant_vault, monkeypatch, capsys):
    monkeypatch.setenv("VAULT_PATH", str(implant_vault))
    _write_memory(implant_vault, "11111111", "Campaign", implants=["deadbeef"])

    assert main(["audit", "--syntax-only"]) == 0

    out = capsys.readouterr().out
    assert "Dangling Implant Links: 1" in out
    assert "[11111111] Campaign -> implant 'deadbeef' (unknown_id)" in out


def test_syntax_only_text_report_says_when_no_implant_link_dangles(implant_vault, monkeypatch, capsys):
    monkeypatch.setenv("VAULT_PATH", str(implant_vault))

    assert main(["audit", "--syntax-only"]) == 0

    assert "Dangling Implant Links: None" in capsys.readouterr().out
