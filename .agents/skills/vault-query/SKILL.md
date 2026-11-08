---
name: vault-query
description: Search and navigate vault memory graph. Trigger when locating notes, exploring DAG parent/children, or discovering domain hubs.
---

`domains`, `search` and `navigate` print readable text by default. Add `--json` for the full record (`file_path`, `inherited_persona`, `inherited_persona_title`).

### 1. Dynamic Domain Hubs
List active domain hubs dynamically registered under root:
```bash
uv run copotron domains
```

### 2. Full-Text & Metadata Search
Search the index by keywords, tags, status, or direct 8-character hex IDs:
```bash
uv run copotron search "<query>" [--type declarative|procedural|prospective|episodic] [--status active|completed|archived] [--tag <tag>] [--limit 20]
```
Uses SQLite FTS5 BM25 relevance ranking across titles, summaries, tags, and bodies. Probe additional options with `uv run copotron search --help`.

### 3. DAG Edge Traversal
Traverse parent/child relationships:
```bash
uv run copotron navigate "<node_id>" --direction <down|up> [--status active|completed|archived] [--limit 20]
```
- `--direction down`: Lists children (default).
- `--direction up`: Lists parents.

### 4. Persona Adoption
Each result carries its Inherited Persona as two fields:
- `inherited_persona`: the Persona Definition's 8-character id.
- `inherited_persona_title`: that definition's title, a label for deciding whether the persona matters here.

When the persona applies, open `{inherited_persona}-*.md` and adopt its instructions, tone, and constraints for subsequent actions in that context.

`inherited_persona_title: null` with a non-null `inherited_persona` is a Dangling Persona: the value names no Persona Definition (often a legacy free-text name like `aegis-null`). Text output marks it `(dangling)`. Proceed without a persona and surface it with `uv run copotron audit`.
