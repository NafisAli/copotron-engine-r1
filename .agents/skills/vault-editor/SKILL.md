---
name: vault-editor
description: Author, edit, and validate vault memory files. Trigger when creating memories, modifying frontmatter, or updating markdown notes.
---

Author and edit `.md` files directly in the flat vault directory.

### 1. File Naming
Files must follow the pattern: `{id}-{slug}.md`
- `{id}`: 8-character unique identifier (e.g. 8-digit hex prefix or numeric ID).
- `{slug}`: lowercase, hyphen-separated title (e.g. `mandalay-build-and-engineering.md`).

### 2. Frontmatter Schema
```yaml
---
id: "00000001"
title: "Note Title"
date: "2026-09-06"
summary: "Concise 1-2 sentence description."
type: declarative  # episodic | declarative | procedural | prospective
status: active     # active | completed | archived | none
parents:           # list of parent 8-character node IDs
  - "00000000"
tags:              # list of semantic tags
  - "domain"
persona: null      # optional persona identifier
---
```
*Open Tail:* Arbitrary metadata fields outside core keys are fully supported and preserved in the index.

### 3. Validation & Indexing
```bash
uv run copotron validate <path_to_file>
uv run copotron index
```

### Completion Criteria:
1. File exists at `VAULT_PATH/{id}-{slug}.md`.
2. `copotron validate <path>` passes with exit code 0.
3. `copotron index` runs and successfully commits updates to `.index.sqlite3`.
