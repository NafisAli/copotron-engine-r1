import sys
import heapq
from pathlib import Path
from schema import parse_frontmatter
from vault import get_vault_path, atomic_write_json

def load_vault():
    vault_dir = get_vault_path(require_root=True)
    graph = {}
    
    # Pass 1: Parse all markdown files (ignore hidden folders like .obsidian)
    for file_path in vault_dir.rglob("*.md"):
        # Skip files in hidden directories
        if any(part.startswith(".") for part in file_path.relative_to(vault_dir).parts):
            continue

        if file_path.is_file():
            try:
                memory = parse_frontmatter(file_path)
                rel_path = str(file_path.relative_to(vault_dir)).replace("\\", "/")
                graph[memory.id] = {
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
                    "inherited_persona": memory.persona
                }
            except Exception as e:
                print(f"Skipping {file_path.name}: {e}")

    # Pass 2: Calculate Children (constant-time set accumulation, deterministically sorted)
    children_sets = {node_id: set() for node_id in graph}
    for node_id, node_data in graph.items():
        for parent_id in node_data["parents"]:
            if parent_id in graph:
                children_sets[parent_id].add(node_id)
            else:
                print(f"Warning: Parent '{parent_id}' not found for node '{node_id}' ({node_data['title']})")

    for node_id in graph:
        graph[node_id]["children"] = sorted(children_sets[node_id])

    # Pass 3: Calculate Persona Inheritance (Topological Sort - Kahn's Algorithm)
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

    # Pass 4: Save Graph Atomically
    graph_path = vault_dir / "graph.json"
    atomic_write_json(graph_path, graph, indent=2)
    print(f"Indexed {len(graph)} memories to {graph_path}")
    return graph

if __name__ == "__main__":
    load_vault()
