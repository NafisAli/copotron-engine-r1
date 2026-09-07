---
name: vault-admin
description: Synchronize and validate the SQLite vault index. Trigger after manual file edits, deletions, or schema updates.
---

### 1. Index Synchronization
Incrementally synchronize vault Markdown files into `.index.sqlite3`:
```bash
uv run copotron index
```

### 2. Vault Schema Validation
Validate all markdown notes in the vault (skips non-memory docs like `README.md`):
```bash
uv run copotron validate
```

### Completion Criteria:
- `uv run copotron index` exits 0 and reports indexed memory count.
- `uv run copotron validate` exits 0 with 0 failures.
