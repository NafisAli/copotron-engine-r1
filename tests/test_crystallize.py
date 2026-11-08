import os
import sys
import json
import pytest
from pathlib import Path

from copotron.core.schema import parse_frontmatter, parse_frontmatter_and_body
from copotron.core.vault import atomic_write_text
from copotron.system_two.crystallize import (
    clean_slug,
    generate_unique_id,
    create_memory_node,
    crystallize_manifest,
    suggest_parents,
    resolve_auto_parent,
)
from copotron.core.db import init_db, get_db_path
from copotron.core.indexer import load_vault
from copotron.system_two.search import search_graph
from copotron.core.navigate import navigate


@pytest.fixture
def mock_vault(tmp_path, monkeypatch):
    """Create a temporary initialized vault for isolation."""
    vault_dir = tmp_path / "test_vault"
    vault_dir.mkdir(parents=True, exist_ok=True)

    # Create 00000000-root.md
    root_content = (
        "---\n"
        "id: '00000000'\n"
        "title: Root\n"
        "date: '2026-09-01'\n"
        "summary: Origin of test memory graph.\n"
        "type: declarative\n"
        "status: active\n"
        "parents: []\n"
        "tags: [root]\n"
        "---\n\n"
        "# Root\n"
    )
    (vault_dir / "00000000-root.md").write_text(root_content, encoding="utf-8")

    # Create a domain hub
    hub_content = (
        "---\n"
        "id: '00000001'\n"
        "title: Hardware Hub\n"
        "date: '2026-09-01'\n"
        "summary: Hardware and embedded systems.\n"
        "type: declarative\n"
        "status: active\n"
        "parents: ['00000000']\n"
        "tags: [hardware]\n"
        "---\n\n"
        "# Hardware Hub\n"
    )
    (vault_dir / "00000001-hardware-hub.md").write_text(hub_content, encoding="utf-8")

    # Override VAULT_PATH
    monkeypatch.setenv("VAULT_PATH", str(vault_dir))
    load_vault(vault_dir)

    return vault_dir


def test_clean_slug():
    assert clean_slug("Raspberry Pi 4B & I2C Setup!") == "raspberry-pi-4b-i2c-setup"
    assert clean_slug("   Spaces   and___UnderScores   ") == "spaces-and-underscores"
    assert clean_slug("???!!!") == "untitled"
    # Max length 50
    long_title = "a" * 100
    assert len(clean_slug(long_title)) == 50


def test_generate_unique_id_collision_avoidance(tmp_path):
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()

    # Pre-occupy first generated ID
    raw_id = generate_unique_id(vault_dir, "Test Node", "2026-09-07")
    (vault_dir / f"{raw_id}-test.md").write_text("dummy", encoding="utf-8")

    # Second call for the same title/date must yield a different ID
    second_id = generate_unique_id(vault_dir, "Test Node", "2026-09-07")
    assert len(second_id) == 8
    assert second_id != raw_id


def test_create_single_memory_node(mock_vault):
    node = create_memory_node(
        vault_dir=mock_vault,
        title="Capacitive Moisture Sensor",
        memory_type="declarative",
        summary="Wiring specs for capacitive soil moisture probe v1.2.",
        body="## Pinout\n- VCC: 3.3V\n- GND: Pin 9\n- AOUT: ADS1115 A0\n",
        parents=["00000001"],
        tags=["sensor", "i2c"],
        status="active",
        node_date="2026-09-07",
    )

    created_file = Path(node["file_path"])
    assert created_file.is_file()
    assert created_file.name.endswith("-capacitive-moisture-sensor.md")
    assert len(node["id"]) == 8

    # Verify frontmatter parsing
    schema, body = parse_frontmatter_and_body(created_file)
    assert schema.id == node["id"]
    assert schema.title == "Capacitive Moisture Sensor"
    assert schema.type == "declarative"
    assert schema.parents == ["00000001"]
    assert "sensor" in schema.tags
    assert "ADS1115 A0" in body


def test_create_node_explicit_id_and_open_tail(mock_vault):
    node = create_memory_node(
        vault_dir=mock_vault,
        title="Custom ID Node",
        memory_type="prospective",
        summary="Testing explicit ID coercion and open tail metadata.",
        node_id="123",  # Should coerce to 00000123
        parents=["00000000"],
        extra_fields={"priority": "p1", "estimated_hours": 4},
    )

    assert node["id"] == "00000123"
    created_file = Path(node["file_path"])
    schema = parse_frontmatter(created_file)
    assert schema.id == "00000123"
    assert schema.model_extra.get("priority") == "p1"
    assert schema.model_extra.get("estimated_hours") == 4


def test_crystallize_manifest_with_ref_resolution(mock_vault):
    manifest = [
        {
            "temp_ref": "pi_project",
            "title": "Smart Plant Irrigation System",
            "type": "prospective",
            "summary": "Automated plant watering node using Raspberry Pi Zero 2W.",
            "parents": ["00000001"],
            "tags": ["project", "diy"],
            "body": "Overarching project hub."
        },
        {
            "title": "Moisture Sensor I2C Wiring Spec",
            "type": "declarative",
            "summary": "ADS1115 ADC and capacitive sensor wiring specification.",
            "parents": ["$pi_project"],
            "tags": ["hardware", "wiring"],
            "body": "Connect ADS1115 to SDA Pin 3, SCL Pin 5."
        },
        {
            "title": "Order Capacitive Sensors and ADS1115",
            "type": "prospective",
            "summary": "Purchase hardware from supplier.",
            "parents": ["$pi_project"],
            "tags": ["task"],
            "status": "active"
        }
    ]

    created = crystallize_manifest(mock_vault, manifest, auto_index=True)
    assert len(created) == 3

    project_node = created[0]
    spec_node = created[1]
    task_node = created[2]

    # Verify reference resolution: children should have project's assigned ID as parent
    assert spec_node["parents"] == [project_node["id"]]
    assert task_node["parents"] == [project_node["id"]]

    # Verify indexing in SQLite: project node should have 2 children in navigation
    down_edges = navigate(node_id=project_node["id"], direction="down")
    child_ids = {e["id"] for e in down_edges}
    assert spec_node["id"] in child_ids
    assert task_node["id"] in child_ids

    # Search should find the new nodes
    search_res = search_graph(query="ADS1115 capacitive")
    assert any(r["id"] == spec_node["id"] for r in search_res)


def test_auto_parent_resolution(mock_vault):
    # Should resolve to 00000001 (Hardware Hub) because query matches "hardware"
    parents = resolve_auto_parent("Hardware Debugging Tools", "Oscilloscopes and logic analyzers.", mock_vault)
    assert parents == ["00000001"]

    # Fallback to root for completely unrelated query
    fallback_parents = resolve_auto_parent("Quantum Cooking Recipe", "Baking bread in another galaxy.", mock_vault)
    assert fallback_parents == ["00000000"]


def test_cli_single_node_and_json(mock_vault, monkeypatch, capsys):
    from copotron.system_two.crystallize import main

    test_args = [
        "crystallize.py",
        "--title", "CLI Created Node",
        "--type", "procedural",
        "--summary", "Created via CLI entrypoint.",
        "--parent", "00000001",
        "--tag", "cli",
        "--json-output",
    ]
    monkeypatch.setattr(sys, "argv", test_args)
    main()

    captured = capsys.readouterr()
    output = json.loads(captured.out)
    assert output["title"] == "CLI Created Node"
    assert output["type"] == "procedural"
    assert output["parents"] == ["00000001"]


def test_cli_manifest_file(mock_vault, monkeypatch, capsys, tmp_path):
    from copotron.system_two.crystallize import main

    manifest_file = tmp_path / "manifest.json"
    manifest_data = [
        {
            "title": "Batch Node Alpha",
            "type": "declarative",
            "summary": "First batch node.",
            "parents": ["00000001"],
        },
        {
            "title": "Batch Node Beta",
            "type": "prospective",
            "summary": "Second batch node.",
            "parents": ["00000001"],
        },
    ]
    manifest_file.write_text(json.dumps(manifest_data), encoding="utf-8")

    test_args = [
        "crystallize.py",
        "--manifest", str(manifest_file),
        "--json-output",
    ]
    monkeypatch.setattr(sys, "argv", test_args)
    main()

    captured = capsys.readouterr()
    output = json.loads(captured.out)
    assert len(output) == 2
    assert output[0]["title"] == "Batch Node Alpha"
    assert output[1]["title"] == "Batch Node Beta"


def test_update_existing_memory_node_in_place(mock_vault):
    from copotron.system_two.crystallize import create_or_update_memory_node, find_memory_file

    # 1. Create original node
    created = create_or_update_memory_node(
        vault_dir=mock_vault,
        title="Initial Architecture Design",
        memory_type="declarative",
        summary="Initial architecture using Redis.",
        body="Original body text.",
        parents=["00000001"],
        tags=["architecture", "v1"],
    )
    node_id = created["id"]
    orig_file = Path(created["file_path"])
    assert orig_file.is_file()

    # 2. Update the node in place with title change and appended body
    updated = create_or_update_memory_node(
        vault_dir=mock_vault,
        node_id=node_id,
        title="Updated Architecture Design Hybrid S3",
        summary="Revised architecture using Redis + S3 hybrid.",
        body="Appended revision notes: S3 pre-signed URLs.",
        append_body=True,
        tags=["s3"],
    )
    assert updated["action"] == "updated"
    assert updated["id"] == node_id

    # Verify old file was cleanly removed and new file exists
    assert not orig_file.exists()
    new_file = Path(updated["file_path"])
    assert new_file.is_file()
    assert new_file.name.endswith("-updated-architecture-design-hybrid-s3.md")

    # Verify content
    schema, body = parse_frontmatter_and_body(new_file)
    assert schema.id == node_id
    assert schema.title == "Updated Architecture Design Hybrid S3"
    assert schema.summary == "Revised architecture using Redis + S3 hybrid."
    assert "architecture" in schema.tags
    assert "s3" in schema.tags
    assert "Original body text." in body
    assert "Appended revision notes: S3 pre-signed URLs." in body


def test_manifest_batch_with_update(mock_vault):
    from copotron.system_two.crystallize import create_or_update_memory_node, crystallize_manifest

    # Create base node
    base = create_or_update_memory_node(
        vault_dir=mock_vault,
        title="Base Hardware BOM",
        memory_type="declarative",
        summary="Original BOM.",
        parents=["00000001"],
        body="NEMA 17 Stepper.",
    )

    manifest = [
        {
            "id": base["id"],
            "summary": "Updated BOM with pancake NEMA 17.",
            "body": "Pancake NEMA 17 (24mm thickness).",
            "append_body": True,
        },
        {
            "title": "Camera Slider Mount CAD Spec",
            "type": "procedural",
            "summary": "CAD mount for pancake motor.",
            "parents": [base["id"]],
            "tags": ["cad", "3d-printing"],
        }
    ]

    results = crystallize_manifest(mock_vault, manifest, auto_index=True)
    assert len(results) == 2
    assert results[0]["action"] == "updated"
    assert results[0]["id"] == base["id"]
    assert results[1]["action"] == "created"
    assert results[1]["parents"] == [base["id"]]




# ---------------------------------------------------------------------------
# Persona references a Persona Definition by id
# ---------------------------------------------------------------------------

PERSONA_DEFINITION_ID = "c19b60a6"


@pytest.fixture
def persona_vault(mock_vault):
    """mock_vault plus a Persona Definition (declarative, tagged persona)."""
    content = (
        "---\n"
        f"id: '{PERSONA_DEFINITION_ID}'\n"
        "title: Aegis Null\n"
        "date: '2026-09-01'\n"
        "summary: Terse, security-minded assistant voice.\n"
        "type: declarative\n"
        "status: active\n"
        "parents: ['00000000']\n"
        "tags: [persona, aegis-null]\n"
        "---\n\n"
        "# Aegis Null\n"
    )
    (mock_vault / f"{PERSONA_DEFINITION_ID}-aegis-null.md").write_text(content, encoding="utf-8")
    return mock_vault


INVALID_PERSONAS = [
    pytest.param("aegis-null", id="not-an-id"),
    pytest.param("deadbeef", id="unknown-id"),
    pytest.param("00000001", id="not-a-persona-definition"),
]


@pytest.mark.parametrize("persona", INVALID_PERSONAS)
def test_create_rejects_persona_that_is_not_a_persona_definition(persona_vault, persona):
    files_before = set(persona_vault.glob("*.md"))

    with pytest.raises(ValueError, match="Persona Definition"):
        create_memory_node(
            vault_dir=persona_vault,
            title="Guarded Memory",
            memory_type="declarative",
            parents=["00000000"],
            persona=persona,
        )

    assert set(persona_vault.glob("*.md")) == files_before


def test_create_accepts_persona_definition_id(persona_vault):
    node = create_memory_node(
        vault_dir=persona_vault,
        title="Guarded Memory",
        memory_type="declarative",
        parents=["00000000"],
        persona=PERSONA_DEFINITION_ID,
    )

    assert parse_frontmatter(Path(node["file_path"])).persona == PERSONA_DEFINITION_ID


def test_manifest_references_persona_definition_created_in_same_batch(mock_vault):
    manifest = [
        {
            "temp_ref": "aegis",
            "title": "Aegis Null",
            "type": "declarative",
            "summary": "Terse, security-minded assistant voice.",
            "parents": ["00000000"],
            "tags": ["persona", "aegis-null"],
        },
        {
            "title": "Firewall Runbook",
            "type": "procedural",
            "summary": "Steps to harden the home firewall.",
            "parents": ["00000001"],
            "persona": "$aegis",
        },
    ]

    definition, runbook = crystallize_manifest(mock_vault, manifest, auto_index=False)

    assert parse_frontmatter(Path(runbook["file_path"])).persona == definition["id"]


@pytest.mark.parametrize("persona", INVALID_PERSONAS)
def test_manifest_rejects_invalid_persona_before_writing_anything(persona_vault, persona):
    files_before = set(persona_vault.glob("*.md"))
    manifest = [
        {
            "title": "Valid Sibling",
            "type": "declarative",
            "parents": ["00000000"],
            "persona": PERSONA_DEFINITION_ID,
        },
        {
            "title": "Guarded Memory",
            "type": "declarative",
            "parents": ["00000000"],
            "persona": persona,
        },
    ]

    with pytest.raises(ValueError, match="Persona Definition"):
        crystallize_manifest(persona_vault, manifest, auto_index=False)

    assert set(persona_vault.glob("*.md")) == files_before


def test_manifest_rejects_temp_ref_persona_that_is_not_a_persona_definition(mock_vault):
    manifest = [
        {"temp_ref": "plain", "title": "Plain Fact", "type": "declarative", "parents": ["00000000"]},
        {"title": "Guarded Memory", "type": "declarative", "parents": ["00000000"], "persona": "$plain"},
    ]

    with pytest.raises(ValueError, match="Persona Definition"):
        crystallize_manifest(mock_vault, manifest, auto_index=False)


def _write_legacy_persona_memory(vault_dir: Path) -> Path:
    """A memory written before persona became an id reference."""
    legacy = vault_dir / "0000beef-legacy-memory.md"
    legacy.write_text(
        "---\n"
        "id: 0000beef\n"
        "title: Legacy Memory\n"
        "date: '2026-09-01'\n"
        "summary: Written when persona held a name.\n"
        "type: declarative\n"
        "status: active\n"
        "parents: ['00000000']\n"
        "tags: []\n"
        "persona: aegis-null\n"
        "---\n\n"
        "Original body.\n",
        encoding="utf-8",
    )
    return legacy


@pytest.mark.parametrize("persona", INVALID_PERSONAS)
def test_update_rejects_persona_that_is_not_a_persona_definition(persona_vault, persona):
    from copotron.system_two.crystallize import create_or_update_memory_node

    target = persona_vault / "00000001-hardware-hub.md"
    content_before = target.read_text(encoding="utf-8")

    with pytest.raises(ValueError, match="Persona Definition"):
        create_or_update_memory_node(vault_dir=persona_vault, node_id="00000001", persona=persona)

    assert target.read_text(encoding="utf-8") == content_before


def test_update_accepts_persona_definition_id(persona_vault):
    from copotron.system_two.crystallize import create_or_update_memory_node

    updated = create_or_update_memory_node(
        vault_dir=persona_vault, node_id="00000001", persona=PERSONA_DEFINITION_ID
    )

    assert parse_frontmatter(Path(updated["file_path"])).persona == PERSONA_DEFINITION_ID


def test_update_leaves_existing_dangling_persona_untouched_when_persona_not_supplied(persona_vault):
    from copotron.system_two.crystallize import create_or_update_memory_node

    _write_legacy_persona_memory(persona_vault)

    updated = create_or_update_memory_node(
        vault_dir=persona_vault, node_id="0000beef", body="Appended note.", append_body=True
    )

    assert parse_frontmatter(Path(updated["file_path"])).persona == "aegis-null"


def test_manifest_update_rejects_invalid_persona(persona_vault):
    target = persona_vault / "00000001-hardware-hub.md"
    content_before = target.read_text(encoding="utf-8")

    with pytest.raises(ValueError, match="Persona Definition"):
        crystallize_manifest(persona_vault, [{"id": "00000001", "persona": "aegis-null"}], auto_index=False)

    assert target.read_text(encoding="utf-8") == content_before


def test_manifest_rejects_persona_whose_definition_is_demoted_earlier_in_batch(persona_vault):
    files_before = {p: p.read_text(encoding="utf-8") for p in persona_vault.glob("*.md")}
    manifest = [
        {"id": PERSONA_DEFINITION_ID, "type": "procedural"},
        {"title": "Guarded Memory", "type": "declarative", "parents": ["00000000"], "persona": PERSONA_DEFINITION_ID},
    ]

    with pytest.raises(ValueError, match="Persona Definition"):
        crystallize_manifest(persona_vault, manifest, auto_index=False)

    assert {p: p.read_text(encoding="utf-8") for p in persona_vault.glob("*.md")} == files_before


# ---------------------------------------------------------------------------
# Writes never produce an Orphan (a non-Root memory with no parents)
# ---------------------------------------------------------------------------


def test_create_rejects_non_root_memory_without_parents(mock_vault):
    files_before = set(mock_vault.glob("*.md"))

    with pytest.raises(ValueError, match=r"Orphan.*--parent.*--auto-parent"):
        create_memory_node(vault_dir=mock_vault, title="Campaign Plan", memory_type="prospective")

    assert set(mock_vault.glob("*.md")) == files_before


def test_create_rejects_parent_that_does_not_exist(mock_vault):
    files_before = set(mock_vault.glob("*.md"))

    with pytest.raises(ValueError, match="'deadbeef'"):
        create_memory_node(
            vault_dir=mock_vault, title="Campaign Plan", memory_type="prospective", parents=["00000001", "deadbeef"]
        )

    assert set(mock_vault.glob("*.md")) == files_before


@pytest.mark.parametrize(
    "orphan_item",
    [
        pytest.param({"title": "Campaign Plan", "type": "prospective"}, id="parents-missing"),
        pytest.param({"title": "Campaign Plan", "type": "prospective", "parents": []}, id="parents-empty"),
        pytest.param({"title": "Campaign Plan", "type": "prospective", "parents": ["deadbeef"]}, id="parent-unknown"),
    ],
)
def test_manifest_rejects_orphan_before_writing_anything(mock_vault, orphan_item):
    files_before = set(mock_vault.glob("*.md"))
    manifest = [
        {"title": "Valid Sibling", "type": "declarative", "parents": ["00000001"]},
        orphan_item,
    ]

    with pytest.raises(ValueError, match="Orphan|'deadbeef'"):
        crystallize_manifest(mock_vault, manifest, auto_index=False)

    assert set(mock_vault.glob("*.md")) == files_before


@pytest.mark.parametrize(
    "parents, error",
    [
        pytest.param([], "Orphan", id="drops-all-parents"),
        pytest.param(["deadbeef"], "'deadbeef'", id="parent-unknown"),
    ],
)
def test_update_rejects_parents_that_would_orphan_the_memory(mock_vault, parents, error):
    from copotron.system_two.crystallize import create_or_update_memory_node

    target = mock_vault / "00000001-hardware-hub.md"
    content_before = target.read_text(encoding="utf-8")

    with pytest.raises(ValueError, match=error):
        create_or_update_memory_node(vault_dir=mock_vault, node_id="00000001", parents=parents)

    assert target.read_text(encoding="utf-8") == content_before


def test_manifest_update_rejects_dropping_all_parents(mock_vault):
    target = mock_vault / "00000001-hardware-hub.md"
    content_before = target.read_text(encoding="utf-8")

    with pytest.raises(ValueError, match="Orphan"):
        crystallize_manifest(mock_vault, [{"id": "00000001", "parents": []}], auto_index=False)

    assert target.read_text(encoding="utf-8") == content_before


def test_manifest_accepts_parent_written_later_in_same_batch(mock_vault):
    manifest = [
        {"title": "Corvette Hull Notes", "type": "declarative", "parents": ["$campaign"]},
        {"temp_ref": "campaign", "title": "Campaign Plan", "type": "prospective", "parents": ["00000001"]},
    ]

    notes, campaign = crystallize_manifest(mock_vault, manifest, auto_index=False)

    assert parse_frontmatter(Path(notes["file_path"])).parents == [campaign["id"]]


def test_manifest_update_without_parents_keeps_existing_parents(mock_vault):
    updated, = crystallize_manifest(mock_vault, [{"id": "00000001", "summary": "Boards and motors."}], auto_index=False)

    assert parse_frontmatter(Path(updated["file_path"])).parents == ["00000000"]


def test_update_without_parents_leaves_existing_orphan_untouched(mock_vault):
    from copotron.system_two.crystallize import create_or_update_memory_node

    (mock_vault / "31f6706f-legacy-orphan.md").write_text(
        "---\n"
        "id: 31f6706f\n"
        "title: Legacy Orphan\n"
        "date: '2026-09-01'\n"
        "summary: Written before writes refused Orphans.\n"
        "type: prospective\n"
        "status: active\n"
        "parents: []\n"
        "---\n\n"
        "Original body.\n",
        encoding="utf-8",
    )

    updated = create_or_update_memory_node(vault_dir=mock_vault, node_id="31f6706f", status="completed")

    assert parse_frontmatter(Path(updated["file_path"])).parents == []


def test_create_with_auto_parent_and_no_parents_succeeds(mock_vault):
    node = create_memory_node(
        vault_dir=mock_vault,
        title="Hardware Debugging Tools",
        memory_type="declarative",
        summary="Oscilloscopes and logic analyzers.",
        auto_parent=True,
    )

    assert parse_frontmatter(Path(node["file_path"])).parents == ["00000001"]


def test_root_memory_may_have_no_parents(tmp_path):
    vault_dir = tmp_path / "fresh_vault"
    vault_dir.mkdir()

    root = create_memory_node(vault_dir=vault_dir, title="Root", memory_type="declarative", node_id="00000000")

    assert parse_frontmatter(Path(root["file_path"])).parents == []


def test_setup_init_creates_root_memory(tmp_path):
    from copotron.core.setup import create_root_memory

    vault_dir = tmp_path / "fresh_vault"
    vault_dir.mkdir()

    create_root_memory(vault_dir)

    root = parse_frontmatter(vault_dir / "00000000-root.md")
    assert root.id == "00000000"
    assert root.parents == []
