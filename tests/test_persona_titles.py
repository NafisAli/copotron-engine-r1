"""
Retrieval surfaces return the Inherited Persona's id together with its Persona
Definition's title (Progressive Disclosure: the profile body is not embedded).
A Dangling Persona yields a null title and never fails retrieval.
"""

import json
from pathlib import Path
from typing import Optional

import pytest

from copotron.cli import main

from copotron.core.indexer import load_vault
from copotron.core.navigate import navigate
from copotron.system_two.search import search_graph
from copotron.system_two.domains import get_domain_hubs
from copotron.system_two.crystallize import suggest_parents
from copotron.system_one import client as system_one_client
from copotron.system_one.client import SystemOneClient
from copotron.system_one.providers.mock import MockProvider

PERSONA_ID = "c19b60a6"
VALID = "11111111"  # names the Persona Definition by id
DANGLING = "22222222"  # names a persona by free-text name (legacy)
NO_PERSONA = "33333333"


def _write_memory(
    vault_dir: Path,
    memory_id: str,
    title: str,
    tags: list[str],
    parents: list[str],
    persona: Optional[str] = None,
    summary: str = "Test memory.",
):
    persona_line = f"persona: '{persona}'\n" if persona is not None else ""
    parents_yaml = ", ".join(f"'{p}'" for p in parents)
    content = (
        "---\n"
        f"id: '{memory_id}'\n"
        f"title: {title}\n"
        "date: '2026-09-01'\n"
        f"summary: {summary}\n"
        "type: declarative\n"
        "status: active\n"
        f"parents: [{parents_yaml}]\n"
        f"tags: [{', '.join(tags)}]\n"
        f"{persona_line}"
        "---\n\n"
        f"# {title}\n"
    )
    slug = title.lower().replace(" ", "-")
    (vault_dir / f"{memory_id}-{slug}.md").write_text(content, encoding="utf-8")


@pytest.fixture
def vault(tmp_path, monkeypatch):
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    _write_memory(vault_dir, "00000000", "Root", ["root"], parents=[])
    _write_memory(vault_dir, PERSONA_ID, "Aegis Null", ["persona", "aegis-null"], parents=["00000000"])
    _write_memory(vault_dir, VALID, "Firmware Hub", ["domain"], parents=["00000000"], persona=PERSONA_ID,
                  summary="Firmware notes owned by a defined persona.")
    _write_memory(vault_dir, DANGLING, "Legacy Hub", ["domain"], parents=["00000000"], persona="aegis-null",
                  summary="Legacy notes naming their persona by free text.")
    _write_memory(vault_dir, NO_PERSONA, "Plain Hub", ["domain"], parents=["00000000"],
                  summary="Notes with no persona at all.")
    monkeypatch.setenv("VAULT_PATH", str(vault_dir))
    load_vault(vault_dir, silent=True)
    return vault_dir


def _by_id(results: list[dict]) -> dict[str, dict]:
    return {r["id"]: r for r in results}


def test_navigate_returns_inherited_persona_id_and_title(vault):
    results = _by_id(navigate("00000000", "down", print_output=False))

    assert results[VALID]["inherited_persona"] == PERSONA_ID
    assert results[VALID]["inherited_persona_title"] == "Aegis Null"
    assert results[DANGLING]["inherited_persona"] == "aegis-null"
    assert results[DANGLING]["inherited_persona_title"] is None
    assert results[NO_PERSONA]["inherited_persona"] is None
    assert results[NO_PERSONA]["inherited_persona_title"] is None


def test_search_by_id_returns_inherited_persona_title(vault):
    results = _by_id(search_graph(query=f"{VALID} {DANGLING}", print_output=False))

    assert results[VALID]["inherited_persona_title"] == "Aegis Null"
    assert results[DANGLING]["inherited_persona"] == "aegis-null"
    assert results[DANGLING]["inherited_persona_title"] is None


def test_search_by_keyword_returns_inherited_persona_title(vault):
    results = _by_id(search_graph(query="notes", print_output=False))

    assert results[VALID]["inherited_persona"] == PERSONA_ID
    assert results[VALID]["inherited_persona_title"] == "Aegis Null"
    assert results[DANGLING]["inherited_persona_title"] is None
    assert results[NO_PERSONA]["inherited_persona_title"] is None


def test_domains_return_inherited_persona_title(vault):
    hubs = _by_id(get_domain_hubs(vault))

    assert hubs[VALID]["inherited_persona"] == PERSONA_ID
    assert hubs[VALID]["inherited_persona_title"] == "Aegis Null"
    assert hubs[DANGLING]["inherited_persona"] == "aegis-null"
    assert hubs[DANGLING]["inherited_persona_title"] is None
    assert hubs[NO_PERSONA]["inherited_persona_title"] is None


def test_suggest_parents_returns_inherited_persona_title(vault, monkeypatch):
    # Stub System One so no model is called; reranking is not under test here.
    monkeypatch.setattr(
        system_one_client, "_GLOBAL_CLIENT", SystemOneClient(provider=MockProvider(), use_cache=False)
    )

    candidates = _by_id(suggest_parents("notes", limit=10, vault_dir=vault))

    assert candidates[VALID]["inherited_persona"] == PERSONA_ID
    assert candidates[VALID]["inherited_persona_title"] == "Aegis Null"
    assert candidates[DANGLING]["inherited_persona"] == "aegis-null"
    assert candidates[DANGLING]["inherited_persona_title"] is None


def _line_for(output: str, memory_id: str) -> str:
    return next(line for line in output.splitlines() if f"[{memory_id}]" in line)


def test_cli_navigate_text_shows_persona_title(vault, capsys):
    assert main(["navigate", "00000000"]) == 0
    out = capsys.readouterr().out

    assert "persona: Aegis Null [c19b60a6]" in _line_for(out, VALID)
    assert "persona: aegis-null (dangling)" in _line_for(out, DANGLING)
    assert "persona" not in _line_for(out, NO_PERSONA)


def test_cli_navigate_json_includes_persona_title(vault, capsys):
    assert main(["navigate", "00000000", "--json"]) == 0
    results = _by_id(json.loads(capsys.readouterr().out))

    assert results[VALID]["inherited_persona_title"] == "Aegis Null"


def test_cli_search_text_shows_persona_title(vault, capsys):
    assert main(["search", "notes"]) == 0
    out = capsys.readouterr().out

    assert "persona: Aegis Null [c19b60a6]" in _line_for(out, VALID)
    assert "persona: aegis-null (dangling)" in _line_for(out, DANGLING)


def test_cli_search_json_includes_persona_title(vault, capsys):
    assert main(["search", "notes", "--json"]) == 0
    results = _by_id(json.loads(capsys.readouterr().out))

    assert results[DANGLING]["inherited_persona_title"] is None
    assert results[VALID]["inherited_persona_title"] == "Aegis Null"


def test_cli_domains_text_shows_persona_title(vault, capsys):
    assert main(["domains"]) == 0
    out = capsys.readouterr().out

    assert "persona: Aegis Null [c19b60a6]" in _line_for(out, VALID)
    assert "persona: aegis-null (dangling)" in _line_for(out, DANGLING)
    assert "persona" not in _line_for(out, NO_PERSONA)


def test_cli_suggest_parents_text_shows_persona_title(vault, monkeypatch, capsys):
    monkeypatch.setattr(
        system_one_client, "_GLOBAL_CLIENT", SystemOneClient(provider=MockProvider(), use_cache=False)
    )

    assert main(["crystallize", "--suggest-parents", "notes", "--limit", "10"]) == 0
    out = capsys.readouterr().out

    assert "persona: Aegis Null [c19b60a6]" in _line_for(out, VALID)
    assert "persona: aegis-null (dangling)" in _line_for(out, DANGLING)
