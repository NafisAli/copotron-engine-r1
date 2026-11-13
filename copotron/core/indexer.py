import os
import sys
import json
import time
import heapq
import hashlib
from pathlib import Path
from copotron.core.schema import parse_frontmatter_and_body, _read_frontmatter_stream
from copotron.core.vault import get_vault_path
from copotron.core.db import get_db_path, init_db

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

def _json_list(text: str | None) -> list:
    """Decode a JSON array column, treating anything else as empty."""
    try:
        value = json.loads(text) if text else []
    except Exception:
        return []
    return value if isinstance(value, list) else []

def _node_from_cached_row(cached: dict) -> dict:
    """Rebuild a graph node from its index row, for a memory whose frontmatter is unchanged."""
    return {
        "id": cached["id"],
        "file_path": cached["file_path"],
        "title": cached["title"],
        "date": cached["date"],
        "summary": cached["summary"],
        "type": cached["type"],
        "status": cached["status"],
        "parents": _json_list(cached.get("parents_json")),
        "tags": _json_list(cached.get("tags_json")),
        "persona": cached["persona"],
        "implants": _json_list(cached.get("implants")),
        "children": [],
        "inherited_persona": cached["inherited_persona"],
        "inherited_implants": _json_list(cached.get("inherited_implants")),
    }

def _resolve_inherited_persona(node: dict, graph: dict) -> str | None:
    """
    Resolve a node's Inherited Persona: its own persona wins, otherwise the
    first declared parent (present in graph) with an Inherited Persona.
    """
    if node.get("persona"):
        return node["persona"]
    for parent_id in node.get("parents", []):
        if parent_id in graph and graph[parent_id].get("inherited_persona"):
            return graph[parent_id]["inherited_persona"]
    return None

def _resolve_inherited_implants(node: dict, graph: dict) -> list[str]:
    """
    Resolve a node's Inherited Implants once its parents are resolved: the
    union of its own implants and every parent's (present in graph) Inherited
    Implants. Unlike persona there is no override, so every ancestor counts.
    """
    inherited = set(node.get("implants", []))
    for parent_id in node.get("parents", []):
        if parent_id in graph:
            inherited.update(graph[parent_id].get("inherited_implants", []))
    return sorted(inherited)

def _union_implants_over_ancestors(node_id: str, graph: dict) -> list[str]:
    """
    Inherited Implants for a node in or below a cycle, whose parents never all
    resolve first: the union over every ancestor reachable through parents in graph.
    """
    inherited = set()
    seen = {node_id}
    stack = [node_id]
    while stack:
        current = graph[stack.pop()]
        inherited.update(current.get("implants", []))
        for parent_id in current.get("parents", []):
            if parent_id in graph and parent_id not in seen:
                seen.add(parent_id)
                stack.append(parent_id)
    return sorted(inherited)

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
    cur = conn.execute("""
    SELECT id, file_path, title, date, summary, type, status, persona, inherited_persona,
           implants, inherited_implants, tags_json, open_tail_json, parents_json, mtime, hash
    FROM memories;
    """)
    cached_rows = cur.fetchall()
    db_by_path = {row["file_path"]: dict(row) for row in cached_rows}
    db_by_id = {row["id"]: dict(row) for row in cached_rows}

    disk_files = scan_vault_files(vault_dir)

    graph = {}
    dirty_nodes = {}
    mtime_updates = []
    core_keys = {"id", "title", "date", "summary", "type", "status", "parents", "tags", "persona", "implants"}

    for rel_path, (abs_path, stat_mtime) in disk_files.items():
        if rel_path in db_by_path:
            cached = db_by_path[rel_path]
            if abs(stat_mtime - cached["mtime"]) < 1e-4:
                graph[cached["id"]] = _node_from_cached_row(cached)
                continue

            try:
                fm_text = read_frontmatter_chunk(abs_path)
                fm_hash = compute_frontmatter_hash(fm_text)
            except Exception as e:
                print(f"Skipping {abs_path.name} (frontmatter read error): {e}", file=sys.stderr)
                continue

            if fm_hash == cached["hash"]:
                mtime_updates.append((stat_mtime, cached["id"]))
                graph[cached["id"]] = _node_from_cached_row(cached)
                continue

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
            "implants": memory.implants,
            "children": [],
            "inherited_persona": memory.persona,
            "inherited_implants": [],
            "open_tail": open_tail,
            "mtime": stat_mtime,
            "hash": fm_hash,
            "body": body
        }
        graph[memory.id] = node_data
        dirty_nodes[memory.id] = node_data

    deleted_ids = set()
    for rel_path, cached in db_by_path.items():
        if rel_path not in disk_files:
            deleted_ids.add(cached["id"])

    # -------------------------------------------------------------------------
    # Phase 2: DAG Resolution
    # -------------------------------------------------------------------------
    children_sets = {node_id: set() for node_id in graph}
    for node_id, node_data in graph.items():
        for parent_id in node_data["parents"]:
            if parent_id in graph:
                children_sets[parent_id].add(node_id)
            else:
                print(f"Warning: Parent '{parent_id}' not found for node '{node_id}' ({node_data['title']})")

    for node_id in graph:
        graph[node_id]["children"] = sorted(children_sets[node_id])

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
        node["inherited_persona"] = _resolve_inherited_persona(node, graph)
        node["inherited_implants"] = _resolve_inherited_implants(node, graph)

        for child_id in node.get("children", []):
            if child_id in in_degree:
                in_degree[child_id] -= 1
                if in_degree[child_id] == 0:
                    heapq.heappush(queue, child_id)

    if processed_count < len(graph):
        cyclic_nodes = sorted([node_id for node_id, deg in in_degree.items() if deg > 0])
        print(f"Warning: Cycle detected involving nodes: {cyclic_nodes}", file=sys.stderr)
        for node_id in cyclic_nodes:
            node = graph[node_id]
            node["inherited_persona"] = _resolve_inherited_persona(node, graph)
            node["inherited_implants"] = _union_implants_over_ancestors(node_id, graph)

    # -------------------------------------------------------------------------
    # Phase 3: Atomic Batch Commit (Single SQLite Transaction)
    # -------------------------------------------------------------------------
    inheritance_updates = []
    for node_id, node_data in graph.items():
        if node_id not in dirty_nodes and node_id in db_by_id:
            cached = db_by_id[node_id]
            new_persona = node_data.get("inherited_persona")
            new_implants = node_data.get("inherited_implants", [])
            if (cached.get("inherited_persona") != new_persona
                    or _json_list(cached.get("inherited_implants")) != new_implants):
                inheritance_updates.append((new_persona, json.dumps(new_implants), node_id))

    needs_commit = bool(dirty_nodes or deleted_ids or mtime_updates or inheritance_updates)

    if needs_commit:
        with conn:
            if deleted_ids:
                placeholders = ",".join("?" for _ in deleted_ids)
                del_list = list(deleted_ids)
                conn.execute(f"DELETE FROM memories WHERE id IN ({placeholders});", del_list)
                conn.execute(
                    f"DELETE FROM memory_edges WHERE parent_id IN ({placeholders}) OR child_id IN ({placeholders});",
                    del_list + del_list
                )
                conn.execute(f"DELETE FROM memories_fts WHERE id IN ({placeholders});", del_list)

            for new_mtime, n_id in mtime_updates:
                conn.execute("UPDATE memories SET mtime = ? WHERE id = ?;", (new_mtime, n_id))

            for new_persona, new_implants_json, n_id in inheritance_updates:
                conn.execute(
                    "UPDATE memories SET inherited_persona = ?, inherited_implants = ? WHERE id = ?;",
                    (new_persona, new_implants_json, n_id)
                )

            for node_id, data in dirty_nodes.items():
                conn.execute("""
                INSERT INTO memories (
                    id, file_path, title, date, summary, type, status, persona,
                    inherited_persona, implants, inherited_implants,
                    tags_json, open_tail_json, parents_json, mtime, hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    file_path=excluded.file_path,
                    title=excluded.title,
                    date=excluded.date,
                    summary=excluded.summary,
                    type=excluded.type,
                    status=excluded.status,
                    persona=excluded.persona,
                    inherited_persona=excluded.inherited_persona,
                    implants=excluded.implants,
                    inherited_implants=excluded.inherited_implants,
                    tags_json=excluded.tags_json,
                    open_tail_json=excluded.open_tail_json,
                    parents_json=excluded.parents_json,
                    mtime=excluded.mtime,
                    hash=excluded.hash;
                """, (
                    data["id"], data["file_path"], data["title"], data["date"], data["summary"],
                    data["type"], data["status"], data["persona"], graph[node_id]["inherited_persona"],
                    json.dumps(data["implants"]), json.dumps(graph[node_id]["inherited_implants"]),
                    json.dumps(data["tags"]), json.dumps(data["open_tail"]), json.dumps(data["parents"]),
                    data["mtime"], data["hash"]
                ))

                conn.execute("DELETE FROM memory_edges WHERE child_id = ?;", (node_id,))
                edge_rows = [(p, node_id) for p in data["parents"]]
                if edge_rows:
                    conn.executemany("INSERT OR IGNORE INTO memory_edges (parent_id, child_id) VALUES (?, ?);", edge_rows)

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
