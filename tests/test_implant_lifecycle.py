"""
The Implant lifecycle (spec §7): `copotron implant insert` (and re-insertion),
`run`, `remove` and `detach`.
"""

import json
import shutil
from datetime import date
from pathlib import Path

import pytest

from copotron.cli import main
from copotron.core.navigate import navigate
from copotron.core.schema import dump_frontmatter, parse_frontmatter, parse_frontmatter_and_body
from copotron.core.vault import find_memory_file
from copotron.system_two.implant_lifecycle import detach_implant, insert_implant, remove_implant, run_implant

IMPLANT_ID = "61b7be77"

# The lantern Implant's entry point: prints its arguments as JSON, leaves a
# marker that it ran, and exits 3 when given --short.
ENTRY_POINT = """import json, sys
from pathlib import Path
(Path(__file__).parent / "ran").write_text("yes")
print(json.dumps(sys.argv[1:]))
sys.exit(3 if "--short" in sys.argv else 0)
"""

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


def _write_memory(
    vault_dir: Path,
    memory_id: str,
    title: str,
    parents: list[str],
    implants: list[str] = (),
    memory_date: str = "2026-09-01",
) -> Path:
    content = (
        "---\n"
        f"id: '{memory_id}'\n"
        f"title: {title}\n"
        f"date: '{memory_date}'\n"
        "summary: Test memory.\n"
        "type: declarative\n"
        "status: active\n"
        f"parents: {parents}\n"
        f"implants: {list(implants)}\n"
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
    (root / "lantern" / "lantern.py").write_text(ENTRY_POINT, encoding="utf-8")
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


# ---------------------------------------------------------
# re-insertion
# ---------------------------------------------------------

def _hand_edit(vault_dir: Path, memory_id: str, old: str, new: str) -> None:
    """A hand edit of memory_id's file: replace old with new."""
    memory_file = find_memory_file(vault_dir, memory_id)
    text = memory_file.read_text(encoding="utf-8")
    assert old in text
    memory_file.write_text(text.replace(old, new), encoding="utf-8")


def _update_template(implants_dir: Path, old: str, new: str) -> None:
    template_file = implants_dir / "lantern" / "instructions.md"
    text = template_file.read_text(encoding="utf-8")
    assert old in text
    template_file.write_text(text.replace(old, new), encoding="utf-8")


def _instructions_files(vault_dir: Path) -> list[str]:
    return [p.name for p in sorted(vault_dir.glob("*.md")) if "implant_id:" in p.read_text(encoding="utf-8")]


def test_reinsertion_refreshes_template_sections_in_the_existing_implant_instructions(vault, implants_dir):
    first = insert_implant(vault, implants_dir, "lantern", attach="0000000a")
    _hand_edit(vault, first["id"], "Run `lantern level`.", "Run `lantern level`, twice.")
    _update_template(implants_dir, "Run `lantern level`.", "Run `lantern level --lux`.")

    result = insert_implant(vault, implants_dir, "lantern")

    assert result["id"] == first["id"]
    assert len(_instructions_files(vault)) == 1
    memory, body = parse_frontmatter_and_body(find_memory_file(vault, first["id"]))
    assert memory.parents == ["0000000a"]
    assert memory.date == first["date"]
    assert "## Read the Light Level\n\nRun `lantern level --lux`.\n\n## Switch the Lantern" in body
    assert "twice" not in body


def test_reinsertion_keeps_sections_the_user_added_where_they_are(vault, implants_dir):
    instructions = insert_implant(vault, implants_dir, "lantern", attach="0000000a")["id"]
    _hand_edit(vault, instructions, "## Switch the Lantern", "## Lantern Care\n\nTrim the wick.\n\n## Switch the Lantern")
    _hand_edit(vault, instructions, "`lantern off`.\n", "`lantern off`.\n\n### Night Mode\n\nDim it.\n")
    _update_template(implants_dir, "Run `lantern level`.", "Run `lantern level --lux`.")

    insert_implant(vault, implants_dir, "lantern")

    _, body = parse_frontmatter_and_body(find_memory_file(vault, instructions))
    assert body.strip() == (
        "## Read the Light Level\n\nRun `lantern level --lux`.\n\n"
        "## Lantern Care\n\nTrim the wick.\n\n"
        "## Switch the Lantern\n\nRun `lantern on` or `lantern off`.\n\n"
        "### Night Mode\n\nDim it."
    )


def test_reinsertion_puts_a_section_new_to_the_template_after_its_template_predecessor(vault, implants_dir):
    instructions = insert_implant(vault, implants_dir, "lantern", attach="0000000a")["id"]
    _hand_edit(vault, instructions, "## Switch the Lantern", "## Lantern Care\n\nTrim the wick.\n\n## Switch the Lantern")
    _update_template(implants_dir, "## Switch the Lantern", "## Refill the Lantern\n\nPour oil.\n\n## Switch the Lantern")

    insert_implant(vault, implants_dir, "lantern")

    _, body = parse_frontmatter_and_body(find_memory_file(vault, instructions))
    assert body.strip() == (
        "## Read the Light Level\n\nRun `lantern level`.\n\n"
        "## Refill the Lantern\n\nPour oil.\n\n"
        "## Lantern Care\n\nTrim the wick.\n\n"
        "## Switch the Lantern\n\nRun `lantern on` or `lantern off`."
    )


def test_reinsertion_refreshes_title_and_summary_and_unions_tags(vault, implants_dir):
    instructions = insert_implant(vault, implants_dir, "lantern", attach="0000000a")["id"]
    memory_file = find_memory_file(vault, instructions)
    memory, body = parse_frontmatter_and_body(memory_file)
    memory_file.write_text(dump_frontmatter(memory.model_copy(update={"tags": [*memory.tags, "night"]}), body), encoding="utf-8")
    _update_template(implants_dir, "title: Lantern Implant", "title: Lamp Implant")
    _update_template(implants_dir, "summary: How to read", "summary: How to dim and read")
    _update_template(implants_dir, "- implant\n", "- implant\n- light\n")

    insert_implant(vault, implants_dir, "lantern")

    renamed = find_memory_file(vault, instructions)
    assert renamed.name == f"{instructions}-lamp-implant.md"
    assert not memory_file.exists()
    memory = parse_frontmatter(renamed)
    assert memory.title == "Lamp Implant"
    assert memory.summary == "How to dim and read the Lantern's light level and switch it on or off."
    assert memory.tags == ["lantern", "implant", "light", "night"]


@pytest.mark.parametrize(
    "old, new, tags",
    [
        ("- lantern\n", "- glow\n- lantern\n", ["glow", "lantern", "implant"]),
        ("- implant\n", "- implant\n- light\n", ["lantern", "implant", "light"]),
    ],
    ids=["new first template tag goes at the top", "new tag goes after its template predecessor"],
)
def test_reinsertion_places_a_tag_new_to_the_template_like_a_new_section(vault, implants_dir, old, new, tags):
    instructions = insert_implant(vault, implants_dir, "lantern", attach="0000000a")["id"]
    _update_template(implants_dir, old, new)

    result = insert_implant(vault, implants_dir, "lantern")

    assert parse_frontmatter(find_memory_file(vault, instructions)).tags == tags
    assert result["tags"] == tags


@pytest.mark.parametrize(
    "attach, attached",
    [(None, ["0000000a"]), ("0000000b", ["0000000a", "0000000b"]), ("0000000a", ["0000000a"])],
    ids=["no --attach", "--attach a new memory", "--attach a memory already attached"],
)
def test_reinsertion_with_attach_only_adds_an_attachment(vault, implants_dir, attach, attached):
    instructions = insert_implant(vault, implants_dir, "lantern", attach="0000000a")["id"]
    _write_memory(vault, "0000000b", "Garden", ["00000000"])

    insert_implant(vault, implants_dir, "lantern", attach=attach)

    implants = {m: parse_frontmatter(find_memory_file(vault, m)).implants for m in ("0000000a", "0000000b")}
    assert implants == {m: [instructions] if m in attached else [] for m in ("0000000a", "0000000b")}
    assert parse_frontmatter(find_memory_file(vault, instructions)).parents == ["0000000a"]
    assert len(_instructions_files(vault)) == 1


def _body_text(memory_file: Path) -> str:
    """The raw text after a memory file's frontmatter."""
    return memory_file.read_text(encoding="utf-8").split("\n---\n", 1)[1]


def test_reinserting_an_unchanged_template_leaves_the_body_byte_identical(vault, implants_dir):
    instructions = insert_implant(vault, implants_dir, "lantern", attach="0000000a")["id"]
    before = _body_text(find_memory_file(vault, instructions))

    insert_implant(vault, implants_dir, "lantern")

    assert _body_text(find_memory_file(vault, instructions)) == before


def test_reinserting_an_unchanged_template_leaves_the_whole_file_byte_identical(vault, implants_dir):
    insert_implant(vault, implants_dir, "lantern", attach="0000000a")
    before = _snapshot(vault)

    insert_implant(vault, implants_dir, "lantern")

    assert _snapshot(vault) == before


@pytest.mark.parametrize("indent", ["", "     "], ids=["fence", "fence nested in a list item"])
def test_reinsertion_does_not_take_a_comment_in_a_fenced_block_for_a_heading(vault, implants_dir, indent):
    def fence(command: str) -> str:
        return f"- Run:\n{indent}```bash\n{indent}# run it\n{indent}{command}\n{indent}```\n"

    _update_template(implants_dir, "Run `lantern level`.\n", fence("lantern level"))
    _update_template(implants_dir, "Run `lantern on` or `lantern off`.\n", fence("lantern on"))
    instructions = insert_implant(vault, implants_dir, "lantern", attach="0000000a")["id"]
    _update_template(implants_dir, "lantern on\n", "lantern on --soft\n")

    insert_implant(vault, implants_dir, "lantern")

    _, body = parse_frontmatter_and_body(find_memory_file(vault, instructions))
    assert body.strip() == (
        f"## Read the Light Level\n\n{fence('lantern level')}\n"
        f"## Switch the Lantern\n\n{fence('lantern on --soft')}"
    ).strip()


def test_first_insertion_refuses_without_attach(vault, implants_dir):
    before = _snapshot(vault)

    with pytest.raises(ValueError, match="--attach"):
        insert_implant(vault, implants_dir, "lantern")

    assert _snapshot(vault) == before


def test_reinsertion_refuses_to_attach_to_a_memory_that_does_not_exist(vault, implants_dir):
    insert_implant(vault, implants_dir, "lantern", attach="0000000a")
    _update_template(implants_dir, "Run `lantern level`.", "Run `lantern level --lux`.")
    before = _snapshot(vault)

    with pytest.raises(ValueError, match="attach.*0000000f"):
        insert_implant(vault, implants_dir, "lantern", attach="0000000f")

    assert _snapshot(vault) == before


def test_reinsertion_refuses_when_a_hand_copy_duplicated_the_implant_instructions(vault, implants_dir):
    instructions = insert_implant(vault, implants_dir, "lantern", attach="0000000a")["id"]
    original = find_memory_file(vault, instructions)
    (vault / "0000000d-lantern-copy.md").write_text(
        original.read_text(encoding="utf-8").replace(instructions, "0000000d"), encoding="utf-8"
    )
    _update_template(implants_dir, "Run `lantern level`.", "Run `lantern level --lux`.")
    before = _snapshot(vault)

    with pytest.raises(ValueError, match="0000000d") as refusal:
        insert_implant(vault, implants_dir, "lantern")

    assert instructions in str(refusal.value)
    assert _snapshot(vault) == before


def test_reinsertion_restores_a_deleted_first_template_section_at_the_top(vault, implants_dir):
    instructions = insert_implant(vault, implants_dir, "lantern", attach="0000000a")["id"]
    _hand_edit(vault, instructions, "## Read the Light Level\n\nRun `lantern level`.\n\n", "")

    insert_implant(vault, implants_dir, "lantern")

    _, body = parse_frontmatter_and_body(find_memory_file(vault, instructions))
    assert body.strip() == (
        "## Read the Light Level\n\nRun `lantern level`.\n\n"
        "## Switch the Lantern\n\nRun `lantern on` or `lantern off`."
    )


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
# run
# ---------------------------------------------------------

def test_run_refuses_an_implant_the_vault_does_not_hold(vault, implants_dir):
    with pytest.raises(ValueError, match="insert"):
        run_implant(vault, implants_dir, "lantern", ["level"])

    assert not (implants_dir / "lantern" / "ran").exists()


@pytest.mark.parametrize("args, exit_code", [(["level", "--json"], 0), (["on", "--short"], 3)])
def test_run_passes_arguments_to_the_entry_point_and_returns_its_exit_code(vault, implants_dir, capfd, args, exit_code):
    insert_implant(vault, implants_dir, "lantern", attach="0000000a")

    assert run_implant(vault, implants_dir, "lantern", args) == exit_code
    assert json.loads(capfd.readouterr().out) == args


def test_run_refuses_an_implant_without_an_entry_point(vault, implants_dir):
    insert_implant(vault, implants_dir, "lantern", attach="0000000a")
    (implants_dir / "lantern" / "lantern.py").unlink()

    with pytest.raises(ValueError, match="lantern.py"):
        run_implant(vault, implants_dir, "lantern", ["level"])


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


def test_cli_reinserts_an_implant_the_vault_holds_without_attach(vault, implants_dir, monkeypatch, capsys):
    monkeypatch.setattr("copotron.cli.engine_implants_dir", lambda: implants_dir)
    instructions = insert_implant(vault, implants_dir, "lantern", attach="0000000a")["id"]

    ret = main(["implant", "insert", "lantern", "--json"])

    assert ret == 0
    result = json.loads(capsys.readouterr().out)
    assert (result["action"], result["id"]) == ("updated", instructions)


def test_cli_refuses_a_first_insertion_without_attach(vault, capsys):
    ret = main(["implant", "insert", "nms"])

    assert ret == 1
    captured = capsys.readouterr()
    assert captured.err.startswith("Error: this vault holds no Implant Instructions for 'nms' yet")
    assert captured.out == ""


# ---------------------------------------------------------
# CLI: copotron implant run
# ---------------------------------------------------------

def test_cli_refuses_to_run_an_implant_the_vault_does_not_hold(vault, capfd):
    ret = main(["implant", "run", "nms", "status"])

    assert ret == 2  # not 1, which nms uses for a short requisition
    captured = capfd.readouterr()
    assert captured.err.startswith("Error: this vault holds no Implant Instructions for 'nms'")
    assert captured.out == ""


def test_cli_run_hands_every_argument_to_the_implant(vault, implants_dir, monkeypatch, capfd):
    monkeypatch.setattr("copotron.cli.engine_implants_dir", lambda: implants_dir)
    insert_implant(vault, implants_dir, "lantern", attach="0000000a")

    ret = main(["implant", "run", "lantern", "on", "--short", "--json", "--help"])

    assert ret == 3
    assert json.loads(capfd.readouterr().out) == ["on", "--short", "--json", "--help"]


# ---------------------------------------------------------
# remove
# ---------------------------------------------------------

def test_removal_deletes_the_implant_instructions_and_every_attachment(vault, implants_dir):
    instructions = insert_implant(vault, implants_dir, "lantern", attach="0000000a")["id"]
    _write_memory(vault, "0000000b", "Garden", ["00000000"], implants=[instructions])

    result = remove_implant(vault, implants_dir, "lantern")

    assert result["id"] == instructions
    assert sorted(result["detached_from"]) == ["0000000a", "0000000b"]
    assert find_memory_file(vault, instructions) is None
    assert parse_frontmatter(find_memory_file(vault, "0000000a")).implants == []
    assert parse_frontmatter(find_memory_file(vault, "0000000b")).implants == []
    assert all(not r["inherited_implants"] for r in navigate("00000000", "down", print_output=False))


def test_removal_by_instructions_id_works_when_the_implant_folder_is_gone(vault, implants_dir):
    instructions = insert_implant(vault, implants_dir, "lantern", attach="0000000a")["id"]
    shutil.rmtree(implants_dir / "lantern")

    result = remove_implant(vault, implants_dir, instructions)

    assert result["id"] == instructions
    assert find_memory_file(vault, instructions) is None
    assert parse_frontmatter(find_memory_file(vault, "0000000a")).implants == []


@pytest.mark.parametrize(
    "target",
    ["beacon", "lantern", "0000000f", "0000000a"],
    ids=["no such implant", "implant not in the vault", "unknown id", "id of a memory that is no implant instructions"],
)
def test_removal_refuses_a_target_that_matches_no_implant_instructions(vault, implants_dir, target):
    before = _snapshot(vault)

    with pytest.raises(ValueError, match=target):
        remove_implant(vault, implants_dir, target)

    assert _snapshot(vault) == before


def test_removal_refuses_implant_instructions_a_hand_edit_gave_children(vault, implants_dir):
    instructions = insert_implant(vault, implants_dir, "lantern", attach="0000000a")["id"]
    _write_memory(vault, "0000000b", "Wick", [instructions])
    _write_memory(vault, "0000000c", "Oil", ["0000000a", instructions])
    before = _snapshot(vault)

    with pytest.raises(ValueError, match="children") as refusal:
        remove_implant(vault, implants_dir, "lantern")

    assert "0000000b" in str(refusal.value) and "0000000c" in str(refusal.value)
    assert _snapshot(vault) == before


def test_removal_by_name_refuses_when_a_hand_copy_duplicated_the_implant_instructions(vault, implants_dir):
    instructions = insert_implant(vault, implants_dir, "lantern", attach="0000000a")["id"]
    original = find_memory_file(vault, instructions)
    (vault / "0000000d-lantern-copy.md").write_text(
        original.read_text(encoding="utf-8").replace(instructions, "0000000d"), encoding="utf-8"
    )
    before = _snapshot(vault)

    with pytest.raises(ValueError, match="0000000d") as refusal:
        remove_implant(vault, implants_dir, "lantern")

    assert instructions in str(refusal.value)
    assert _snapshot(vault) == before


# ---------------------------------------------------------
# CLI: copotron implant remove
# ---------------------------------------------------------

def test_cli_removes_an_implant(vault, implants_dir, monkeypatch, capsys):
    monkeypatch.setattr("copotron.cli.engine_implants_dir", lambda: implants_dir)
    instructions = insert_implant(vault, implants_dir, "lantern", attach="0000000a")["id"]

    ret = main(["implant", "remove", "lantern", "--json"])

    assert ret == 0
    assert json.loads(capsys.readouterr().out) == {
        "id": instructions, "title": "Lantern Implant", "detached_from": ["0000000a"]
    }
    assert find_memory_file(vault, instructions) is None


def test_cli_reports_a_refused_removal_on_stderr(vault, capsys):
    ret = main(["implant", "remove", "nms"])

    assert ret == 1
    captured = capsys.readouterr()
    assert captured.err.startswith("Error: this vault holds no Implant Instructions for 'nms'")
    assert captured.out == ""


# ---------------------------------------------------------
# detach
# ---------------------------------------------------------

def test_detachment_from_a_memory_that_is_no_parent_only_ends_that_attachment(vault, implants_dir):
    instructions = insert_implant(vault, implants_dir, "lantern", attach="0000000a")["id"]
    _write_memory(vault, "0000000b", "Garden", ["00000000"], implants=[instructions])

    result = detach_implant(vault, implants_dir, "lantern", from_memory="0000000b")

    assert result["id"] == instructions
    assert result["removed"] is False
    assert parse_frontmatter(find_memory_file(vault, "0000000b")).implants == []
    assert parse_frontmatter(find_memory_file(vault, "0000000a")).implants == [instructions]
    assert parse_frontmatter(find_memory_file(vault, instructions)).parents == ["0000000a"]


def _set_parents(vault_dir: Path, memory_id: str, parents: list[str]) -> None:
    """A hand edit of memory_id's parents."""
    memory_file = find_memory_file(vault_dir, memory_id)
    memory, body = parse_frontmatter_and_body(memory_file)
    memory_file.write_text(dump_frontmatter(memory.model_copy(update={"parents": parents}), body), encoding="utf-8")


def test_detachment_from_one_of_two_parents_drops_only_that_parent(vault, implants_dir):
    instructions = insert_implant(vault, implants_dir, "lantern", attach="0000000a")["id"]
    _write_memory(vault, "0000000b", "Garden", ["00000000"], implants=[instructions])
    _set_parents(vault, instructions, ["0000000a", "0000000b"])

    result = detach_implant(vault, implants_dir, instructions, from_memory="0000000a")

    assert result["parents"] == ["0000000b"]
    assert parse_frontmatter(find_memory_file(vault, instructions)).parents == ["0000000b"]
    assert parse_frontmatter(find_memory_file(vault, "0000000a")).implants == []


@pytest.mark.parametrize(
    "garden_date, shed_date, new_parent",
    [("2026-09-05", "2026-08-01", "0000000c"), ("2026-08-01", "2026-08-01", "0000000b")],
    ids=["earliest date wins", "tie broken by id"],
)
def test_detachment_from_the_only_parent_moves_the_instructions_beneath_the_oldest_remaining_attachment(
    vault, implants_dir, garden_date, shed_date, new_parent
):
    instructions = insert_implant(vault, implants_dir, "lantern", attach="0000000a")["id"]
    _write_memory(vault, "0000000c", "Shed", ["00000000"], implants=[instructions], memory_date=shed_date)
    _write_memory(vault, "0000000b", "Garden", ["00000000"], implants=[instructions], memory_date=garden_date)

    result = detach_implant(vault, implants_dir, "lantern", from_memory="0000000a")

    assert result["parents"] == [new_parent]
    assert parse_frontmatter(find_memory_file(vault, instructions)).parents == [new_parent]
    assert parse_frontmatter(find_memory_file(vault, "0000000a")).implants == []


def test_detaching_the_last_attachment_removes_the_implant(vault, implants_dir):
    instructions = insert_implant(vault, implants_dir, "lantern", attach="0000000a")["id"]

    result = detach_implant(vault, implants_dir, "lantern", from_memory="0000000a")

    assert result["removed"] is True
    assert result["parents"] == []
    assert find_memory_file(vault, instructions) is None
    assert parse_frontmatter(find_memory_file(vault, "0000000a")).implants == []


@pytest.mark.parametrize(
    "from_memory", ["00000000", "0000000f"], ids=["memory that does not attach them", "unknown id"]
)
def test_detachment_refuses_a_memory_the_implant_instructions_are_not_attached_to(vault, implants_dir, from_memory):
    insert_implant(vault, implants_dir, "lantern", attach="0000000a")
    before = _snapshot(vault)

    with pytest.raises(ValueError, match=f"{from_memory}.*not attached"):
        detach_implant(vault, implants_dir, "lantern", from_memory=from_memory)

    assert _snapshot(vault) == before


# ---------------------------------------------------------
# CLI: copotron implant detach
# ---------------------------------------------------------

def test_cli_detaches_an_implant(vault, implants_dir, monkeypatch, capsys):
    monkeypatch.setattr("copotron.cli.engine_implants_dir", lambda: implants_dir)
    instructions = insert_implant(vault, implants_dir, "lantern", attach="0000000a")["id"]
    _write_memory(vault, "0000000b", "Garden", ["00000000"], implants=[instructions])

    ret = main(["implant", "detach", "lantern", "--from", "0000000a", "--json"])

    assert ret == 0
    assert json.loads(capsys.readouterr().out) == {
        "id": instructions,
        "title": "Lantern Implant",
        "detached_from": "0000000a",
        "parents": ["0000000b"],
        "removed": False,
    }


def test_cli_reports_a_refused_detachment_on_stderr(vault, implants_dir, monkeypatch, capsys):
    monkeypatch.setattr("copotron.cli.engine_implants_dir", lambda: implants_dir)
    insert_implant(vault, implants_dir, "lantern", attach="0000000a")

    ret = main(["implant", "detach", "lantern", "--from", "00000000"])

    assert ret == 1
    captured = capsys.readouterr()
    assert captured.err.startswith("Error: --from '00000000': Implant Instructions ")
    assert captured.out == ""
