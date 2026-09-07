import os
import sys
import argparse
from pathlib import Path
from datetime import datetime
from copotron.schema import MemorySchema, dump_frontmatter
from copotron.vault import load_env, find_env_file, atomic_write_text

def update_env_file(vault_path: Path):
    """Write or update VAULT_PATH in copotron-engine/.env."""
    env_file = find_env_file()
    if not env_file:
        env_file = Path(__file__).resolve().parent.parent / ".env"

    abs_path = str(vault_path.resolve())
    lines = []
    found = False

    if env_file.is_file():
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith("VAULT_PATH="):
                    lines.append(f"VAULT_PATH='{abs_path}'\n")
                    found = True
                else:
                    lines.append(line)

    if not found:
        lines.append(f"VAULT_PATH='{abs_path}'\n")

    atomic_write_text(env_file, "".join(lines))
    print(f"Updated {env_file} with VAULT_PATH='{abs_path}'")

def create_root_memory(vault_dir: Path):
    root_id = "00000000"
    root_filename = f"{root_id}-root.md"
    root_path = vault_dir / root_filename

    date_str = datetime.now().strftime("%Y-%m-%d")
    root_memory = MemorySchema(
        id=root_id,
        title="Root",
        date=date_str,
        summary="The origin of the Second Brain memory tree.",
        type="declarative",
        status="active",
        parents=[],
        tags=["root"],
        persona=None
    )
    root_body = "# Root\n\nWelcome to the Second Brain Vault. This is the starting point of the memory tree."
    content = dump_frontmatter(root_memory, root_body)

    atomic_write_text(root_path, content)
    print(f"Created root node: {root_filename}")

def setup_vault(init_path: str | None = None, link_path: str | None = None):
    # Case 1: Linking an existing vault
    if link_path:
        target_dir = Path(link_path).resolve()
        if not target_dir.exists() or not target_dir.is_dir():
            print(f"Error: Target directory does not exist: {target_dir}", file=sys.stderr)
            sys.exit(1)
        root_file = target_dir / "00000000-root.md"
        if not root_file.is_file():
            print(f"Error: Directory is missing '00000000-root.md': {target_dir}", file=sys.stderr)
            print("To initialize a new vault instead, use: --init <path>", file=sys.stderr)
            sys.exit(1)
        update_env_file(target_dir)
        os.environ["VAULT_PATH"] = str(target_dir)
        print(f"Successfully linked existing vault at {target_dir}")
        from indexer import load_vault
        load_vault()
        return

    # Case 2: Explicit init path provided
    if init_path:
        target_dir = Path(init_path).resolve()
        if target_dir.exists() and list(target_dir.glob("*.md")):
            print(f"Error: Target directory {target_dir} already contains .md files.", file=sys.stderr)
            print("Setup aborted to prevent overwriting existing data.", file=sys.stderr)
            sys.exit(1)
        target_dir.mkdir(parents=True, exist_ok=True)
        create_root_memory(target_dir)
        update_env_file(target_dir)
        os.environ["VAULT_PATH"] = str(target_dir)
        from indexer import load_vault
        load_vault()
        print(f"Successfully initialized new vault at {target_dir}")
        return

    # Case 3: No CLI flags; rely on existing .env
    load_env()
    raw_path = os.getenv("VAULT_PATH")
    if not raw_path or not raw_path.strip():
        print(
            "Error: VAULT_PATH is not configured in .env, and no path argument was provided.\n\n"
            "To initialize a new vault:\n"
            "  uv run copotron setup --init <path_to_directory>\n\n"
            "To link an existing vault:\n"
            "  uv run copotron setup --link <path_to_existing_vault>",
            file=sys.stderr
        )
        sys.exit(1)

    target_dir = Path(raw_path.strip()).resolve()
    if target_dir.exists() and list(target_dir.glob("*.md")):
        print(f"Vault at {target_dir} is already initialized and contains markdown memories.")
        print("Setup aborted to prevent overwriting.")
        return

    target_dir.mkdir(parents=True, exist_ok=True)
    create_root_memory(target_dir)
    from copotron.indexer import load_vault
    load_vault()
    print(f"Successfully initialized vault at {target_dir}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Initialize or link a Copotron Vault.")
    parser.add_argument("--init", type=str, help="Initialize a brand new vault in the specified directory.")
    parser.add_argument("--link", type=str, help="Link an existing vault directory in .env.")
    
    args = parser.parse_args()
    setup_vault(init_path=args.init, link_path=args.link)
