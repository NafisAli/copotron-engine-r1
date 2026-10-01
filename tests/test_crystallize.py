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


