import sys
import json
import argparse
from pathlib import Path
from vault import get_vault_path

def search_graph(query=None, tag=None, memory_type=None, status=None, limit=20, offset=0):
    vault_dir = get_vault_path(require_root=True)
    graph_path = vault_dir / "graph.json"
    if not graph_path.exists():
        print(f"Error: {graph_path} not found. Run indexer.py first.", file=sys.stderr)
        sys.exit(1)

    with open(graph_path, "r", encoding="utf-8") as f:
        graph = json.load(f)

    results = []
    query_tokens = query.lower().split() if query else []
    
    for node_id, data in graph.items():
        match = True
        
        # Filter by type
        if memory_type and data.get("type") != memory_type.lower():
            match = False
            
        # Filter by status
        if status and data.get("status") != status.lower():
            match = False

        # Filter by tag (case-insensitive)
        if tag:
            tags_lower = [t.lower() for t in data.get("tags", [])]
            if tag.lower() not in tags_lower:
                match = False
            
        # Filter by query (multi-term matching across title, summary, tags)
        if query_tokens:
            text_to_search = f"{data.get('title', '')} {data.get('summary', '')} {' '.join(data.get('tags', []))}".lower()
            if not all(token in text_to_search for token in query_tokens):
                match = False
                
        if match:
            flat_node = {
                "id": node_id,
                "file_path": data.get("file_path", ""),
                "title": data.get("title", ""),
                "type": data.get("type", ""),
                "status": data.get("status", ""),
                "summary": data.get("summary", ""),
                "inherited_persona": data.get("inherited_persona")
            }
            results.append(flat_node)

    # Apply pagination (limit=0 means unlimited)
    limit_slice = (offset + limit) if limit > 0 else None
    paginated = results[offset:limit_slice]
    print(json.dumps(paginated, indent=2))
    return paginated

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Search the Memory Graph (Flat Match)")
    parser.add_argument("--query", "-q", type=str, help="Search title, summary, and tags (matches all words)")
    parser.add_argument("--tag", "-t", type=str, help="Filter by tag")
    parser.add_argument("--type", type=str, help="Filter by memory type (episodic, declarative, procedural, prospective)")
    parser.add_argument("--status", "-s", type=str, help="Filter by status (active, completed, archived, none)")
    parser.add_argument("--limit", "-l", type=int, default=20, help="Max results to return (default: 20; 0 for unlimited)")
    parser.add_argument("--offset", type=int, default=0, help="Number of results to skip (default: 0)")
    
    args = parser.parse_args()
    search_graph(args.query, args.tag, args.type, args.status, args.limit, args.offset)
