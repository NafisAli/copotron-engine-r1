import os
import sys
import re
import json
import hashlib
import argparse
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

# Ensure scripts directory is on sys.path
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from schema import MemorySchema, dump_frontmatter, parse_frontmatter
from vault import get_vault_path, atomic_write_text
from indexer import load_vault
from search import search_graph

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def clean_slug(title: str) -> str:
    """Generate a clean, lower-case, hyphenated slug for filenames."""
    s = title.lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s).strip("-")
    return s[:50] or "untitled"


def generate_unique_id(vault_dir: Path, title: str, date_str: str, extra_entropy: str = "") -> str:
    """
    Generate an 8-character collision-free hex ID.
    Hashes title + date + extra entropy, incrementing counter on collision.
    """
    existing_ids = set()
    if vault_dir.exists():
        for f in vault_dir.glob("*.md"):
            if len(f.name) >= 9 and f.name[8] == "-":
                existing_ids.add(f.name[:8].lower())

    counter = 0
    while True:
        raw = f"{title}:{date_str}:{extra_entropy}:{counter}"
        candidate_id = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8].lower()
        if candidate_id not in existing_ids:
            existing_ids.add(candidate_id)
            return candidate_id
        counter += 1


def suggest_parents(query: str, limit: int = 5, vault_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Search index for candidate parent nodes matching a keyword query."""
    try:
        results = search_graph(query=query, limit=limit, print_output=False)
        if not results:
            # If multi-token AND search finds nothing, search by significant tokens
            tokens = [t for t in re.findall(r'\w+', query) if len(t) > 3]
            for t in tokens:
                sub_results = search_graph(query=t, limit=limit, print_output=False)
                if sub_results:
                    results = sub_results
                    break

        return [
            {
                "id": r["id"],
                "title": r["title"],
                "type": r["type"],
                "summary": r.get("summary", ""),
                "inherited_persona": r.get("inherited_persona")
            }
            for r in results
        ]
    except Exception as e:
        print(f"Warning: Parent search failed ({e}).", file=sys.stderr)
        return []


def resolve_auto_parent(title: str, summary: str, vault_dir: Path) -> List[str]:
    """Find the most relevant parent ID or default to root node '00000000'."""
    query = f"{title} {summary}".strip()
    candidates = suggest_parents(query, limit=5, vault_dir=vault_dir)
    # Prefer domain or project hubs (declarative or prospective) over episodic
    for c in candidates:
        if c["type"] in ("declarative", "prospective") and c["id"] != "00000000":
            return [c["id"]]

    # Fallback to root if root exists
    root_file = vault_dir / "00000000-root.md"
    if root_file.is_file():
        return ["00000000"]
    return []


def create_memory_node(
    vault_dir: Path,
    title: str,
    memory_type: str,
    summary: str = "",
    body: str = "",
    parents: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
    status: str = "active",
    node_date: Optional[str] = None,
    node_id: Optional[str] = None,
    persona: Optional[str] = None,
    extra_fields: Optional[Dict[str, Any]] = None,
    auto_parent: bool = False,
) -> Dict[str, Any]:
    """
    Create, validate, and write a single memory file in the vault.
    Returns metadata dict for the created node.
    """
    if node_date is None:
        node_date = datetime.now().strftime("%Y-%m-%d")

    parents = list(parents) if parents else []
    tags = list(tags) if tags else []

    if auto_parent and not parents:
        parents = resolve_auto_parent(title, summary, vault_dir)

    if node_id:
        final_id = str(node_id).strip().lower()
        if len(final_id) < 8:
            final_id = f"{int(final_id):08d}" if final_id.isdigit() else final_id.zfill(8)
    else:
        final_id = generate_unique_id(vault_dir, title, node_date)

    slug = clean_slug(title)
    filename = f"{final_id}-{slug}.md"
    file_path = vault_dir / filename

    # Build schema data including open tail extra fields
    schema_data = {
        "id": final_id,
        "title": title,
        "date": node_date,
        "summary": summary,
        "type": memory_type,
        "status": status,
        "parents": parents,
        "tags": tags,
        "persona": persona,
    }
    if extra_fields:
        schema_data.update(extra_fields)

    memory = MemorySchema(**schema_data)
    content = dump_frontmatter(memory, body)

    # Atomically write file
    atomic_write_text(file_path, content)

    # Validate output
    parse_frontmatter(file_path)

    return {
        "action": "created",
        "id": final_id,
        "title": title,
        "slug": slug,
        "filename": filename,
        "file_path": str(file_path),
        "type": memory_type,
        "status": status,
        "parents": parents,
        "tags": tags,
        "date": node_date,
    }


def find_memory_file(vault_dir: Path, node_id: str) -> Optional[Path]:
    """Find an existing markdown file in vault_dir matching {node_id}-*.md."""
    if not vault_dir.is_dir() or not node_id:
        return None
    norm_id = str(node_id).strip().lower()
    if len(norm_id) < 8 and norm_id.isdigit():
        norm_id = f"{int(norm_id):08d}"

    for p in vault_dir.glob(f"{norm_id}-*.md"):
        if p.is_file():
            return p
    return None


def update_memory_node(
    vault_dir: Path,
    existing_file: Path,
    title: Optional[str] = None,
    memory_type: Optional[str] = None,
    summary: Optional[str] = None,
    body: Optional[str] = None,
    append_body: bool = False,
    parents: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
    status: Optional[str] = None,
    node_date: Optional[str] = None,
    persona: Optional[str] = None,
    extra_fields: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Update an existing memory note in-place.
    Preserves existing metadata and open-tail fields when not explicitly overridden.
    Renames file if title/slug changes.
    """
    from schema import parse_frontmatter_and_body

    existing_schema, existing_body = parse_frontmatter_and_body(existing_file)

    final_title = title.strip() if title and title.strip() else existing_schema.title
    final_type = memory_type if memory_type else existing_schema.type
    final_summary = summary.strip() if summary and summary.strip() else existing_schema.summary
    final_status = status if status else existing_schema.status
    final_parents = list(parents) if parents is not None else existing_schema.parents

    if tags is not None and len(tags) > 0:
        final_tags = sorted(list(set(existing_schema.tags + list(tags))))
    else:
        final_tags = existing_schema.tags

    final_persona = persona if persona is not None else existing_schema.persona
    final_date = node_date if node_date else datetime.now().strftime("%Y-%m-%d")

    # Body update logic
    if body is not None and body.strip():
        if append_body:
            final_body = f"{existing_body.rstrip()}\n\n{body.lstrip()}".strip()
        else:
            final_body = body.strip()
    else:
        final_body = existing_body

    # Open tail metadata merge
    merged_extra = dict(existing_schema.model_extra or {})
    if extra_fields:
        merged_extra.update(extra_fields)

    schema_data = {
        "id": existing_schema.id,
        "title": final_title,
        "date": final_date,
        "summary": final_summary,
        "type": final_type,
        "status": final_status,
        "parents": final_parents,
        "tags": final_tags,
        "persona": final_persona,
    }
    schema_data.update(merged_extra)

    updated_schema = MemorySchema(**schema_data)
    content = dump_frontmatter(updated_schema, final_body)

    new_slug = clean_slug(final_title)
    new_filename = f"{existing_schema.id}-{new_slug}.md"
    new_file_path = vault_dir / new_filename

    atomic_write_text(new_file_path, content)

    # Clean up old file if slug changed
    if new_file_path.resolve() != existing_file.resolve() and existing_file.exists():
        try:
            existing_file.unlink()
        except OSError:
            pass

    parse_frontmatter(new_file_path)

    return {
        "action": "updated",
        "id": existing_schema.id,
        "title": final_title,
        "slug": new_slug,
        "filename": new_filename,
        "file_path": str(new_file_path),
        "type": final_type,
        "status": final_status,
        "parents": final_parents,
        "tags": final_tags,
        "date": final_date,
    }


def create_or_update_memory_node(
    vault_dir: Path,
    title: Optional[str] = None,
    memory_type: Optional[str] = None,
    summary: str = "",
    body: str = "",
    append_body: bool = False,
    parents: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
    status: str = "active",
    node_date: Optional[str] = None,
    node_id: Optional[str] = None,
    persona: Optional[str] = None,
    extra_fields: Optional[Dict[str, Any]] = None,
    auto_parent: bool = False,
) -> Dict[str, Any]:
    """
    Dispatcher: updates existing node if node_id matches an existing file,
    otherwise creates a new memory node.
    """
    if node_id:
        existing = find_memory_file(vault_dir, node_id)
        if existing:
            return update_memory_node(
                vault_dir=vault_dir,
                existing_file=existing,
                title=title,
                memory_type=memory_type,
                summary=summary,
                body=body,
                append_body=append_body,
                parents=parents,
                tags=tags,
                status=status,
                node_date=node_date,
                persona=persona,
                extra_fields=extra_fields,
            )

    if not title or not memory_type:
        raise ValueError("Both 'title' and 'type' are required when creating a new memory node.")

    return create_memory_node(
        vault_dir=vault_dir,
        title=title,
        memory_type=memory_type,
        summary=summary,
        body=body,
        parents=parents,
        tags=tags,
        status=status,
        node_date=node_date,
        node_id=node_id,
        persona=persona,
        extra_fields=extra_fields,
        auto_parent=auto_parent,
    )


def sync_index(vault_dir: Path, quiet: bool = False):
    """Synchronize SQLite index, optionally silencing stdout for clean JSON outputs."""
    if quiet:
        import io
        from contextlib import redirect_stdout
        with redirect_stdout(io.StringIO()):
            load_vault(vault_dir)
    else:
        load_vault(vault_dir)


def crystallize_manifest(
    vault_dir: Path,
    manifest_nodes: List[Dict[str, Any]],
    auto_index: bool = True,
    quiet_index: bool = False
) -> List[Dict[str, Any]]:
    """
    Commit a batch of memory nodes atomically.
    Supports in-place updates for existing IDs and reference substitution via $temp_ref.
    """
    created_nodes = []
    ref_map: Dict[str, str] = {}

    # First pass: pre-assign IDs so inter-node references can resolve
    for item in manifest_nodes:
        temp_ref = item.get("temp_ref")
        if item.get("id"):
            assigned_id = str(item["id"]).strip().lower()
            if len(assigned_id) < 8 and assigned_id.isdigit():
                assigned_id = f"{int(assigned_id):08d}"
        else:
            date_str = item.get("date") or datetime.now().strftime("%Y-%m-%d")
            assigned_id = generate_unique_id(vault_dir, item["title"], date_str, extra_entropy=str(temp_ref or ""))
        item["_assigned_id"] = assigned_id
        if temp_ref:
            ref_map[f"${temp_ref}"] = assigned_id
            ref_map[temp_ref] = assigned_id

    # Second pass: resolve parent references and create or update nodes
    for item in manifest_nodes:
        raw_parents = item.get("parents", [])
        resolved_parents = []
        if raw_parents is not None:
            for p in raw_parents:
                p_str = str(p).strip()
                if p_str in ref_map:
                    resolved_parents.append(ref_map[p_str])
                elif p_str.startswith("$") and p_str in ref_map:
                    resolved_parents.append(ref_map[p_str])
                else:
                    resolved_parents.append(p_str)
        else:
            resolved_parents = None

        extra_keys = {
            k: v for k, v in item.items()
            if k not in (
                "title", "type", "summary", "body", "parents", "tags",
                "status", "date", "id", "persona", "temp_ref", "_assigned_id", "auto_parent", "append_body"
            )
        }

        node_id_to_use = item.get("id") or item.get("_assigned_id")
        created = create_or_update_memory_node(
            vault_dir=vault_dir,
            title=item.get("title"),
            memory_type=item.get("type"),
            summary=item.get("summary", ""),
            body=item.get("body", ""),
            append_body=item.get("append_body", False),
            parents=resolved_parents,
            tags=item.get("tags", []),
            status=item.get("status", "active"),
            node_date=item.get("date"),
            node_id=node_id_to_use,
            persona=item.get("persona"),
            extra_fields=extra_keys,
            auto_parent=item.get("auto_parent", False),
        )
        created_nodes.append(created)

    if auto_index:
        sync_index(vault_dir, quiet=quiet_index)

    return created_nodes


def main():
    parser = argparse.ArgumentParser(
        description="Copotron Memory Crystallizer: transform conversational discoveries into validated DAG memory nodes."
    )
    # Manifest / batch options
    parser.add_argument("--manifest", help="Path to a JSON file containing a list of memory nodes to crystallize.")
    parser.add_argument("--json", dest="json_str", help="JSON string containing a list of memory nodes to crystallize.")
    
    # Single node options
    parser.add_argument("--title", help="Title of the memory node.")
    parser.add_argument("--type", choices=["episodic", "declarative", "procedural", "prospective"], help="Memory type.")
    parser.add_argument("--summary", default="", help="1-2 sentence summary for AI context scanning.")
    parser.add_argument("--body", default="", help="Markdown body content.")
    parser.add_argument("--parent", action="append", dest="parents", default=[], help="Parent 8-character node ID (can specify multiple).")
    parser.add_argument("--tag", action="append", dest="tags", default=[], help="Semantic tag (can specify multiple).")
    parser.add_argument("--status", choices=["active", "completed", "archived", "none"], default="active", help="Lifecycle status.")
    parser.add_argument("--date", default=None, help="Date in YYYY-MM-DD format (defaults to today).")
    parser.add_argument("--id", default=None, help="Explicit 8-character ID (defaults to auto-generated).")
    parser.add_argument("--persona", default=None, help="Persona identifier.")
    parser.add_argument("--auto-parent", action="store_true", help="Auto-resolve parent node via semantic search.")
    parser.add_argument("--append-body", action="store_true", help="When updating an existing node, append to the body instead of replacing.")
    
    # Utility / query options
    parser.add_argument("--suggest-parents", help="Query the index and return top candidate parent node IDs without creating a node.")
    parser.add_argument("--no-index", action="store_true", help="Skip re-indexing SQLite database after node creation.")
    parser.add_argument("--json-output", action="store_true", help="Format CLI output as JSON.")

    args = parser.parse_args()

    vault_dir = get_vault_path(require_root=True)

    # Mode 1: Parent suggestion query
    if args.suggest_parents:
        candidates = suggest_parents(args.suggest_parents, limit=10, vault_dir=vault_dir)
        if args.json_output:
            print(json.dumps(candidates, indent=2))
        else:
            print(f"Parent candidates for '{args.suggest_parents}':")
            for c in candidates:
                print(f"  [{c['id']}] ({c['type']}) {c['title']} — {c.get('summary', '')}")
        return

    # Mode 2: Batch manifest mode
    manifest_nodes = None
    if args.manifest:
        manifest_path = Path(args.manifest)
        if not manifest_path.exists():
            print(f"Error: Manifest file not found: {args.manifest}", file=sys.stderr)
            sys.exit(1)
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest_nodes = json.load(f)
    elif args.json_str:
        manifest_nodes = json.loads(args.json_str)

    if manifest_nodes is not None:
        if not isinstance(manifest_nodes, list):
            manifest_nodes = [manifest_nodes]
        created = crystallize_manifest(
            vault_dir,
            manifest_nodes,
            auto_index=not args.no_index,
            quiet_index=args.json_output
        )
        if args.json_output:
            print(json.dumps(created, indent=2))
        else:
            print(f"✅ Successfully crystallized {len(created)} node(s):")
            for node in created:
                action_label = "updated" if node.get("action") == "updated" else "created"
                print(f"  • [{node['id']}] {node['filename']} ({node['type']}) [{action_label}]")
        return

    # Mode 3: Single node mode (create or update)
    existing_file = find_memory_file(vault_dir, args.id) if args.id else None
    if not existing_file and (not args.title or not args.type):
        parser.print_help(sys.stderr)
        print("\nError: --title and --type are required when creating a new memory node.", file=sys.stderr)
        sys.exit(1)

    node = create_or_update_memory_node(
        vault_dir=vault_dir,
        title=args.title,
        memory_type=args.type,
        summary=args.summary,
        body=args.body,
        append_body=args.append_body,
        parents=args.parents if args.parents else None,
        tags=args.tags if args.tags else None,
        status=args.status,
        node_date=args.date,
        node_id=args.id,
        persona=args.persona,
        auto_parent=args.auto_parent,
    )

    if not args.no_index:
        sync_index(vault_dir, quiet=args.json_output)

    if args.json_output:
        print(json.dumps(node, indent=2))
    else:
        action_verb = "updated" if node.get("action") == "updated" else "crystallized"
        print(f"✅ Successfully {action_verb} node: [{node['id']}] {node['filename']}")


if __name__ == "__main__":
    main()
