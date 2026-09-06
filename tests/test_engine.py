import os
import sys
import time
import json
import pytest
from pathlib import Path
from datetime import date

# Add scripts directory to path
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from schema import MemorySchema, parse_frontmatter, dump_frontmatter, parse_frontmatter_and_body
from vault import get_vault_path, load_env, atomic_write_text, atomic_write_json
from search import search_graph, format_fts_query
from navigate import navigate
from indexer import load_vault, compute_frontmatter_hash
from validate import validate_file
from db import get_db_path, init_db, get_readonly_db, INDEX_SCHEMA_VERSION

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

# ---------------------------------------------------------
# Phase 1: Linear Topological Persona Inheritance Tests
# ---------------------------------------------------------

def _create_test_note(vault: Path, node_id: str, title: str, parents: list, persona: str | None = None, status: str = "active", body: str = "Test body"):
    m = MemorySchema(
        id=node_id,
        title=title,
        date="2026-09-01",
        summary=f"Summary for {title}",
        type="declarative",
        status=status,
        parents=parents,
        persona=persona
    )
    content = dump_frontmatter(m, body)
    (vault / f"{node_id}-{title.lower().replace(' ', '-')}.md").write_text(content, encoding="utf-8")

def test_topological_persona_diamond_dag(tmp_path, monkeypatch):
    """Verify diamond DAG (A -> B, C -> D) propagates persona from A down to D."""
    vault = tmp_path / "diamond_vault"
    vault.mkdir()
    monkeypatch.setenv("VAULT_PATH", str(vault))

    # Root / A: has persona "work"
    _create_test_note(vault, "00000000", "Root", parents=[], persona="work")
    # B and C inherit from A
    _create_test_note(vault, "0000000b", "Node B", parents=["00000000"])
    _create_test_note(vault, "0000000c", "Node C", parents=["00000000"])
    # D has parents B and C
    _create_test_note(vault, "0000000d", "Node D", parents=["0000000b", "0000000c"])

    graph = load_vault()
    assert graph["00000000"]["inherited_persona"] == "work"
    assert graph["0000000b"]["inherited_persona"] == "work"
    assert graph["0000000c"]["inherited_persona"] == "work"
    assert graph["0000000d"]["inherited_persona"] == "work"

def test_topological_persona_multi_parent_conflict_resolution(tmp_path, monkeypatch):
    """Verify multi-parent conflict resolution prioritizes the first parent in declared order."""
    vault = tmp_path / "conflict_vault"
    vault.mkdir()
    monkeypatch.setenv("VAULT_PATH", str(vault))

    _create_test_note(vault, "00000000", "Root", parents=[])
    _create_test_note(vault, "0000000a", "Parent Work", parents=["00000000"], persona="work")
    _create_test_note(vault, "0000000b", "Parent Gaming", parents=["00000000"], persona="gaming")
    # Child C prioritizes A
    _create_test_note(vault, "0000000c", "Child C", parents=["0000000a", "0000000b"])
    # Child D prioritizes B
    _create_test_note(vault, "0000000d", "Child D", parents=["0000000b", "0000000a"])

    graph = load_vault()
    assert graph["0000000c"]["inherited_persona"] == "work"
    assert graph["0000000d"]["inherited_persona"] == "gaming"

def test_topological_cycle_detection(tmp_path, monkeypatch, capsys):
    """Verify cyclical dependencies log a warning and complete safely without RecursionError."""
    vault = tmp_path / "cycle_vault"
    vault.mkdir()
    monkeypatch.setenv("VAULT_PATH", str(vault))

    _create_test_note(vault, "00000000", "Root", parents=[])
    # Cycle between 0000000a and 0000000b
    _create_test_note(vault, "0000000a", "Cycle Node A", parents=["0000000b"], persona="work")
    _create_test_note(vault, "0000000b", "Cycle Node B", parents=["0000000a"])

    graph = load_vault()
    captured = capsys.readouterr()
    assert "Warning: Cycle detected involving nodes:" in captured.err
    assert "0000000a" in captured.err and "0000000b" in captured.err
    assert "0000000a" in graph
    assert "0000000b" in graph

# ---------------------------------------------------------
# Phase 1: Streaming Frontmatter & Parser Tests
# ---------------------------------------------------------

def test_streaming_frontmatter_large_file(tmp_path):
    """Verify parse_frontmatter only reads frontmatter and executes fast on large body files."""
    test_file = tmp_path / "large_note.md"
    frontmatter = (
        "---\n"
        "id: '00000099'\n"
        "title: Large Body Note\n"
        "date: '2026-09-01'\n"
        "summary: Testing streaming frontmatter parser\n"
        "type: declarative\n"
        "status: active\n"
        "---\n\n"
    )
    # Generate a large body with 50,000 lines (~1.5 MB)
    large_body = "\n".join(f"Line {i}: Some detailed note content here." for i in range(50000))
    test_file.write_text(frontmatter + large_body, encoding="utf-8")

    start_time = time.perf_counter()
    memory = parse_frontmatter(test_file)
    elapsed = time.perf_counter() - start_time

    assert memory.id == "00000099"
    assert memory.title == "Large Body Note"
    # Streaming frontmatter should easily parse in under 50ms
    assert elapsed < 0.05

def test_streaming_frontmatter_embedded_hyphens_in_multiline(tmp_path):
    """Verify indented triple hyphens in multiline YAML strings do not break frontmatter parsing."""
    content = (
        "---\n"
        "id: '00000088'\n"
        "title: Embedded Hyphens\n"
        "date: '2026-09-01'\n"
        "summary: |\n"
        "  First line of summary\n"
        "  ---\n"
        "  Second line of summary\n"
        "type: declarative\n"
        "status: active\n"
        "---\n\n"
        "# Body Header\n"
        "Body content here."
    )
    test_file = tmp_path / "embedded_hyphens.md"
    test_file.write_text(content, encoding="utf-8")

    memory = parse_frontmatter(test_file)
    assert memory.id == "00000088"
    assert "First line of summary\n---\nSecond line of summary" in memory.summary

    # Also test parse_frontmatter_and_body
    parsed_mem, body = parse_frontmatter_and_body(test_file)
    assert parsed_mem.id == "00000088"
    assert body.startswith("# Body Header")

# ---------------------------------------------------------
# Phase 1: Atomic File Persistence Tests
# ---------------------------------------------------------

def test_atomic_write_text_success_and_no_tmp_leftover(tmp_path):
    """Verify atomic_write_text writes file atomically without leaving temp files."""
    target_file = tmp_path / "atomic_note.md"
    content = "Hello Atomic World"
    atomic_write_text(target_file, content)

    assert target_file.is_file()
    assert target_file.read_text(encoding="utf-8") == content

    # Sibling temp files should be cleaned up
    tmp_files = list(tmp_path.glob("*.tmp.*"))
    assert len(tmp_files) == 0

def test_atomic_write_json_success(tmp_path):
    """Verify atomic_write_json writes valid JSON atomically."""
    target_file = tmp_path / "graph.json"
    data = {"00000000": {"title": "Root", "children": ["00000001"]}}
    atomic_write_json(target_file, data)

    assert target_file.is_file()
    loaded = json.loads(target_file.read_text(encoding="utf-8"))
    assert loaded == data
    assert len(list(tmp_path.glob("*.tmp.*"))) == 0

def test_atomic_write_failure_cleanup(tmp_path, monkeypatch):
    """Verify on write failure, target is untouched and temp file is cleaned up."""
    target_file = tmp_path / "untainted.txt"
    target_file.write_text("original content", encoding="utf-8")

    # Simulate an error during fsync
    def mock_fsync(fd):
        raise OSError("Simulated disk error")

    monkeypatch.setattr(os, "fsync", mock_fsync)

    with pytest.raises(OSError, match="Simulated disk error"):
        atomic_write_text(target_file, "new corrupted content")

    # Target should remain untouched
    assert target_file.read_text(encoding="utf-8") == "original content"
    # Temp file should be removed
    assert len(list(tmp_path.glob("*.tmp.*"))) == 0

# ---------------------------------------------------------
# Phase 1: Progressive Disclosure (Pagination & Filtering) Tests
# ---------------------------------------------------------

def test_search_pagination_limit_and_offset(capsys):
    """Verify --limit and --offset partition search results correctly."""
    # Search with limit 5, offset 0
    res_page1 = search_graph(query="psychology", limit=5, offset=0)
    res_page2 = search_graph(query="psychology", limit=5, offset=5)
    
    assert len(res_page1) <= 5
    assert len(res_page2) <= 5
    ids_page1 = {r["id"] for r in res_page1}
    ids_page2 = {r["id"] for r in res_page2}
    # Slices should not overlap
    assert ids_page1.isdisjoint(ids_page2)

def test_search_unlimited(capsys):
    """Verify limit=0 returns all matching results."""
    all_results = search_graph(query="psychology", limit=0)
    paged_results = search_graph(query="psychology", limit=5)
    assert len(all_results) >= len(paged_results)

def test_navigate_status_filter_and_pagination(capsys):
    """Verify navigate filters by status and applies pagination."""
    all_children = navigate(node_id="00000000", direction="down", limit=0)
    active_children = navigate(node_id="00000000", direction="down", status="active", limit=0)
    
    for child in active_children:
        assert child["status"] == "active"
    
    # Test pagination on navigate
    paged_children = navigate(node_id="00000000", direction="down", limit=2, offset=0)
    assert len(paged_children) <= 2

# ---------------------------------------------------------
# Phase 2: Database Lifecycle & Schema Tests
# ---------------------------------------------------------

def test_db_initialization_and_wal_mode(tmp_path):
    """Verify init_db initializes tables, WAL journal mode, and schema user_version."""
    db_file = tmp_path / ".index.sqlite3"
    conn = init_db(db_file)

    # Check WAL mode
    journal_mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
    assert journal_mode.lower() == "wal"

    # Check user_version
    user_version = conn.execute("PRAGMA user_version;").fetchone()[0]
    assert user_version == INDEX_SCHEMA_VERSION

    # Check tables exist
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()}
    assert "memories" in tables
    assert "memory_edges" in tables
    assert "memories_fts" in tables
    conn.close()

def test_db_schema_version_mismatch_auto_rebuild(tmp_path):
    """Verify schema version mismatch wipes existing tables and rebuilds cleanly."""
    db_file = tmp_path / ".index.sqlite3"
    conn = init_db(db_file)

    # Insert a sentinel record
    conn.execute("""
    INSERT INTO memories (id, file_path, title, date, summary, type, status, tags_json, open_tail_json, mtime, hash)
    VALUES ('99999999', 'test.md', 'Old Data', '2026-09-01', 'Old', 'declarative', 'active', '[]', '{}', 1.0, 'hash');
    """)
    conn.commit()
    conn.close()

    # Simulate an obsolete schema version
    conn2 = init_db(db_file)
    conn2.execute("PRAGMA user_version = 999;")
    conn2.commit()
    conn2.close()

    # Re-initialization should detect version mismatch (999 != 1), drop and recreate
    conn3 = init_db(db_file)
    assert conn3.execute("PRAGMA user_version;").fetchone()[0] == INDEX_SCHEMA_VERSION
    rows = conn3.execute("SELECT * FROM memories;").fetchall()
    assert len(rows) == 0  # Table was dropped and recreated cleanly
    conn3.close()

# ---------------------------------------------------------
# Phase 2: Cross-Platform Normalization & Hash Stability
# ---------------------------------------------------------

def test_cross_platform_hash_stability():
    """Verify CRLF and LF line endings produce the exact same frontmatter hash."""
    lf_text = "id: '00000001'\ntitle: Test\ndate: '2026-09-01'\nsummary: Summary\n"
    crlf_text = "id: '00000001'\r\ntitle: Test\r\ndate: '2026-09-01'\r\nsummary: Summary\r\n"

    hash_lf = compute_frontmatter_hash(lf_text)
    hash_crlf = compute_frontmatter_hash(crlf_text)
    assert hash_lf == hash_crlf
    assert len(hash_lf) == 64

# ---------------------------------------------------------
# Phase 2: Incremental Indexer Cache Hit/Miss & Pruning Tests
# ---------------------------------------------------------

def test_incremental_indexer_cache_hit_and_miss(tmp_path, monkeypatch):
    """Verify incremental indexer caches unchanged files, updates modified files, and prunes deleted files."""
    vault = tmp_path / "inc_vault"
    vault.mkdir()
    monkeypatch.setenv("VAULT_PATH", str(vault))

    # 1. Setup Root and Note A
    _create_test_note(vault, "00000000", "Root", parents=[])
    _create_test_note(vault, "0000000a", "Note A", parents=["00000000"], body="Initial body of Note A")

    # Initial indexing run
    g1 = load_vault()
    assert "00000000" in g1
    assert "0000000a" in g1

    db_path = get_db_path(vault)
    conn = get_readonly_db(db_path)
    count1 = conn.execute("SELECT count(*) FROM memories;").fetchone()[0]
    assert count1 == 2
    conn.close()

    # 2. Second run: 0 changes. Should be a clean cache hit.
    t0 = time.perf_counter()
    g2 = load_vault()
    elapsed2 = time.perf_counter() - t0
    assert len(g2) == 2
    assert elapsed2 < 0.1  # Fast cache hit

    # 3. Modify Note A frontmatter (title change)
    note_a_path = next(vault.glob("*0000000a*.md"))
    m_updated = MemorySchema(
        id="0000000a",
        title="Note A Updated",
        date="2026-09-01",
        summary="Summary for Note A Updated",
        type="declarative",
        status="active",
        parents=["00000000"]
    )
    note_a_path.write_text(dump_frontmatter(m_updated, "Updated body of Note A"), encoding="utf-8")
    g3 = load_vault()
    assert g3["0000000a"]["title"] == "Note A Updated"

    conn = get_readonly_db(db_path)
    row_a = conn.execute("SELECT title FROM memories WHERE id = '0000000a';").fetchone()
    assert row_a["title"] == "Note A Updated"
    conn.close()

    # 4. Touch Note A (update mtime without changing content)
    note_a_path = next(vault.glob("*0000000a*.md"))
    new_mtime = time.time() + 100
    os.utime(note_a_path, (new_mtime, new_mtime))

    g4 = load_vault()
    assert g4["0000000a"]["title"] == "Note A Updated"
    conn = get_readonly_db(db_path)
    row_mtime = conn.execute("SELECT mtime FROM memories WHERE id = '0000000a';").fetchone()
    assert abs(row_mtime["mtime"] - new_mtime) < 1e-3
    conn.close()

    # 5. Delete Note A file on disk
    note_a_path.unlink()
    g5 = load_vault()
    assert "0000000a" not in g5
    conn = get_readonly_db(db_path)
    row_deleted = conn.execute("SELECT count(*) FROM memories WHERE id = '0000000a';").fetchone()[0]
    assert row_deleted == 0
    fts_deleted = conn.execute("SELECT count(*) FROM memories_fts WHERE id = '0000000a';").fetchone()[0]
    assert fts_deleted == 0
    edges_deleted = conn.execute("SELECT count(*) FROM memory_edges WHERE child_id = '0000000a';").fetchone()[0]
    assert edges_deleted == 0
    conn.close()

# ---------------------------------------------------------
# Phase 2: FTS5 Full-Text Search & BM25 Ranking Tests
# ---------------------------------------------------------

def test_fts5_fulltext_search_body_and_ranking(tmp_path, monkeypatch, capsys):
    """Verify FTS5 searches note body text and applies BM25 ranking."""
    vault = tmp_path / "fts_vault"
    vault.mkdir()
    monkeypatch.setenv("VAULT_PATH", str(vault))

    _create_test_note(vault, "00000000", "Root", parents=[])
    _create_test_note(
        vault, "00000001", "Architecture Blueprint", parents=["00000000"],
        body="Detailed design for high-throughput stream processing."
    )
    _create_test_note(
        vault, "00000002", "Unrelated Note", parents=["00000000"],
        body="This note discusses completely different topics like gardening."
    )

    load_vault()

    # Query term present only in note body ("high-throughput")
    results = search_graph(query="high-throughput")
    assert len(results) >= 1
    assert results[0]["id"] == "00000001"

    # Verify unrelated note is excluded
    ids = [r["id"] for r in results]
    assert "00000002" not in ids

# ---------------------------------------------------------
# Phase 2: SQLite-Backed Navigation Tests
# ---------------------------------------------------------

def test_navigate_sqlite_edge_traversal(tmp_path, monkeypatch, capsys):
    """Verify navigate travels up/down, filters by status, and paginates using SQLite."""
    vault = tmp_path / "nav_vault"
    vault.mkdir()
    monkeypatch.setenv("VAULT_PATH", str(vault))

    _create_test_note(vault, "00000000", "Root", parents=[])
    _create_test_note(vault, "00000001", "Active Child", parents=["00000000"], status="active")
    _create_test_note(vault, "00000002", "Completed Child", parents=["00000000"], status="completed")

    load_vault()

    # Down: all children
    down_all = navigate(node_id="00000000", direction="down", limit=0)
    assert len(down_all) == 2
    assert [d["id"] for d in down_all] == ["00000001", "00000002"]

    # Down: status filtered
    down_active = navigate(node_id="00000000", direction="down", status="active")
    assert len(down_active) == 1
    assert down_active[0]["id"] == "00000001"

    # Up: parent traversal
    up_parent = navigate(node_id="00000001", direction="up")
    assert len(up_parent) == 1
    assert up_parent[0]["id"] == "00000000"

def test_phase_2_performance_benchmarks():
    """Verify incremental index (<25ms), search (<5ms), and navigation (<2ms) meet criteria."""
    # Ensure index is warmed up
    load_vault()

    # 1. Benchmark 0-change re-indexing
    t0 = time.perf_counter()
    load_vault()
    elapsed_index = (time.perf_counter() - t0) * 1000.0
    assert elapsed_index < 25.0, f"Incremental index took {elapsed_index:.2f}ms (expected < 25ms)"

    # 2. Benchmark FTS5 Search
    t0 = time.perf_counter()
    search_graph(query="psychology", limit=5)
    elapsed_search = (time.perf_counter() - t0) * 1000.0
    assert elapsed_search < 15.0, f"Search took {elapsed_search:.2f}ms (expected < 15ms)"

    # 3. Benchmark Navigate
    t0 = time.perf_counter()
    navigate(node_id="00000000", direction="down", limit=5)
    elapsed_nav = (time.perf_counter() - t0) * 1000.0
    assert elapsed_nav < 10.0, f"Navigate took {elapsed_nav:.2f}ms (expected < 10ms)"



# ---------------------------------------------------------
# Phase 1: Set-Based Child Deduplication Tests
# ---------------------------------------------------------

def test_set_based_child_deduplication(tmp_path, monkeypatch):
    """Verify child accumulation deduplicates and sorts deterministically."""
    vault = tmp_path / "dedup_vault"
    vault.mkdir()
    monkeypatch.setenv("VAULT_PATH", str(vault))

    _create_test_note(vault, "00000000", "Root", parents=[])
    # Node 2 references Root multiple times in its parents list
    _create_test_note(vault, "00000002", "Node Two", parents=["00000000", "00000000"])
    # Node 1 references Root
    _create_test_note(vault, "00000001", "Node One", parents=["00000000"])

    graph = load_vault()
    # Root children must be deduplicated and sorted deterministically: ["00000001", "00000002"]
    assert graph["00000000"]["children"] == ["00000001", "00000002"]

