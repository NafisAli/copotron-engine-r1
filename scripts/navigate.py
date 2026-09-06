import sys
import json
import argparse
from pathlib import Path
from vault import get_vault_path

def navigate(node_id: str, direction: str):
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

    if direction == "up":
        for parent_id in node.get("parents", []):
            if parent_id in graph:
                results.append(format_node(parent_id, graph[parent_id]))
            else:
                results.append({
                    "id": parent_id,
                    "error": f"Parent node '{parent_id}' referenced but not found in graph."
                })
    elif direction == "down":
        for child_id in node.get("children", []):
            if child_id in graph:
                results.append(format_node(child_id, graph[child_id]))
            else:
                results.append({
                    "id": child_id,
                    "error": f"Child node '{child_id}' referenced but not found in graph."
                })

    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Navigate the Memory Tree")
    parser.add_argument("--node", required=True, type=str, help="The 8-character Node ID to navigate from")
    parser.add_argument("--direction", required=True, choices=["up", "down"], help="Direction to travel (up to parents, down to children)")
    
    args = parser.parse_args()
    navigate(args.node, args.direction)
