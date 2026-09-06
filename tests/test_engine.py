import os
import sys
import json
import pytest
from pathlib import Path
from datetime import date

# Add scripts directory to path
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from schema import MemorySchema, parse_frontmatter, dump_frontmatter
from vault import get_vault_path, load_env
from search import search_graph
from navigate import navigate
from indexer import load_vault
from validate import validate_file

# ---------------------------------------------------------
# Schema & Type Coercion Tests
# ---------------------------------------------------------

def test_schema_coercion_unquoted_int_id():
    """Verify unquoted integer IDs (e.g. 0, 1) coerce to 8-character zero-padded strings."""
    m = MemorySchema(
        id=0,
        title="Test Root",
        date="2026-09-01",
        summary="Test summary",
        type="declarative",
        status="active"
    )
    assert m.id == "00000000"

    m2 = MemorySchema(
        id=12345,
        title="Numeric ID",
        date="2026-09-01",
        summary="Test summary",
        type="declarative",
        status="active"
    )
    assert m2.id == "00012345"

def test_schema_coercion_datetime_date():
    """Verify datetime.date objects coerce to ISO YYYY-MM-DD strings."""
    today = date(2026, 9, 5)
    m = MemorySchema(
        id="a1b2c3d4",
        title="Date Test",
        date=today,
        summary="Testing date coercion",
        type="episodic",
        status="active"
    )
    assert m.date == "2026-09-05"

def test_schema_defaults_and_null_coercion():
    """Verify parents and tags default to empty lists and accept None without error."""
    m = MemorySchema(
        id="a1b2c3d4",
        title="Null Coercion",
        date="2026-09-01",
        summary="Testing defaults",
        type="declarative",
        status="active",
        parents=None,
        tags=None
    )
    assert m.parents == []
    assert m.tags == []

def test_schema_int_parents_coercion():
    """Verify integer parents inside YAML lists are coerced to 8-char strings."""
    m = MemorySchema(
        id="a1b2c3d4",
        title="Parent Coercion",
        date="2026-09-01",
        summary="Testing parent coercion",
        type="prospective",
        status="active",
        parents=[0, 1, "00000002"]
    )
    assert m.parents == ["00000000", "00000001", "00000002"]

def test_schema_open_tail_preservation(tmp_path):
    """Verify custom metadata fields are retained and dumped correctly."""
    m = MemorySchema(
        id="a1b2c3d4",
        title="Open Tail",
        date="2026-09-01",
        summary="Testing open tail",
        type="prospective",
        status="active",
        urgency="high",
        assignee="alice",
        custom_metrics={"complexity": 3}
    )
    data = m.model_dump()
    assert data["urgency"] == "high"
    assert data["assignee"] == "alice"
    assert data["custom_metrics"]["complexity"] == 3

    dumped = dump_frontmatter(m, "# Body\n\nSome body text.")
    assert "urgency: high" in dumped
    assert "assignee: alice" in dumped

    # Re-parse to verify round-trip retention
    test_file = tmp_path / "test_open_tail.md"
    test_file.write_text(dumped, encoding="utf-8")
    reparsed = parse_frontmatter(test_file)
    assert getattr(reparsed, "urgency") == "high"
    assert getattr(reparsed, "assignee") == "alice"

def test_parse_frontmatter_utf8_bom(tmp_path):
    """Verify UTF-8 BOM encoding is handled transparently."""
    content = '\ufeff---\nid: "a1b2c3d4"\ntitle: BOM Test\ndate: "2026-09-01"\nsummary: Testing BOM\ntype: declarative\nstatus: active\n---\n\n# Body'
    test_file = tmp_path / "bom_test.md"
    test_file.write_text(content, encoding="utf-8")
    m = parse_frontmatter(test_file)
    assert m.id == "a1b2c3d4"
    assert m.title == "BOM Test"

# ---------------------------------------------------------
# Zero-Fallback Vault Path Resolution Tests
# ---------------------------------------------------------

def test_vault_path_missing_env_halts(monkeypatch):
    """Verify missing VAULT_PATH exits with code 1."""
    monkeypatch.delenv("VAULT_PATH", raising=False)
    monkeypatch.setattr("vault.find_env_file", lambda: None)

    with pytest.raises(SystemExit) as exc_info:
        get_vault_path(require_root=True)
    assert exc_info.value.code == 1

def test_vault_path_nonexistent_directory_halts(monkeypatch, tmp_path):
    """Verify non-existent VAULT_PATH directory exits with code 1."""
    non_existent = tmp_path / "does_not_exist"
    monkeypatch.setenv("VAULT_PATH", str(non_existent))

    with pytest.raises(SystemExit) as exc_info:
        get_vault_path(require_root=True)
    assert exc_info.value.code == 1

def test_vault_path_missing_root_node_halts(monkeypatch, tmp_path):
    """Verify missing 00000000-root.md exits with code 1 when require_root=True."""
    empty_vault = tmp_path / "empty_vault"
    empty_vault.mkdir()
    monkeypatch.setenv("VAULT_PATH", str(empty_vault))

    with pytest.raises(SystemExit) as exc_info:
        get_vault_path(require_root=True)
    assert exc_info.value.code == 1

def test_vault_path_valid(monkeypatch, tmp_path):
    """Verify valid vault directory with 00000000-root.md succeeds."""
    vault = tmp_path / "valid_vault"
    vault.mkdir()
    (vault / "00000000-root.md").write_text("---\nid: '00000000'\ntitle: Root\ndate: '2026-09-01'\nsummary: Root\ntype: declarative\nstatus: active\n---\n", encoding="utf-8")
    monkeypatch.setenv("VAULT_PATH", str(vault))

    resolved = get_vault_path(require_root=True)
    assert resolved == vault

# ---------------------------------------------------------
# Search & Navigation Tests
# ---------------------------------------------------------

def test_search_multi_token_matching(capsys):
    """Verify multi-token query matches across non-contiguous words."""
    # Test query 'aws failure' against real vault
    search_graph(query="aws failure")
    captured = capsys.readouterr()
    results = json.loads(captured.out)
    assert len(results) >= 1
    ids = [r["id"] for r in results]
    assert "9bf7fa35" in ids

def test_search_status_filtering(capsys):
    """Verify search filters by status."""
    search_graph(query="work", status="active")
    captured = capsys.readouterr()
    results = json.loads(captured.out)
    assert len(results) >= 1
    for r in results:
        assert r["status"] == "active"

def test_navigate_includes_status_and_tags(capsys):
    """Verify navigation output includes status and tags."""
    navigate(node_id="00000001", direction="down")
    captured = capsys.readouterr()
    results = json.loads(captured.out)
    assert len(results) >= 1
    for child in results:
        assert "status" in child
        assert "tags" in child
        assert "inherited_persona" in child

def test_navigate_invalid_node_exits():
    """Verify navigate with invalid node ID exits with code 1."""
    with pytest.raises(SystemExit) as exc_info:
        navigate(node_id="nonexistent_id", direction="up")
    assert exc_info.value.code == 1

# ---------------------------------------------------------
# Validation Script Tests
# ---------------------------------------------------------

def test_validate_file_passes_real_vault():
    """Verify validate_file passes on real vault root memory."""
    vault_dir = get_vault_path(require_root=True)
    root_file = vault_dir / "00000000-root.md"
    assert validate_file(root_file) is True

def test_validate_file_fails_malformed(tmp_path):
    """Verify validate_file returns False on invalid markdown."""
    bad_file = tmp_path / "bad.md"
    bad_file.write_text("No frontmatter at all", encoding="utf-8")
    assert validate_file(bad_file) is False
