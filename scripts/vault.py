import os
import sys
from pathlib import Path

def find_env_file() -> Path | None:
    """Locate .env in copotron-engine directory or current working directory."""
    # Check parent of scripts/ (i.e. copotron-engine)
    engine_env = Path(__file__).resolve().parent.parent / ".env"
    if engine_env.is_file():
        return engine_env
    # Check current working directory
    cwd_env = Path.cwd() / ".env"
    if cwd_env.is_file():
        return cwd_env
    return None

def load_env():
    """Load key-value pairs from .env into os.environ if not already set."""
    env_file = find_env_file()
    if not env_file:
        return
    with open(env_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip("'\"")
            if key and key not in os.environ:
                os.environ[key] = val

def get_vault_path(require_root: bool = True) -> Path:
    """
    Resolve and validate VAULT_PATH strictly from environment / .env file.
    Has NO fallback directory.
    If VAULT_PATH is unset or invalid, halts execution with exit code 1.
    """
    load_env()
    raw_path = os.getenv("VAULT_PATH")

    if not raw_path or not raw_path.strip():
        print(
            "Error: No vault configured. VAULT_PATH is not set in environment or .env file.\n\n"
            "To configure a vault:\n"
            "  • Setup a new vault:\n"
            "      uv run python scripts/setup.py --init <path_to_directory>\n"
            "  • Link an existing vault:\n"
            "      Set VAULT_PATH='<path_to_vault>' in .env\n"
            "      Then run: uv run python scripts/indexer.py",
            file=sys.stderr
        )
        sys.exit(1)

    vault_dir = Path(raw_path.strip())

    if not vault_dir.exists() or not vault_dir.is_dir():
        print(
            f"Error: Configured VAULT_PATH does not exist or is not a directory: {vault_dir}\n\n"
            "To initialize this directory as a new vault:\n"
            f"  uv run python scripts/setup.py --init \"{vault_dir}\"\n"
            "Or update VAULT_PATH in .env to link your existing vault.",
            file=sys.stderr
        )
        sys.exit(1)

    if require_root:
        root_file = vault_dir / "00000000-root.md"
        if not root_file.is_file():
            print(
                f"Error: Directory at VAULT_PATH is not a valid Copotron vault (missing '00000000-root.md'):\n"
                f"  {vault_dir}\n\n"
                "To initialize this directory as a vault:\n"
                "  uv run python scripts/setup.py\n"
                "Or update VAULT_PATH in .env to link your existing vault.",
                file=sys.stderr
            )
            sys.exit(1)

    return vault_dir
