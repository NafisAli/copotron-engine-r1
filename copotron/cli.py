import sys
import json
import argparse
from pathlib import Path

from copotron.search import search_graph
from copotron.navigate import navigate
from copotron.domains import get_domain_hubs, resolve_auto_parent
from copotron.validate import validate_file, validate_vault
from copotron.indexer import load_vault
from copotron.crystallize import (
    create_or_update_memory_node,
    crystallize_manifest,
    suggest_parents,
)
from copotron.setup import setup_vault

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def cmd_domains(args) -> int:
    """List all active domain hubs currently registered in the vault."""
    hubs = get_domain_hubs()
    if getattr(args, "json", False):
        print(json.dumps(hubs, indent=2))
    else:
        if not hubs:
            print("No domain hubs found under root '00000000'.")
            return 0
        print(f"Active Domain Hubs ({len(hubs)}):")
        for h in hubs:
            tags_str = f" [{', '.join(h['tags'])}]" if h["tags"] else ""
            print(f"  • [{h['id']}] {h['title']}{tags_str}")
            if h.get("summary"):
                print(f"      {h['summary']}")
    return 0


def cmd_search(args) -> int:
    """Search vault index via FTS5 BM25 or direct ID matching."""
    query = args.query or args.query_flag
    search_graph(
        query=query,
        tag=args.tag,
        memory_type=args.type,
        status=args.status,
        limit=args.limit,
        offset=args.offset,
        print_output=True,
    )
    return 0


def cmd_navigate(args) -> int:
    """Traverse DAG hierarchy up to parents or down to children."""
    node_id = args.node or args.node_flag
    if not node_id:
        print("Error: Node ID is required to navigate.", file=sys.stderr)
        return 1
    navigate(
        node_id=node_id,
        direction=args.direction,
        limit=args.limit,
        offset=args.offset,
        status=args.status,
        print_output=True,
    )
    return 0


def cmd_validate(args) -> int:
    """Validate frontmatter against schema, skipping non-memory documentation files."""
    is_json = getattr(args, "json", False)
    if args.file:
        success = validate_file(args.file, silent=is_json)
        if is_json:
            print(json.dumps({"valid": success, "file": str(args.file)}))
        return 0 if success else 1
    else:
        errors = validate_vault(silent=is_json)
        if is_json:
            print(json.dumps({"valid": errors == 0, "errors": errors}))
        return 0 if errors == 0 else 1


def cmd_index(args) -> int:
    """Incrementally synchronize Markdown vault memories into SQLite local index (.index.sqlite3)."""
    is_json = getattr(args, "json", False)
    graph = load_vault(silent=is_json)
    if is_json:
        print(json.dumps({"indexed": True, "count": len(graph)}))
    return 0


def cmd_setup(args) -> int:
    """Initialize a new vault or link an existing directory in .env."""
    setup_vault(init_path=args.init, link_path=args.link)
    return 0


def cmd_crystallize(args) -> int:
    """Create or update memory notes atomically."""
    from copotron.vault import get_vault_path
    vault_dir = get_vault_path(require_root=True)

    if args.suggest_parents:
        candidates = suggest_parents(args.suggest_parents, limit=args.limit, vault_dir=vault_dir)
        if getattr(args, "json", False) is True:
            print(json.dumps(candidates, indent=2))
        else:
            print(f"Parent candidates for '{args.suggest_parents}':")
            for c in candidates:
                print(f"  [{c['id']}] ({c['type']}) {c['title']} — {c.get('summary', '')[:80]}")
        return 0

    # Batch manifest mode
    manifest_data = None
    if args.manifest:
        m_str = args.manifest.strip()
        if m_str.startswith("[") or m_str.startswith("{"):
            manifest_data = json.loads(m_str)
        else:
            manifest_path = Path(args.manifest)
            if not manifest_path.exists():
                print(f"Error: Manifest file '{manifest_path}' does not exist.", file=sys.stderr)
                return 1
            manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    elif isinstance(args.json, str) and args.json:
        manifest_data = json.loads(args.json)

    if manifest_data is not None:
        results = crystallize_manifest(
            vault_dir=vault_dir,
            manifest_nodes=manifest_data,
            auto_index=not args.no_index,
            quiet_index=True,
        )
        print(json.dumps(results, indent=2))
        return 0

    # Single node mode
    if not args.id and not args.title:
        print("Error: Either --manifest, --id, or --title is required to crystallize memories.", file=sys.stderr)
        return 1

    result = create_or_update_memory_node(
        vault_dir=vault_dir,
        title=args.title,
        memory_type=args.type,
        summary=args.summary or "",
        body=args.body or "",
        append_body=args.append_body,
        parents=args.parents,
        tags=args.tags,
        status=args.status or "active",
        node_id=args.id,
        auto_parent=args.auto_parent,
    )
    if not args.no_index:
        load_vault(vault_dir, silent=True)

    print(json.dumps(result, indent=2))
    return 0


CRYSTALLIZE_EPILOG = """
Manifest Schema & Examples:
  Write manifests as JSON files and run: copotron crystallize --manifest <path>

  Format:
  [
    {
      "temp_ref": "proj",
      "title": "ESP32 Outdoor Weather Station",
      "type": "prospective",
      "summary": "18650-powered weather station using ESP-NOW.",
      "parents": ["00000004"],
      "tags": ["esp32", "hardware"]
    },
    {
      "title": "BME280 Sensor Spec",
      "type": "declarative",
      "summary": "Bosch BME280 I2C pinouts and power budget.",
      "parents": ["$proj"],
      "tags": ["sensor", "i2c"],
      "body": "## Hardware Details\\n\\nPinout: GPIO 21 SDA, GPIO 22 SCL."
    },
    {
      "id": "2b8f071e",
      "summary": "Updated architecture with ESP-NOW uplink.",
      "body": "Revisited decision: ESP-NOW cuts active radio time to 15ms.",
      "append_body": true
    }
  ]
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="copotron",
        description="Copotron: Second Brain Cognitive Memory Engine CLI",
        epilog="Use 'copotron <command> --help' for command-specific options and examples.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True, help="Available engine commands")

    # 1. domains
    p_domains = subparsers.add_parser("domains", help="List active vault domain hubs dynamically")
    p_domains.add_argument("--json", action="store_true", help="Output domain hubs in JSON format")
    p_domains.set_defaults(func=cmd_domains)

    # 2. search
    p_search = subparsers.add_parser("search", help="Search vault memories using FTS5 BM25 or direct IDs")
    p_search.add_argument("query", nargs="?", default=None, help="Keyword query or 8-char hex IDs (positional)")
    p_search.add_argument("--query", "-q", dest="query_flag", default=None, help="Keyword query or 8-char hex IDs")
    p_search.add_argument("--tag", "-t", type=str, help="Filter by tag")
    p_search.add_argument("--type", type=str, choices=["declarative", "procedural", "prospective", "episodic"], help="Filter by memory type")
    p_search.add_argument("--status", "-s", type=str, choices=["active", "completed", "archived", "none"], help="Filter by status")
    p_search.add_argument("--limit", "-l", type=int, default=20, help="Max results (default: 20; 0 for all)")
    p_search.add_argument("--offset", type=int, default=0, help="Results offset (default: 0)")
    p_search.add_argument("--json", action="store_true", help="Output results in JSON format")
    p_search.set_defaults(func=cmd_search)

    # 3. navigate
    p_nav = subparsers.add_parser("navigate", help="Traverse DAG hierarchy (parents up, children down)")
    p_nav.add_argument("node", nargs="?", default=None, help="8-character Node ID to navigate from (positional)")
    p_nav.add_argument("--node", "-n", dest="node_flag", default=None, help="8-character Node ID to navigate from")
    p_nav.add_argument("--direction", "-d", choices=["up", "down"], default="down", help="Direction: up (parents) or down (children; default)")
    p_nav.add_argument("--status", "-s", type=str, choices=["active", "completed", "archived", "none"], help="Filter by status")
    p_nav.add_argument("--limit", "-l", type=int, default=20, help="Max results (default: 20; 0 for all)")
    p_nav.add_argument("--offset", type=int, default=0, help="Results offset (default: 0)")
    p_nav.add_argument("--json", action="store_true", help="Output results in JSON format")
    p_nav.set_defaults(func=cmd_navigate)

    # 4. crystallize
    p_cryst = subparsers.add_parser(
        "crystallize",
        help="Create new memory notes or update existing notes in-place",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=CRYSTALLIZE_EPILOG,
    )
    p_cryst.add_argument("--manifest", "-m", type=str, help="Path to a JSON manifest file or JSON string")
    p_cryst.add_argument("--json", "-j", nargs="?", const=True, default=False, help="JSON manifest string or JSON output flag")
    p_cryst.add_argument("--id", type=str, help="Existing 8-character ID to update in-place")
    p_cryst.add_argument("--title", type=str, help="Memory title")
    p_cryst.add_argument("--type", type=str, choices=["declarative", "procedural", "prospective", "episodic"], help="Memory biological type")
    p_cryst.add_argument("--summary", type=str, help="1-2 sentence memory summary")
    p_cryst.add_argument("--body", type=str, help="Markdown body content")
    p_cryst.add_argument("--append-body", action="store_true", help="Append body content to existing note instead of replacing")
    p_cryst.add_argument("--parents", "-p", nargs="*", default=None, help="Parent 8-character IDs")
    p_cryst.add_argument("--tags", "-t", nargs="*", default=None, help="Tags for taxonomy")
    p_cryst.add_argument("--status", type=str, choices=["active", "completed", "archived", "none"], default="active", help="Lifecycle status")
    p_cryst.add_argument("--auto-parent", action="store_true", help="Automatically determine the best domain parent hub")
    p_cryst.add_argument("--suggest-parents", type=str, help="Search for candidate parent nodes matching a keyword query")
    p_cryst.add_argument("--limit", "-l", type=int, default=5, help="Max candidates for parent suggestion (default: 5)")
    p_cryst.add_argument("--no-index", action="store_true", help="Skip automatic SQLite re-indexing after creation")
    p_cryst.set_defaults(func=cmd_crystallize)

    # 5. validate
    p_val = subparsers.add_parser("validate", help="Validate frontmatter schema (skips non-memory documentation files)")
    p_val.add_argument("file", nargs="?", help="Specific markdown file to validate (validates all if omitted)")
    p_val.add_argument("--json", action="store_true", help="Output validation results as JSON")
    p_val.set_defaults(func=cmd_validate)

    # 6. index
    p_index = subparsers.add_parser("index", help="Synchronize Markdown vault notes into SQLite local index")
    p_index.add_argument("--json", action="store_true", help="Output indexing status as JSON")
    p_index.set_defaults(func=cmd_index)

    # 7. setup
    p_setup = subparsers.add_parser("setup", help="Initialize or link a Copotron Vault")
    p_setup.add_argument("--init", type=str, help="Initialize a brand new vault in the specified directory")
    p_setup.add_argument("--link", type=str, help="Link an existing vault directory in .env")
    p_setup.set_defaults(func=cmd_setup)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    ret = args.func(args)
    return ret if ret is not None else 0


if __name__ == "__main__":
    sys.exit(main())
