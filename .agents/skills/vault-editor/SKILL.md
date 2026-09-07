---
name: vault-editor
description: Author, edit, and validate vault markdown files directly. Trigger when modifying frontmatter, editing notes in place, or updating schema.
---

Author and edit `.md` files directly in the flat vault directory.

### 1. File Naming & Schema
Format: `VAULT_PATH/{id}-{slug}.md` (`{id}`: 8-character hex/numeric ID; `{slug}`: lowercase hyphenated title).

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
*Open Tail:* Arbitrary metadata fields outside core keys are preserved in the index.

### 2. Validation & Indexing
```bash
uv run copotron validate <path_to_file>
uv run copotron index
```

### Completion Criteria:
1. File saved at `VAULT_PATH/{id}-{slug}.md`.
2. `uv run copotron validate <path>` exits 0.
3. `uv run copotron index` exits 0.
