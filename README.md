# Copotron Second Brain Engine

The deterministic logic, indexing engine, and black-box CLI for the AI-driven Second Brain.

## Overview
`copotron` parses, indexes, searches, navigates, and crystallizes markdown memory notes located in the vault directory specified by `VAULT_PATH`.

## Setup & Configuration
The vault path is governed strictly by the `.env` file with **no fallback default**:
```env
VAULT_PATH='C:\Users\digit\Documents\Programming\copotron-r1\copotron-vault-r1'
```

### Initializing or Linking a Vault
* **Initialize a new vault:**
  ```bash
  uv run copotron setup --init "<path_to_directory>"
  ```
* **Link an existing vault:**
  ```bash
  uv run copotron setup --link "<path_to_vault>"
  ```

## Unified CLI (`copotron`)

Run `uv run copotron --help` for full command-line options and examples.

* **Domain Hubs (`copotron domains`):**
  Dynamically lists all domain hubs currently active under root node `00000000`:
  ```bash
  uv run copotron domains
  ```

* **Search Memory Index (`copotron search`):**
  FTS5 BM25 full-text keyword search across titles, summaries, tags, and note bodies, with direct ID matching and metadata filtering:
  ```bash
  uv run copotron search "aws failure" --status active
  ```

* **Tree Navigation (`copotron navigate`):**
  Instant indexed DAG edge traversal up (to parents) or down (to children) via SQLite:
  ```bash
  uv run copotron navigate "00000001" --direction down
  ```

* **Crystallize Memories (`copotron crystallize`):**
  Create new memory notes atomically or update existing nodes in-place from a JSON manifest:
  ```bash
  uv run copotron crystallize --manifest <path_to_manifest.json>
  ```
  Or create a single node directly:
  ```bash
  uv run copotron crystallize --title "Note Title" --summary "Summary" --type declarative --parents "00000004"
  ```

* **Rebuild / Sync Index (`copotron index`):**
  Incrementally synchronizes memories, DAG links, and inherited personas into the local SQLite index (`.index.sqlite3`):
  ```bash
  uv run copotron index
  ```

* **Validate Frontmatter (`copotron validate`):**
  Validates a single file or the entire vault against the Pydantic schema (skipping non-memory docs like `README.md`):
  ```bash
  uv run copotron validate [path_to_file.md]
  ```

## Running Tests
Run the automated test suite with pytest:
```bash
uv run pytest
```
