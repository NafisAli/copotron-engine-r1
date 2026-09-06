---
name: vault-admin
description: Synchronize vault memories into the SQLite index (.index.sqlite3). Trigger after creating, editing, or deleting memory files, or updating schema.
---

Incrementally sync vault memories into `.index.sqlite3`:
```bash
uv run python scripts/indexer.py
```

### Completion Criteria:
- Command completes with exit code 0.
- Output confirms indexed memory count and write target (e.g. `Indexed N memories ... to .../.index.sqlite3`).
