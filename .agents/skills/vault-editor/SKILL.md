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
persona: null      # optional: 8-character id of a Persona Definition, e.g. "c19b60a6"
---
```
*Open Tail:* Arbitrary metadata fields outside core keys are preserved in the index.

*Parents:* Every memory except the Root (`00000000`) needs at least one parent id that exists in the vault. A non-Root memory with `parents: []` is an **Orphan**. `copotron crystallize` rejects Orphans and unknown parent ids, but direct edits and `validate` do not check them, so verify the ids yourself. An Orphan or a missing parent still indexes, but `copotron audit` flags it.

*Persona:* `persona` holds the id of a **Persona Definition**: a `declarative` memory tagged `persona`. Never write a name such as `aegis-null`. Find the definition with `uv run copotron search "persona <name>"` and copy its `id`. To add a Persona, create its definition first. `copotron crystallize` rejects any other value, but direct edits and `validate` do not check it, so verify the id yourself. A value that does not identify a Persona Definition is a **Dangling Persona**. It still indexes, but the audit flags it.

### 2. Validation & Indexing
```bash
uv run copotron validate <path_to_file>
uv run copotron index
```

### Completion Criteria:
1. File saved at `VAULT_PATH/{id}-{slug}.md`.
2. `uv run copotron validate <path>` exits 0.
3. `uv run copotron index` exits 0.
