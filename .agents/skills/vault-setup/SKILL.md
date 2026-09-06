---
name: vault-setup
description: Initialize a new Second Brain vault or link an existing one.
disable-model-invocation: true
---

Initialize a new vault:
```bash
uv run python scripts/setup.py --init "<path_to_empty_directory>"
```

Link an existing vault:
```bash
uv run python scripts/setup.py --link "<path_to_existing_vault>"
```

### Completion Criteria:
- `.env` file contains `VAULT_PATH='<path>'`.
- `00000000-root.md` exists in the target directory.
- `.index.sqlite3` is initialized and indexed.
