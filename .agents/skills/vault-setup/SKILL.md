---
name: vault-setup
description: Initialize a new Second Brain vault or link an existing one.
disable-model-invocation: true
---

Initialize a new vault:
```bash
uv run copotron setup --init "<path_to_empty_directory>"
```

Link an existing vault:
```bash
uv run copotron setup --link "<path_to_existing_vault>"
```

### Completion Criteria:
1. `.env` contains `VAULT_PATH='<path>'`.
2. `00000000-root.md` exists in target directory.
3. `.index.sqlite3` is initialized and indexed.
