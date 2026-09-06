# Second Brain Engine

Vault data lives at `VAULT_PATH` defined in `.env`.

## Reading Memories

Retrieve context through engine CLI scripts rather than bulk file scans:
- **Search**: `uv run python scripts/search.py -q "<query>"` for FTS5 full-text and BM25-ranked discovery across titles, summaries, tags, and note bodies.
- **Navigate**: `uv run python scripts/navigate.py --node "<id>" --direction <up|down>` for indexed parent/child DAG edge traversal.
- **Inspect**: Open individual Markdown files directly only after resolving target IDs from search or navigation.
- **Persona**: When results include an `inherited_persona`, read that persona's memory file and adopt its instructions.

## Modifying Memories

1. Create or edit Markdown memory files directly in the flat vault directory following `{id}-{slug}.md`.
2. Validate frontmatter: `uv run python scripts/validate.py <path_to_file>` (exit code 0 required).
3. Synchronize index: `uv run python scripts/indexer.py` to update the local SQLite index (`.index.sqlite3`).
