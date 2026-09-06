---
name: vault-editor
description: Write, edit, and validate memory files. Use when creating or modifying vault memories.
---

Write and modify vault `.md` files directly in the flat vault directory.

### Naming Convention:
Files must be named: `{id}-{slug}.md`
- `{id}`: 8-character unique identifier (e.g. 8-digit hex prefix from SHA-256 or numeric ID).
- `{slug}`: lowercase, hyphen-separated title (e.g. `mandalay-build-and-engineering.md`).

### Frontmatter Schema:
- `id`: required 8-character string.
- `title`: required string.
- `date`: required string in `YYYY-MM-DD` format.
- `summary`: required 1-2 sentence string.
- `type`: `episodic`, `declarative`, `procedural`, or `prospective`.
- `status`: `active`, `completed`, `archived`, or `none`.
- `parents`: optional list of parent 8-character node IDs (defaults to `[]`).
- `tags`: optional list of strings (defaults to `[]`).
- `persona`: optional persona identifier string.
- *Open Tail:* Custom metadata fields are fully supported and preserved.

### Validation:
Every edit must pass schema validation:
`uv run python scripts/validate.py <file_path>`

### Completion Criteria:
1. File is saved with the correct `{id}-{slug}.md` naming convention.
2. `validate.py` passes with no errors (exit code 0).
3. The graph indexer is run: `uv run python scripts/indexer.py`.
