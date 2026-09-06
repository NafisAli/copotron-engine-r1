import sys
import argparse
from pathlib import Path
from schema import parse_frontmatter
from pydantic import ValidationError
from vault import get_vault_path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

def validate_file(file_path: str | Path) -> bool:
    path = Path(file_path)
    if not path.exists():
        print(f"❌ Error: File {file_path} does not exist.", file=sys.stderr)
        return False
        
    try:
        memory = parse_frontmatter(path)
        print(f"✅ {path.name} is valid. (ID: {memory.id})")
        return True
    except ValidationError as e:
        print(f"❌ {path.name} validation failed:\n{e}", file=sys.stderr)
        return False
    except ValueError as e:
        print(f"❌ {path.name} parsing failed:\n{e}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"❌ {path.name} unexpected error:\n{e}", file=sys.stderr)
        return False

def validate_vault() -> int:
    vault_dir = get_vault_path(require_root=True)

    print(f"Validating all markdown files in {vault_dir}...")
    valid_count = 0
    error_count = 0
    
    for file_path in sorted(vault_dir.rglob("*.md")):
        # Skip hidden files and directories
        if any(part.startswith(".") for part in file_path.relative_to(vault_dir).parts):
            continue

        if file_path.is_file():
            if validate_file(file_path):
                valid_count += 1
            else:
                error_count += 1
                
    print(f"\nValidation complete: {valid_count} valid, {error_count} failed.")
    return error_count

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Validate memory frontmatter against the schema.")
    parser.add_argument("file", nargs="?", help="Path to a specific markdown file to validate.")
    
    args = parser.parse_args()
    if args.file:
        success = validate_file(args.file)
        sys.exit(0 if success else 1)
    else:
        errors = validate_vault()
        sys.exit(0 if errors == 0 else 1)
