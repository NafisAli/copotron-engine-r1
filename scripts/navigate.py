import sys
import json
import argparse
from pathlib import Path
from vault import get_vault_path

def navigate(node_id: str, direction: str, limit: int = 20, offset: int = 0, status: str | None = None):
    vault_dir = get_vault_path(require_root=True)
    graph_path = vault_dir / "graph.json"
    if not graph_path.exists():
        print(f"Error: {graph_path} not found. Run indexer.py first.", file=sys.stderr)
        sys.exit(1)

    with open(graph_path, "r", encoding="utf-8") as f:
        graph = json.load(f)

    if node_id not in graph:
        print(json.dumps({"error": f"Node '{node_id}' not found in graph."}, indent=2), file=sys.stderr)
        sys.exit(1)

    node = graph[node_id]
    results = []

    def format_node(n_id: str, n_data: dict) -> dict:
        return {
            "id": n_id,
            "file_path": n_data.get("file_path", ""),
            "title": n_data.get("title", ""),
            "summary": n_data.get("summary", ""),
            "type": n_data.get("type", ""),
            "status": n_data.get("status", ""),
            "tags": n_data.get("tags", []),
            "inherited_persona": n_data.get("inherited_persona")
        }

    target_ids = node.get("parents", []) if direction == "up" else node.get("children", [])

    for target_id in target_ids:
        if target_id in graph:
            target_data = graph[target_id]
            if status and target_data.get("status", "").lower() != status.lower():
                continue
            results.append(format_node(target_id, target_data))
        else:
            if not status:
                rel_type = "Parent" if direction == "up" else "Child"
                results.append({
                    "id": target_id,
                    "error": f"{rel_type} node '{target_id}' referenced but not found in graph."
                })

    # Apply pagination (limit=0 means unlimited)
    limit_slice = (offset + limit) if limit > 0 else None
    paginated = results[offset:limit_slice]
    print(json.dumps(paginated, indent=2))
    return paginated

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Navigate the Memory Tree")
    parser.add_argument("--node", required=True, type=str, help="The 8-character Node ID to navigate from")
    parser.add_argument("--direction", required=True, choices=["up", "down"], help="Direction to travel (up to parents, down to children)")
    parser.add_argument("--status", "-s", type=str, help="Filter results by status (active, completed, archived, none)")
    parser.add_argument("--limit", "-l", type=int, default=20, help="Max results to return (default: 20; 0 for unlimited)")
    parser.add_argument("--offset", type=int, default=0, help="Number of results to skip (default: 0)")
    
    args = parser.parse_args()
    navigate(args.node, args.direction, limit=args.limit, offset=args.offset, status=args.status)
