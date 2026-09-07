import sys
import json
import argparse
from pathlib import Path
from copotron.vault import get_vault_path
from copotron.db import get_db_path, get_readonly_db

def navigate(node_id: str, direction: str, limit: int = 20, offset: int = 0, status: str | None = None, print_output: bool = True):
    vault_dir = get_vault_path(require_root=True)
    db_path = get_db_path(vault_dir)
    if not db_path.exists():
        print(f"Error: {db_path} not found. Run 'copotron index' first.", file=sys.stderr)
        sys.exit(1)

    conn = get_readonly_db(db_path)

    # Check if target node exists
    cur = conn.execute("SELECT id FROM memories WHERE id = ?;", (node_id,))
    if not cur.fetchone():
        conn.close()
        print(json.dumps({"error": f"Node '{node_id}' not found in graph."}, indent=2), file=sys.stderr)
        sys.exit(1)

    sql_limit = limit if limit > 0 else -1

    if direction == "down":
        sql = """
        SELECT m.id, m.file_path, m.title, m.summary, m.type, m.status, m.tags_json, m.inherited_persona
        FROM memories m
        JOIN memory_edges e ON m.id = e.child_id
        WHERE e.parent_id = ?
          AND (? IS NULL OR lower(m.status) = lower(?))
        ORDER BY m.id
        LIMIT ? OFFSET ?;
        """
    else:
        sql = """
        SELECT m.id, m.file_path, m.title, m.summary, m.type, m.status, m.tags_json, m.inherited_persona
        FROM memories m
        JOIN memory_edges e ON m.id = e.parent_id
        WHERE e.child_id = ?
          AND (? IS NULL OR lower(m.status) = lower(?))
        ORDER BY m.id
        LIMIT ? OFFSET ?;
        """

    cur = conn.execute(sql, (node_id, status, status, sql_limit, offset))
    rows = cur.fetchall()

    results = []
    for row in rows:
        try:
            tags = json.loads(row["tags_json"])
        except Exception:
            tags = []
        results.append({
            "id": row["id"],
            "file_path": row["file_path"],
            "title": row["title"],
            "summary": row["summary"],
            "type": row["type"],
            "status": row["status"],
            "tags": tags,
            "inherited_persona": row["inherited_persona"]
        })

    conn.close()
    if print_output:
        print(json.dumps(results, indent=2))
    return results

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Navigate the Memory Tree (SQLite Indexed Traversal)")
    parser.add_argument("--node", required=True, type=str, help="The 8-character Node ID to navigate from")
    parser.add_argument("--direction", required=True, choices=["up", "down"], help="Direction to travel (up to parents, down to children)")
    parser.add_argument("--status", "-s", type=str, help="Filter results by status (active, completed, archived, none)")
    parser.add_argument("--limit", "-l", type=int, default=20, help="Max results to return (default: 20; 0 for unlimited)")
    parser.add_argument("--offset", type=int, default=0, help="Number of results to skip (default: 0)")

    args = parser.parse_args()
    navigate(args.node, args.direction, limit=args.limit, offset=args.offset, status=args.status)
