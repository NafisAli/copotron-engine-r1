---
name: vault-query
description: Search and navigate vault memory graph. Trigger when locating notes, exploring DAG parent/children, or discovering domain hubs.
---

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
When search or navigation returns a non-null `inherited_persona`, read that persona's Markdown note (`{id}-{slug}.md`) and adopt its instructions, tone, and constraints for subsequent actions in that context.
