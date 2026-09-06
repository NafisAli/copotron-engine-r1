import sys
from pathlib import Path
from schema import parse_frontmatter_and_body, dump_frontmatter
from vault import get_vault_path, atomic_write_text

def migrate_vault(vault_dir: Path | None = None) -> dict:
    if vault_dir is None:
        vault_dir = get_vault_path(require_root=True)
        
    updated_count = 0
    unchanged_count = 0
    error_count = 0
    
    for file_path in sorted(vault_dir.rglob("*.md")):
        # Skip hidden files and directories
        if any(part.startswith(".") for part in file_path.relative_to(vault_dir).parts):
            continue

        if file_path.is_file():
            try:
                # parse_frontmatter_and_body applies Pydantic schema validation & defaults
                # extra="allow" ensures open-tail fields are preserved
                memory, body = parse_frontmatter_and_body(file_path)
                new_content = dump_frontmatter(memory, body)
                
                with open(file_path, "r", encoding="utf-8-sig") as f:
                    existing_content = f.read()
                
                # Dirty check: skip writing if content is unchanged to preserve mtime
                if existing_content != new_content:
                    atomic_write_text(file_path, new_content, encoding="utf-8")
                    updated_count += 1
                else:
                    unchanged_count += 1
                
            except Exception as e:
                print(f"Error migrating {file_path.name}: {e}", file=sys.stderr)
                error_count += 1
                
    print(f"Migration complete: {updated_count} files updated, {unchanged_count} unchanged, {error_count} errors.")
    return {"updated": updated_count, "unchanged": unchanged_count, "errors": error_count}

if __name__ == "__main__":
    result = migrate_vault()
    if result["errors"] > 0:
        sys.exit(1)
