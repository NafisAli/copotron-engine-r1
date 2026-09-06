# Copotron Second Brain Engine

The deterministic logic and indexing engine for the AI-driven Second Brain.

## Overview
`copotron-engine` parses, indexes, searches, and validates markdown memory files located in the vault directory specified by `VAULT_PATH`.

## Setup & Configuration
The vault path is governed strictly by the `.env` file with **no fallback default**:
```env
VAULT_PATH='C:\Users\digit\Documents\Programming\copotron-r1\copotron-vault'
```

### Initializing or Linking a Vault
* **Initialize a new vault:**
  ```bash
  uv run python scripts/setup.py --init "<path_to_directory>"
  ```
* **Link an existing vault:**
  ```bash
  uv run python scripts/setup.py --link "<path_to_vault>"
  ```

## Core Scripts
* **Search Memory Index (`search.py`):**
  Multi-token flat search with type and status filtering:
  ```bash
  uv run python scripts/search.py -q "aws failure" --status active
  ```
* **Tree Navigation (`navigate.py`):**
  Traverse DAG relationships up (to parents) or down (to children):
  ```bash
  uv run python scripts/navigate.py --node "00000001" --direction down
  ```
* **Rebuild Index (`indexer.py`):**
  Re-parses all memories, resolves parent-child links, computes persona inheritance, and writes `graph.json`:
  ```bash
  uv run python scripts/indexer.py
  ```
* **Validate Frontmatter (`validate.py`):**
  Validates a single file or the entire vault against the Pydantic schema:
  ```bash
  uv run python scripts/validate.py [path_to_file.md]
  ```
* **Schema Migration (`migrate.py`):**
  Safely upgrades frontmatter while preserving open-tail metadata:
  ```bash
  uv run python scripts/migrate.py
  ```

## Running Tests
Run the automated test suite with pytest:
```bash
uv run pytest tests/
```
