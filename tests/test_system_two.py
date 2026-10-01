import pytest
from pathlib import Path

from copotron.system_one.providers.mock import MockProvider
from copotron.system_one.client import SystemOneClient
from copotron.system_one.types import ChoiceAnswer
from copotron.system_two.splicer import parse_markdown_sections, splice_markdown_sections
from copotron.system_two.audit import audit_vault_health
from copotron.core.indexer import load_vault
from copotron.system_two.crystallize import create_memory_node, update_memory_node


def test_parse_markdown_sections():
    doc = """
Preamble text here.

# Section 1
Content of section 1.

## Section 2
Content of section 2.
"""
    sections = parse_markdown_sections(doc)
    assert len(sections) == 3
    assert sections[0][1] == ""  # Preamble
    assert "Preamble" in sections[0][2]
    assert sections[1][1] == "Section 1"
    assert "section 1" in sections[1][2]
    assert sections[2][1] == "Section 2"


def test_splice_markdown_replace_and_extend():
    existing = """# Architecture
Old architecture description.

## Hardware
ESP32 board."""

    incoming_update = """# Architecture
New architecture with S3 payload buffering.

### Network
ESP-NOW protocol."""

    # Test replace: System One votes 'replace' for Architecture
    mock = MockProvider()
    mock.set_answer("splice_architecture", ChoiceAnswer(choice="replace", confidence=0.9))
    client = SystemOneClient(provider=mock, use_cache=False)

    spliced = splice_markdown_sections(existing, incoming_update, client=client)
    assert "New architecture with S3 payload buffering" in spliced
    assert "Old architecture description" not in spliced
    assert "## Hardware\n\nESP32 board" in spliced
    assert "### Network\n\nESP-NOW protocol" in spliced


def test_vault_health_audit(tmp_path):
    vault_dir = tmp_path / "audit_vault"
    vault_dir.mkdir(parents=True, exist_ok=True)

    # 1. Create root
    create_memory_node(
        vault_dir=vault_dir,
        title="Root",
        memory_type="declarative",
        node_id="00000000",
        parents=[],
    )

    # 2. Create node with broken parent
    create_memory_node(
        vault_dir=vault_dir,
        title="Broken Parent Node",
        memory_type="declarative",
        node_id="11111111",
        parents=["deadbeef"],
    )

    # 3. Create orphan node
    create_memory_node(
        vault_dir=vault_dir,
        title="Orphan Node",
        memory_type="declarative",
        node_id="22222222",
        parents=[],
    )

    load_vault(vault_dir, silent=True)

    report = audit_vault_health(vault_dir=vault_dir, check_semantic=False)
    assert report["total_nodes"] == 3
    assert len(report["broken_parent_references"]) == 1
    assert report["broken_parent_references"][0]["missing_parent"] == "deadbeef"
    assert len(report["orphan_nodes"]) == 1
    assert report["orphan_nodes"][0]["id"] == "22222222"
    assert report["healthy"] is False


def test_create_with_auto_type(tmp_path):
    vault_dir = tmp_path / "autotype_vault"
    vault_dir.mkdir(parents=True, exist_ok=True)

    mock = MockProvider()
    mock.set_answer("mem_type", ChoiceAnswer(choice="procedural", confidence=0.9))
    client = SystemOneClient(provider=mock, use_cache=False)

    node = create_memory_node(
        vault_dir=vault_dir,
        title="Deploy Script Instructions",
        summary="How to run deployment",
        body="Step 1: run deploy.sh",
        auto_type=True,
    )
    assert node["type"] in ("procedural", "declarative")
