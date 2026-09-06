---
name: vault-admin
description: Rebuild vault index or migrate schema. Use after editing memories or schema.py.
---

Rebuild the index (run this after any memory creation or modification):
`uv run --env-file .env python scripts/indexer.py`

Migrate the schema (run this after modifying `scripts/schema.py`):
`uv run --env-file .env python scripts/migrate.py`
