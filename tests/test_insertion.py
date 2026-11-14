"""
Insertion: `copotron implant insert <name> --attach <memory-id>` copies an
Implant's instructions.md into the vault as its Implant Instructions and
attaches them beneath a memory of the user's choosing (spec §7).
"""

import json
from datetime import date
from pathlib import Path

import pytest

from copotron.cli import main
from copotron.core.navigate import navigate
from copotron.core.schema import parse_frontmatter, parse_frontmatter_and_body
from copotron.core.vault import find_memory_file
from copotron.system_two.insertion import insert_implant

IMPLANT_ID = "61b7be77"

TEMPLATE = f"""---
title: Lantern Implant
summary: How to read the Lantern's light level and switch it on or off.
tags:
- lantern
- implant
implant_id: {IMPLANT_ID}
---

## Read the Light Level

Run `lantern level`.

## Switch the Lantern

Run `lantern on` or `lantern off`.
"""


def _write_memory(vault_dir: Path, memory_id: str, title: str, parents: list[str]) -> Path:
    content = (
        "---\n"
        f"id: '{memory_id}'\n"
        f"title: {title}\n"
        "date: '2026-09-01'\n"
        "summary: Test memory.\n"
        "type: declarative\n"
        "status: active\n"
        f"parents: {parents}\n"
        "---\n\n"
        f"# {title}\n"
    )
    path = vault_dir / f"{memory_id}-{title.lower().replace(' ', '-')}.md"
    path.write_text(content, encoding="utf-8")
    return path


@pytest.fixture
def vault(tmp_path, monkeypatch):
    """Root ── Workshop (0000000a)"""
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    monkeypatch.setenv("VAULT_PATH", str(vault_dir))
    _write_memory(vault_dir, "00000000", "Root", [])
    _write_memory(vault_dir, "0000000a", "Workshop", ["00000000"])
    return vault_dir


@pytest.fixture
def implants_dir(tmp_path):
    """An implants directory holding one Implant, `lantern`."""
    root = tmp_path / "implants"
    (root / "lantern").mkdir(parents=True)
    (root / "lantern" / "instructions.md").write_text(TEMPLATE, encoding="utf-8")
    return root


def test_insertion_creates_implant_instructions_from_the_template(vault, implants_dir):
    result = insert_implant(vault, implants_dir, "lantern", attach="0000000a")

    memory, body = parse_frontmatter_and_body(find_memory_file(vault, result["id"]))
    assert memory.type == "procedural"
    assert memory.title == "Lantern Implant"
    assert memory.summary == "How to read the Lantern's light level and switch it on or off."
    assert memory.tags == ["lantern", "implant"]
    assert memory.model_extra["implant_id"] == IMPLANT_ID
    assert memory.parents == ["0000000a"]
    assert memory.status == "active"
    assert memory.date == date.today().isoformat()
    assert "## Read the Light Level\n\nRun `lantern level`." in body
    assert "## Switch the Lantern" in body


def test_insertion_attaches_the_implant_instructions_to_the_chosen_memory(vault, implants_dir):
    result = insert_implant(vault, implants_dir, "lantern", attach="0000000a")

    assert parse_frontmatter(find_memory_file(vault, "0000000a")).implants == [result["id"]]


def test_inserted_implant_is_inherited_by_the_chosen_memory_and_its_descendants(vault, implants_dir):
    _write_memory(vault, "0000000b", "Bench", ["0000000a"])

    result = insert_implant(vault, implants_dir, "lantern", attach="0000000a")

    below_root = {r["id"]: r for r in navigate("00000000", "down", print_output=False)}
    below_workshop = {r["id"]: r for r in navigate("0000000a", "down", print_output=False)}
    assert below_root["0000000a"]["inherited_implants"] == [result["id"]]
    assert below_workshop["0000000b"]["inherited_implants"] == [result["id"]]


def _snapshot(vault_dir: Path) -> dict[str, str]:
    return {p.name: p.read_text(encoding="utf-8") for p in sorted(vault_dir.glob("*.md"))}


def test_insertion_refuses_an_implant_the_vault_already_holds(vault, implants_dir):
    first = insert_implant(vault, implants_dir, "lantern", attach="0000000a")
    before = _snapshot(vault)

    with pytest.raises(ValueError, match=first["id"]):
        insert_implant(vault, implants_dir, "lantern", attach="00000000")

    assert _snapshot(vault) == before


@pytest.mark.parametrize("name", ["beacon", "../implants", ""])
def test_insertion_refuses_a_name_that_is_no_implant(vault, implants_dir, name):
    before = _snapshot(vault)

    with pytest.raises(ValueError, match="lantern"):  # the error lists the Implants there are
        insert_implant(vault, implants_dir, name, attach="0000000a")

    assert _snapshot(vault) == before


@pytest.mark.parametrize(
    "template",
    [
        TEMPLATE.replace(f"implant_id: {IMPLANT_ID}\n", ""),
        TEMPLATE.replace(f"implant_id: {IMPLANT_ID}", "implant_id: Lantern"),
        TEMPLATE.replace("title: Lantern Implant\n", ""),
        "## Read the Light Level\n\nRun `lantern level`.\n",
    ],
    ids=["no implant_id", "implant_id not 8 hex", "no title", "no frontmatter"],
)
def test_insertion_refuses_a_malformed_template(vault, implants_dir, template):
    (implants_dir / "lantern" / "instructions.md").write_text(template, encoding="utf-8")
    before = _snapshot(vault)

    with pytest.raises(ValueError, match="instructions.md"):
        insert_implant(vault, implants_dir, "lantern", attach="0000000a")

    assert _snapshot(vault) == before


@pytest.mark.parametrize("attach", ["0000000f", "workshop"])
def test_insertion_refuses_to_attach_beneath_a_memory_that_does_not_exist(vault, implants_dir, attach):
    before = _snapshot(vault)

    with pytest.raises(ValueError, match=f"attach.*{attach}"):
        insert_implant(vault, implants_dir, "lantern", attach=attach)

    assert _snapshot(vault) == before


def test_insertion_refuses_to_attach_beneath_a_memory_it_cannot_read(vault, implants_dir):
    (vault / "0000000a-workshop.md").write_text("---\nid: '0000000a'\ntitle: [unclosed\n---\n", encoding="utf-8")
    before = _snapshot(vault)

    with pytest.raises(ValueError, match="0000000a"):
        insert_implant(vault, implants_dir, "lantern", attach="0000000a")

    assert _snapshot(vault) == before


# ---------------------------------------------------------
# CLI: copotron implant insert
# ---------------------------------------------------------

NMS_IMPLANT_ID = "61b7be77"  # implants/nms/instructions.md in this repo


def test_cli_inserts_the_nms_implant(vault, capsys):
    ret = main(["implant", "insert", "nms", "--attach", "0000000a", "--json"])

    assert ret == 0
    result = json.loads(capsys.readouterr().out)
    instructions = parse_frontmatter(find_memory_file(vault, result["id"]))
    assert instructions.title == "No Man's Sky Implant"
    assert instructions.model_extra["implant_id"] == NMS_IMPLANT_ID
    assert parse_frontmatter(find_memory_file(vault, "0000000a")).implants == [result["id"]]


def test_cli_reports_a_refused_insertion_on_stderr(vault, capsys):
    ret = main(["implant", "insert", "beacon", "--attach", "0000000a"])

    assert ret == 1
    captured = capsys.readouterr()
    assert captured.err.startswith("Error: 'beacon' is not an Implant.")
    assert "nms" in captured.err
    assert captured.out == ""
