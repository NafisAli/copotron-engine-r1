import sys
import re
import json
import argparse
from pathlib import Path
from vault import get_vault_path
from db import get_db_path, get_readonly_db

def format_fts_query(raw_query: str, op: str = "AND") -> str:
    """Extract alphanumeric tokens and wrap each in prefix matching syntax for FTS5."""
    tokens = re.findall(r'[\w]+', raw_query)
    if not tokens:
        return ""
    joiner = " OR " if op == "OR" else " "
    return joiner.join(f'"{t}"*' for t in tokens)

def search_graph(query=None, tag=None, memory_type=None, status=None, limit=20, offset=0, print_output=True):
    vault_dir = get_vault_path(require_root=True)
    db_path = get_db_path(vault_dir)
    if not db_path.exists():
        print(f"Error: {db_path} not found. Run indexer.py first.", file=sys.stderr)
        sys.exit(1)

    conn = get_readonly_db(db_path)
    sql_limit = limit if limit > 0 else -1

    tokens = re.findall(r'[\w]+', query) if query else []
    id_tokens = list(dict.fromkeys(t.lower() for t in tokens if len(t) == 8 and re.match(r'^[0-9a-fA-F]{8}$', t)))

    id_rows = []
    if id_tokens:
        placeholders = ",".join("?" for _ in id_tokens)
        sql_id = f"""
        SELECT id, file_path, title, type, status, summary, inherited_persona
        FROM memories
        WHERE lower(id) IN ({placeholders})
          AND (? IS NULL OR lower(type) = lower(?))
          AND (? IS NULL OR lower(status) = lower(?))
          AND (? IS NULL OR EXISTS (SELECT 1 FROM json_each(tags_json) WHERE lower(value) = lower(?)))
        ORDER BY id;
        """
        params_id = [*id_tokens, memory_type, memory_type, status, status, tag, tag]
        cur_id = conn.execute(sql_id, params_id)
        id_rows = cur_id.fetchall()

    fts_match = format_fts_query(query) if query else ""
    fts_rows = []

    if fts_match:
        # Full-Text Keyword Search via FTS5 with BM25 ranking
        sql = """
        SELECT m.id, m.file_path, m.title, m.type, m.status, m.summary, m.inherited_persona
        FROM memories_fts f
        JOIN memories m ON f.id = m.id
        WHERE memories_fts MATCH ?
          AND (? IS NULL OR lower(m.type) = lower(?))
          AND (? IS NULL OR lower(m.status) = lower(?))
          AND (? IS NULL OR EXISTS (SELECT 1 FROM json_each(m.tags_json) WHERE lower(value) = lower(?)))
        ORDER BY rank
        LIMIT ? OFFSET ?;
        """
        params = [fts_match, memory_type, memory_type, status, status, tag, tag, sql_limit, offset]
        cur = conn.execute(sql, params)
        fts_rows = cur.fetchall()

        # Resilient fallback: If strict AND returned 0 results and query has multiple tokens,
        # fall back to OR match so callers don't get stuck on multi-keyword queries
        if len(fts_rows) == 0 and len(tokens) > 1:
            fts_match_or = format_fts_query(query, op="OR")
            params_or = [fts_match_or, memory_type, memory_type, status, status, tag, tag, sql_limit, offset]
            cur = conn.execute(sql, params_or)
            fts_rows = cur.fetchall()
    elif not id_tokens:
        # Pure Metadata Filter Search
        sql = """
        SELECT id, file_path, title, type, status, summary, inherited_persona
        FROM memories
        WHERE (? IS NULL OR lower(type) = lower(?))
          AND (? IS NULL OR lower(status) = lower(?))
          AND (? IS NULL OR EXISTS (SELECT 1 FROM json_each(tags_json) WHERE lower(value) = lower(?)))
        ORDER BY id
        LIMIT ? OFFSET ?;
        """
        params = [memory_type, memory_type, status, status, tag, tag, sql_limit, offset]
        cur = conn.execute(sql, params)
        fts_rows = cur.fetchall()

    # Merge ID rows and FTS rows, deduplicating by ID
    seen_ids = set()
    rows = []
    for r in id_rows:
        if r["id"] not in seen_ids:
            seen_ids.add(r["id"])
            rows.append(r)
    for r in fts_rows:
        if r["id"] not in seen_ids:
            seen_ids.add(r["id"])
            rows.append(r)

    if sql_limit > 0 and len(rows) > sql_limit:
        rows = rows[:sql_limit]

    results = []
    for row in rows:
        results.append({
            "id": row["id"],
            "file_path": row["file_path"],
            "title": row["title"],
            "type": row["type"],
            "status": row["status"],
            "summary": row["summary"],
            "inherited_persona": row["inherited_persona"]
        })

    conn.close()
    if print_output:
        print(json.dumps(results, indent=2))
    return results

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Search the Memory Index (FTS5 & Metadata Match)")
    parser.add_argument("--query", "-q", type=str, help="Search title, summary, tags, and body using FTS5")
    parser.add_argument("--tag", "-t", type=str, help="Filter by tag")
    parser.add_argument("--type", type=str, help="Filter by memory type (episodic, declarative, procedural, prospective)")
    parser.add_argument("--status", "-s", type=str, help="Filter by status (active, completed, archived, none)")
    parser.add_argument("--limit", "-l", type=int, default=20, help="Max results to return (default: 20; 0 for unlimited)")
    parser.add_argument("--offset", type=int, default=0, help="Number of results to skip (default: 0)")

    args = parser.parse_args()
    search_graph(args.query, args.tag, args.type, args.status, args.limit, args.offset, print_output=True)

