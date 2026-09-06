import json
from pathlib import Path
from schema import parse_frontmatter
from vault import get_vault_path

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

    # Pass 2: Calculate Children (deduplicated)
    for node_id, node_data in graph.items():
        for parent_id in node_data["parents"]:
            if parent_id in graph:
                if node_id not in graph[parent_id]["children"]:
                    graph[parent_id]["children"].append(node_id)
            else:
                print(f"Warning: Parent '{parent_id}' not found for node '{node_id}' ({node_data['title']})")

    # Pass 3: Calculate Persona Inheritance (DFS with cycle guard)
    roots = [node_id for node_id, data in graph.items() if not data["parents"]]

    def dfs_persona(node_id: str, current_persona: str | None, visiting: set):
        if node_id in visiting:
            # Cycle detected; break recursion
            return
        visiting.add(node_id)

        node = graph[node_id]
        # Explicit persona on node always overrides
        if node["persona"]:
            active_persona = node["persona"]
        elif current_persona:
            active_persona = current_persona
        else:
            active_persona = node.get("inherited_persona")

        node["inherited_persona"] = active_persona

        for child_id in node["children"]:
            if child_id in graph:
                dfs_persona(child_id, active_persona, visiting)

        visiting.remove(node_id)

    for root_id in roots:
        dfs_persona(root_id, None, set())

    # Save Graph
    graph_path = vault_dir / "graph.json"
    with open(graph_path, "w", encoding="utf-8") as f:
        json.dump(graph, f, indent=2)
    print(f"Indexed {len(graph)} memories to {graph_path}")

if __name__ == "__main__":
    load_vault()
