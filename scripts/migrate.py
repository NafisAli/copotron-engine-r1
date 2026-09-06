import sys
from pathlib import Path
from schema import parse_frontmatter, dump_frontmatter
from vault import get_vault_path

def migrate_vault():
    vault_dir = get_vault_path(require_root=True)
        
    success_count = 0
    error_count = 0
    
    for file_path in sorted(vault_dir.rglob("*.md")):
        # Skip hidden files and directories
        if any(part.startswith(".") for part in file_path.relative_to(vault_dir).parts):
            continue

        if file_path.is_file():
            try:
                # parse_frontmatter applies Pydantic schema validation & defaults
                # extra="allow" ensures open-tail fields are preserved
                memory = parse_frontmatter(file_path)
                
                with open(file_path, "r", encoding="utf-8-sig") as f:
                    content = f.read().lstrip()
                parts = content.split("---", 2)
                body = parts[2].lstrip("\r\n") if len(parts) >= 3 else ""
                
                new_content = dump_frontmatter(memory, body)
                
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(new_content)
                success_count += 1
                
            except Exception as e:
                print(f"Error migrating {file_path.name}: {e}", file=sys.stderr)
                error_count += 1
                
    print(f"Migration complete: {success_count} files successfully updated, {error_count} errors.")
    if error_count > 0:
        sys.exit(1)

if __name__ == "__main__":
    migrate_vault()
