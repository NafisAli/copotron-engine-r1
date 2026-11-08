import os
import sys
import re
import json
import hashlib
import argparse
from pathlib import Path
from datetime import datetime
from typing import Collection, List, Dict, Any, Optional

from copotron.core.schema import MemorySchema, dump_frontmatter, parse_frontmatter, parse_frontmatter_and_body
from copotron.core.vault import get_vault_path, atomic_write_text, find_memory_file
from copotron.core.indexer import load_vault
from copotron.core.parents import require_parents
from copotron.core.personas import (
    PERSONA_DEFINITION_TAG,
    PERSONA_DEFINITION_TYPE,
    require_persona_definition,
)
from copotron.system_two.search import search_graph
from copotron.system_two.domains import get_domain_hubs
from copotron.system_one.judgments.slug import generate_clean_slug
from copotron.system_one.judgments.routing import resolve_domain_parent
from copotron.system_one.judgments.rerank import rerank_candidates
from copotron.system_one.judgments.classification import infer_memory_type
from copotron.system_two.splicer import splice_markdown_sections

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def clean_slug(title: str) -> str:
    """Generate a clean, lower-case, hyphenated slug without cutting words in half."""
    return generate_clean_slug(title)


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
    """Search index for candidate parent nodes and rerank using System One."""
    try:
        results = search_graph(query=query, limit=max(limit * 2, 10), print_output=False)
        if not results:
            tokens = [t for t in re.findall(r'\w+', query) if len(t) > 3]
            for t in tokens:
                sub_results = search_graph(query=t, limit=max(limit * 2, 10), print_output=False)
                if sub_results:
                    results = sub_results
                    break

        candidates = [
            {
                "id": r["id"],
                "title": r["title"],
                "type": r["type"],
                "summary": r.get("summary", ""),
                "inherited_persona": r.get("inherited_persona"),
                "inherited_persona_title": r.get("inherited_persona_title"),
            }
            for r in results
        ]

        # Rerank via System One Score
        reranked = rerank_candidates(query, "", candidates, purpose="parent")
        return reranked[:limit] if reranked else candidates[:limit]

    except Exception as e:
        print(f"Warning: Parent search failed ({e}).", file=sys.stderr)
        return []


def resolve_auto_parent(title: str, summary: str, vault_dir: Optional[Path] = None) -> List[str]:
    """Find the most relevant parent ID (domain hub or project parent) or default to root node '00000000'."""
    if vault_dir is None:
        vault_dir = get_vault_path(require_root=True)

    hubs = get_domain_hubs(vault_dir)
    if hubs:
        res = resolve_domain_parent(title=title, summary=summary, hubs=hubs)
        if res and res != ["00000000"]:
            return res

    # Check candidates from suggest_parents (prefer declarative or prospective over episodic)
    candidates = suggest_parents(f"{title} {summary}".strip(), limit=5, vault_dir=vault_dir)
    for c in candidates:
        if c["type"] in ("declarative", "prospective") and c["id"] != "00000000":
            return [c["id"]]

    root_file = vault_dir / "00000000-root.md"
    if root_file.is_file():
        return ["00000000"]
    return []


def _normalize_persona(persona: Any) -> Optional[str]:
    """Strip a persona value; a blank value means no persona."""
    if persona is None:
        return None
    stripped = str(persona).strip()
    return stripped or None


def _validated_persona(vault_dir: Path, persona: Any) -> Optional[str]:
    """Normalize a persona supplied by a write and require it to be a Persona Definition id."""
    persona = _normalize_persona(persona)
    if persona is not None:
        require_persona_definition(vault_dir, persona)
    return persona


def _declares_persona_definition(item: Dict[str, Any]) -> bool:
    """True when a manifest item declares itself a Persona Definition (explicit type and tag)."""
    return (
        item.get("type") == PERSONA_DEFINITION_TYPE
        and not item.get("auto_type")
        and PERSONA_DEFINITION_TAG in (item.get("tags") or [])
    )


def _resolve_auto_parents(vault_dir: Path, memory_id: str, title: str, summary: str) -> List[str]:
    """Resolve auto-parent for a new memory, refusing a result that would make it an Orphan."""
    parents = resolve_auto_parent(title, summary, vault_dir)
    if not parents:
        raise ValueError(
            f"memory {memory_id!r}: auto-parent found no parent, which would make it an Orphan. "
            f"Pass --parents <id> instead."
        )
    return parents


def create_memory_node(
    vault_dir: Path,
    title: str,
    memory_type: Optional[str] = None,
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
    auto_type: bool = False,
    batch_ids: Collection[str] = (),
) -> Dict[str, Any]:
    """
    Create, validate, and write a single memory file in the vault.
    Returns metadata dict for the created node. Refuses to write an Orphan or
    a memory whose parent does not exist; batch_ids are the memories a
    manifest batch writes, which count as existing parents.
    """
    if node_date is None:
        node_date = datetime.now().strftime("%Y-%m-%d")

    parents = list(parents) if parents else []
    tags = list(tags) if tags else []

    persona = _validated_persona(vault_dir, persona)

    if (auto_type or not memory_type) and title:
        memory_type = infer_memory_type(title=title, summary=summary, body=body)

    if not memory_type:
        memory_type = "declarative"

    if node_id:
        final_id = str(node_id).strip().lower()
        if len(final_id) < 8:
            final_id = f"{int(final_id):08d}" if final_id.isdigit() else final_id.zfill(8)
    else:
        final_id = generate_unique_id(vault_dir, title, node_date)

    if auto_parent and not parents:
        parents = _resolve_auto_parents(vault_dir, final_id, title, summary)
    require_parents(vault_dir, final_id, parents, batch_ids)

    slug = clean_slug(title)
    filename = f"{final_id}-{slug}.md"
    file_path = vault_dir / filename

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

    atomic_write_text(file_path, content)
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
    batch_ids: Collection[str] = (),
) -> Dict[str, Any]:
    """
    Update an existing memory note in-place.
    Preserves existing metadata and open-tail fields when not explicitly overridden.
    Uses intelligent section splicing when append_body is True.
    """
    existing_schema, existing_body = parse_frontmatter_and_body(existing_file)

    final_title = title.strip() if title and title.strip() else existing_schema.title
    final_type = memory_type if memory_type else existing_schema.type
    final_summary = summary.strip() if summary and summary.strip() else existing_schema.summary
    final_status = status if status else existing_schema.status
    # Only parents supplied by this write are checked; an existing Orphan or
    # missing parent is left for the audit and vault doctor.
    if parents is not None:
        final_parents = list(parents)
        require_parents(vault_dir, existing_schema.id, final_parents, batch_ids)
    else:
        final_parents = existing_schema.parents

    if tags is not None and len(tags) > 0:
        final_tags = sorted(list(set(existing_schema.tags + list(tags))))
    else:
        final_tags = existing_schema.tags

    # Only a persona supplied by this write is validated; an existing Dangling
    # Persona is left for the audit and vault doctor. A blank persona clears it.
    if persona is not None:
        final_persona = _validated_persona(vault_dir, persona)
    else:
        final_persona = existing_schema.persona
    final_date = node_date if node_date else datetime.now().strftime("%Y-%m-%d")

    # Body update logic with section splicing
    if body is not None and body.strip():
        if append_body:
            final_body = splice_markdown_sections(existing_body, body)
        else:
            final_body = body.strip()
    else:
        final_body = existing_body

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
    auto_type: bool = False,
    batch_ids: Collection[str] = (),
) -> Dict[str, Any]:
    """Dispatcher: updates existing node if node_id matches an existing file, else creates a new memory node."""
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
                batch_ids=batch_ids,
            )

    if not title:
        raise ValueError("Field 'title' is required when creating a new memory node.")

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
        auto_type=auto_type,
        batch_ids=batch_ids,
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
    """Commit a batch of memory nodes atomically."""
    created_nodes = []
    ref_map: Dict[str, str] = {}

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

    # Validate every persona before writing anything, so a rejected batch leaves
    # the vault untouched. A persona may name a Persona Definition created by an
    # earlier item in the same batch, and an earlier item that changes a
    # definition's type stops it counting.
    resolved_personas: List[Optional[str]] = []
    batch_persona_definitions: set[str] = set()
    batch_demoted: set[str] = set()
    for item in manifest_nodes:
        persona = _normalize_persona(item.get("persona"))
        if persona is not None:
            persona = ref_map.get(persona, persona)
            if persona not in batch_persona_definitions:
                if persona in batch_demoted:
                    raise ValueError(
                        f"persona {persona!r} is changed by an earlier manifest item so that it is no longer "
                        f"a Persona Definition ({PERSONA_DEFINITION_TYPE} memory tagged '{PERSONA_DEFINITION_TAG}')."
                    )
                require_persona_definition(vault_dir, persona)
        resolved_personas.append(persona)
        assigned_id = item["_assigned_id"]
        if _declares_persona_definition(item):
            batch_persona_definitions.add(assigned_id)
            batch_demoted.discard(assigned_id)
        elif item.get("auto_type") or (item.get("type") and item["type"] != PERSONA_DEFINITION_TYPE):
            batch_persona_definitions.discard(assigned_id)
            batch_demoted.add(assigned_id)

    # Check every item's parents before writing anything, so a batch that would
    # leave an Orphan or a missing parent leaves the vault untouched. A parent
    # may be any memory the batch writes, in any order. An update that does not
    # supply parents (no key, or null) keeps its existing ones, and an
    # auto-parent create without parents is resolved here, so it is checked
    # with the rest of the batch.
    batch_ids = frozenset(item["_assigned_id"] for item in manifest_nodes)
    resolved_parent_lists: List[Optional[List[str]]] = []
    for item in manifest_nodes:
        memory_id = item["_assigned_id"]
        raw_parents = item.get("parents")
        if raw_parents is None:
            resolved_parents = None
        else:
            resolved_parents = [ref_map.get(str(p).strip(), str(p).strip()) for p in raw_parents]

        is_update = find_memory_file(vault_dir, memory_id) is not None
        if not is_update and not resolved_parents and item.get("auto_parent"):
            resolved_parents = _resolve_auto_parents(
                vault_dir, memory_id, item.get("title") or "", item.get("summary", "")
            )
        resolved_parent_lists.append(resolved_parents)

        if is_update and resolved_parents is None:
            continue
        require_parents(vault_dir, memory_id, resolved_parents or [], batch_ids)

    for item, persona, resolved_parents in zip(manifest_nodes, resolved_personas, resolved_parent_lists):
        extra_keys = {
            k: v for k, v in item.items()
            if k not in (
                "title", "type", "summary", "body", "parents", "tags",
                "status", "date", "id", "persona", "temp_ref", "_assigned_id", "auto_parent", "auto_type", "append_body"
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
            persona=persona,
            extra_fields=extra_keys,
            auto_parent=item.get("auto_parent", False),
            auto_type=item.get("auto_type", False),
            batch_ids=batch_ids,
        )
        created_nodes.append(created)

    if auto_index:
        sync_index(vault_dir, quiet=quiet_index)

    return created_nodes


def main():
    parser = argparse.ArgumentParser(
        description="Copotron Memory Crystallizer: transform conversational discoveries into validated DAG memory nodes."
    )
    parser.add_argument("--manifest", help="Path to a JSON file containing a list of memory nodes to crystallize.")
    parser.add_argument("--json", dest="json_str", help="JSON string containing a list of memory nodes to crystallize.")
    parser.add_argument("--title", help="Title of the memory node.")
    parser.add_argument("--type", choices=["episodic", "declarative", "procedural", "prospective"], help="Memory type.")
    parser.add_argument("--auto-type", action="store_true", help="Infer biological memory type using System One.")
    parser.add_argument("--summary", default="", help="1-2 sentence summary for AI context scanning.")
    parser.add_argument("--body", default="", help="Markdown body content.")
    parser.add_argument("--parent", "--parents", action="append", dest="parents", default=[], help="Parent 8-character node ID (can specify multiple).")
    parser.add_argument("--tag", action="append", dest="tags", default=[], help="Semantic tag (can specify multiple).")
    parser.add_argument("--status", choices=["active", "completed", "archived", "none"], default="active", help="Lifecycle status.")
    parser.add_argument("--date", default=None, help="Date in YYYY-MM-DD format (defaults to today).")
    parser.add_argument("--id", default=None, help="Explicit 8-character ID (defaults to auto-generated).")
    parser.add_argument("--persona", default=None, help="Persona identifier.")
    parser.add_argument("--auto-parent", action="store_true", help="Auto-resolve parent node via semantic search.")
    parser.add_argument("--append-body", action="store_true", help="When updating an existing node, append/splice body instead of replacing.")
    parser.add_argument("--suggest-parents", help="Query the index and return top candidate parent node IDs without creating a node.")
    parser.add_argument("--no-index", action="store_true", help="Skip re-indexing SQLite database after node creation.")
    parser.add_argument("--json-output", action="store_true", help="Format CLI output as JSON.")

    args = parser.parse_args()
    vault_dir = get_vault_path(require_root=True)

    if args.suggest_parents:
        candidates = suggest_parents(args.suggest_parents, limit=10, vault_dir=vault_dir)
        if args.json_output:
            print(json.dumps(candidates, indent=2))
        else:
            print(f"Parent candidates for '{args.suggest_parents}':")
            for c in candidates:
                print(f"  [{c['id']}] ({c['type']}) {c['title']} — {c.get('summary', '')}")
        return

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

    existing_file = find_memory_file(vault_dir, args.id) if args.id else None
    if not existing_file and (not args.title or (not args.type and not args.auto_type)):
        parser.print_help(sys.stderr)
        print("\nError: --title and either --type or --auto-type are required when creating a new memory node.", file=sys.stderr)
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
        auto_type=args.auto_type,
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

