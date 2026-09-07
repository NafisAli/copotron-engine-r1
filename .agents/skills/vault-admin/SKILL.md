---
name: vault-admin
description: Synchronize vault memories into the SQLite index (.index.sqlite3) and validate frontmatter integrity. Trigger after creating, editing, or deleting memory files, or updating schema.
---

### 1. Index Synchronization
Incrementally sync vault memories into `.index.sqlite3`:
```bash
uv run copotron index
```

### 2. Vault-Wide Schema Validation
Validate all markdown notes in the vault (skipping documentation files like README.md):
```bash
uv run copotron validate
```

### Completion Criteria:
- `copotron index` completes with exit code 0 and reports indexed count.
- `copotron validate` completes with exit code 0 (0 failed).
