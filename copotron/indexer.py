import os
import sys
import json
import time
import heapq
import hashlib
from pathlib import Path
from copotron.schema import parse_frontmatter_and_body, _read_frontmatter_stream
from copotron.vault import get_vault_path
from copotron.db import get_db_path, init_db

def compute_frontmatter_hash(frontmatter_text: str) -> str:
    """Normalize line endings to LF and return SHA-256 hex digest."""
    normalized = frontmatter_text.replace("\r\n", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

def read_frontmatter_chunk(file_path: Path) -> str:
    """Stream frontmatter lines up to the closing delimiter without reading the body."""
    with open(file_path, "r", encoding="utf-8-sig") as f:
        yaml_lines = _read_frontmatter_stream(f, file_path)
    return "".join(yaml_lines)

def scan_vault_files(vault_dir: Path) -> dict[str, tuple[Path, float]]:
    """
    Fast filesystem scan via os.scandir collecting markdown files and mtimes.
    Returns mapping: posix_rel_path -> (absolute_path, st_mtime).
    """
    files = {}

    def _scan(current_dir: Path):
        try:
            with os.scandir(current_dir) as it:
                for entry in it:
                    if entry.name.startswith("."):
                        continue
                    if entry.name.lower() in ("readme.md", "license.md", "contributing.md"):
                        continue
                    if entry.is_file() and entry.name.endswith(".md"):
                        rel_posix = Path(entry.path).relative_to(vault_dir).as_posix()
                        files[rel_posix] = (Path(entry.path), entry.stat().st_mtime)
                    elif entry.is_dir():
                        _scan(Path(entry.path))
        except OSError:
            pass

    _scan(vault_dir)
    return files

def load_vault(vault_dir: Path | None = None, silent: bool = False) -> dict:
    """
    Incrementally synchronize Markdown vault memories into SQLite local index (.index.sqlite3).
    Returns in-memory graph dict for backwards compatibility.
    """
    start_time = time.perf_counter()
    if vault_dir is None:
        vault_dir = get_vault_path(require_root=True)

    db_path = get_db_path(vault_dir)
    conn = init_db(db_path)

    # -------------------------------------------------------------------------
    # Phase 1: Discovery & Diff
    # -------------------------------------------------------------------------
    # Load cached memory records from SQLite
    cur = conn.execute("""
    SELECT id, file_path, title, date, summary, type, status, persona, inherited_persona,
           tags_json, open_tail_json, parents_json, mtime, hash
    FROM memories;
    """)
    cached_rows = cur.fetchall()
    db_by_path = {row["file_path"]: dict(row) for row in cached_rows}
    db_by_id = {row["id"]: dict(row) for row in cached_rows}

    # Fast scan of disk files
    disk_files = scan_vault_files(vault_dir)

    graph = {}
    dirty_nodes = {}
    mtime_updates = []
    core_keys = {"id", "title", "date", "summary", "type", "status", "parents", "tags", "persona"}

    for rel_path, (abs_path, stat_mtime) in disk_files.items():
        if rel_path in db_by_path:
            cached = db_by_path[rel_path]
            # Compare mtime with tolerance for float rounding
            if abs(stat_mtime - cached["mtime"]) < 1e-4:
                # Cache hit: Unchanged file, reuse cached metadata in RAM
                try:
                    parents = json.loads(cached.get("parents_json", "[]"))
                except Exception:
                    parents = []
                try:
                    tags = json.loads(cached.get("tags_json", "[]"))
                except Exception:
                    tags = []

                graph[cached["id"]] = {
                    "id": cached["id"],
                    "file_path": cached["file_path"],
                    "title": cached["title"],
                    "date": cached["date"],
                    "summary": cached["summary"],
                    "type": cached["type"],
                    "status": cached["status"],
                    "parents": parents,
                    "tags": tags,
                    "persona": cached["persona"],
                    "children": [],
                    "inherited_persona": cached["inherited_persona"]
                }
                continue

            # Mtime differed: check frontmatter hash
            try:
                fm_text = read_frontmatter_chunk(abs_path)
                fm_hash = compute_frontmatter_hash(fm_text)
            except Exception as e:
                print(f"Skipping {abs_path.name} (frontmatter read error): {e}", file=sys.stderr)
                continue

            if fm_hash == cached["hash"]:
                # Content unchanged (e.g. git checkout/touch bumped mtime)
                mtime_updates.append((stat_mtime, cached["id"]))
                try:
                    parents = json.loads(cached.get("parents_json", "[]"))
                except Exception:
                    parents = []
                try:
                    tags = json.loads(cached.get("tags_json", "[]"))
                except Exception:
                    tags = []

                graph[cached["id"]] = {
                    "id": cached["id"],
                    "file_path": cached["file_path"],
                    "title": cached["title"],
                    "date": cached["date"],
                    "summary": cached["summary"],
                    "type": cached["type"],
                    "status": cached["status"],
                    "parents": parents,
                    "tags": tags,
                    "persona": cached["persona"],
                    "children": [],
                    "inherited_persona": cached["inherited_persona"]
                }
                continue

        # File is new or frontmatter content changed
        try:
            memory, body = parse_frontmatter_and_body(abs_path)
            fm_text = read_frontmatter_chunk(abs_path)
            fm_hash = compute_frontmatter_hash(fm_text)
        except Exception as e:
            print(f"Skipping {abs_path.name}: {e}", file=sys.stderr)
            continue

        raw_dict = memory.model_dump()
        open_tail = {k: v for k, v in raw_dict.items() if k not in core_keys}

        node_data = {
            "id": memory.id,
            "file_path": rel_path,
            "title": memory.title,
            "date": memory.date,
            "summary": memory.summary,
            "type": memory.type,
            "status": memory.status,
            "parents": memory.parents,
            "tags": memory.tags,
            "persona": memory.persona,
            "children": [],
            "inherited_persona": memory.persona,
            "open_tail": open_tail,
            "mtime": stat_mtime,
            "hash": fm_hash,
            "body": body
        }
        graph[memory.id] = node_data
        dirty_nodes[memory.id] = node_data

    # Detect deleted files (in DB, absent on disk)
    deleted_ids = set()
    for rel_path, cached in db_by_path.items():
        if rel_path not in disk_files:
            deleted_ids.add(cached["id"])

    # -------------------------------------------------------------------------
    # Phase 2: DAG Resolution
    # -------------------------------------------------------------------------
    # Calculate Children (constant-time set accumulation, deterministically sorted)
    children_sets = {node_id: set() for node_id in graph}
    for node_id, node_data in graph.items():
        for parent_id in node_data["parents"]:
            if parent_id in graph:
                children_sets[parent_id].add(node_id)
            else:
                print(f"Warning: Parent '{parent_id}' not found for node '{node_id}' ({node_data['title']})")

    for node_id in graph:
        graph[node_id]["children"] = sorted(children_sets[node_id])

    # Calculate Persona Inheritance (Topological Sort - Kahn's Algorithm)
    in_degree = {
        node_id: sum(1 for p in node_data.get("parents", []) if p in graph)
        for node_id, node_data in graph.items()
    }

    queue = [node_id for node_id, deg in in_degree.items() if deg == 0]
    heapq.heapify(queue)
    processed_count = 0

    while queue:
        u = heapq.heappop(queue)
        processed_count += 1
        node = graph[u]

        if node.get("persona"):
            node["inherited_persona"] = node["persona"]
        else:
            inherited = None
            for parent_id in node.get("parents", []):
                if parent_id in graph and graph[parent_id].get("inherited_persona"):
                    inherited = graph[parent_id]["inherited_persona"]
                    break
            node["inherited_persona"] = inherited

        for child_id in node.get("children", []):
            if child_id in in_degree:
                in_degree[child_id] -= 1
                if in_degree[child_id] == 0:
                    heapq.heappush(queue, child_id)

    # Cycle Detection
    if processed_count < len(graph):
        cyclic_nodes = sorted([node_id for node_id, deg in in_degree.items() if deg > 0])
        print(f"Warning: Cycle detected involving nodes: {cyclic_nodes}", file=sys.stderr)
        for node_id in cyclic_nodes:
            node = graph[node_id]
            if node.get("persona"):
                node["inherited_persona"] = node["persona"]
            else:
                inherited = None
                for parent_id in node.get("parents", []):
                    if parent_id in graph and graph[parent_id].get("inherited_persona"):
                        inherited = graph[parent_id]["inherited_persona"]
                        break
                node["inherited_persona"] = inherited

    # -------------------------------------------------------------------------
    # Phase 3: Atomic Batch Commit (Single SQLite Transaction)
    # -------------------------------------------------------------------------
    # Check if inherited_persona changed for clean nodes
    persona_updates = []
    for node_id, node_data in graph.items():
        if node_id not in dirty_nodes and node_id in db_by_id:
            old_inherited = db_by_id[node_id].get("inherited_persona")
            new_inherited = node_data.get("inherited_persona")
            if old_inherited != new_inherited:
                persona_updates.append((new_inherited, node_id))

    needs_commit = bool(dirty_nodes or deleted_ids or mtime_updates or persona_updates)

    if needs_commit:
        with conn:
            # 1. Delete removed nodes
            if deleted_ids:
                placeholders = ",".join("?" for _ in deleted_ids)
                del_list = list(deleted_ids)
                conn.execute(f"DELETE FROM memories WHERE id IN ({placeholders});", del_list)
                conn.execute(
                    f"DELETE FROM memory_edges WHERE parent_id IN ({placeholders}) OR child_id IN ({placeholders});",
                    del_list + del_list
                )
                conn.execute(f"DELETE FROM memories_fts WHERE id IN ({placeholders});", del_list)

            # 2. Update mtimes for unchanged files whose timestamp changed
            for new_mtime, n_id in mtime_updates:
                conn.execute("UPDATE memories SET mtime = ? WHERE id = ?;", (new_mtime, n_id))

            # 3. Update shifted inherited personas for clean nodes
            for new_inherited, n_id in persona_updates:
                conn.execute("UPDATE memories SET inherited_persona = ? WHERE id = ?;", (new_inherited, n_id))

            # 4. Upsert dirty / new nodes into memories
            for node_id, data in dirty_nodes.items():
                conn.execute("""
                INSERT INTO memories (
                    id, file_path, title, date, summary, type, status, persona,
                    inherited_persona, tags_json, open_tail_json, parents_json, mtime, hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    file_path=excluded.file_path,
                    title=excluded.title,
                    date=excluded.date,
                    summary=excluded.summary,
                    type=excluded.type,
                    status=excluded.status,
                    persona=excluded.persona,
                    inherited_persona=excluded.inherited_persona,
                    tags_json=excluded.tags_json,
                    open_tail_json=excluded.open_tail_json,
                    parents_json=excluded.parents_json,
                    mtime=excluded.mtime,
                    hash=excluded.hash;
                """, (
                    data["id"], data["file_path"], data["title"], data["date"], data["summary"],
                    data["type"], data["status"], data["persona"], graph[node_id]["inherited_persona"],
                    json.dumps(data["tags"]), json.dumps(data["open_tail"]), json.dumps(data["parents"]),
                    data["mtime"], data["hash"]
                ))

                # Update memory_edges
                conn.execute("DELETE FROM memory_edges WHERE child_id = ?;", (node_id,))
                edge_rows = [(p, node_id) for p in data["parents"]]
                if edge_rows:
                    conn.executemany("INSERT OR IGNORE INTO memory_edges (parent_id, child_id) VALUES (?, ?);", edge_rows)

                # Update memories_fts
                conn.execute("DELETE FROM memories_fts WHERE id = ?;", (node_id,))
                tags_text = " ".join(data["tags"])
                conn.execute(
                    "INSERT INTO memories_fts (id, title, summary, tags, body) VALUES (?, ?, ?, ?, ?);",
                    (node_id, data["title"], data["summary"], tags_text, data["body"])
                )

    conn.close()

    if not silent:
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        print(f"Indexed {len(graph)} memories ({len(dirty_nodes)} updated/added, {len(deleted_ids)} deleted) in {elapsed_ms:.1f}ms to {db_path}")
    return graph

if __name__ == "__main__":
    load_vault()
