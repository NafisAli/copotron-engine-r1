# Copotron Second Brain Engine

The deterministic logic and indexing engine for the AI-driven Second Brain.

## Overview
`copotron-engine` parses, indexes, searches, and validates markdown memory files located in the vault directory specified by `VAULT_PATH`.

## Setup & Configuration
The vault path is governed strictly by the `.env` file with **no fallback default**:
```env
VAULT_PATH='C:\Users\digit\Documents\Programming\copotron-r1\copotron-vault-r1'
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
  FTS5 full-text keyword search across titles, summaries, tags, and note bodies with BM25 ranking, plus metadata filtering:
  ```bash
  uv run python scripts/search.py -q "aws failure" --status active
  ```
* **Tree Navigation (`navigate.py`):**
  Instant indexed DAG edge traversal up (to parents) or down (to children) via SQLite:
  ```bash
  uv run python scripts/navigate.py --node "00000001" --direction down
  ```
* **Rebuild Index (`indexer.py`):**
  Incrementally synchronizes memories, DAG links, and inherited personas into the local SQLite index (`.index.sqlite3`):
  ```bash
  uv run python scripts/indexer.py
  ```
* **Validate Frontmatter (`validate.py`):**
  Validates a single file or the entire vault against the Pydantic schema:
  ```bash
  uv run python scripts/validate.py [path_to_file.md]
  ```

## Running Tests
Run the automated test suite with pytest:
```bash
uv run pytest tests/
```
