---
name: vault-query
description: Search memories via FTS5 full-text or traverse DAG parent/child relationships. Trigger when finding relevant notes, exploring parent projects, or discovering tasks.
---

### 1. Full-Text & Metadata Search (`search.py`)
Search the index with keyword queries and relational filters:
```bash
uv run python scripts/search.py -q "<keywords>" --type "prospective" --status "active" --limit 20 --offset 0
```
- **`-q, --query`**: Full-text keyword matching across title, summary, tags, and note body with Porter stemming and BM25 relevance ranking.
- **`--type`**: Filter by memory type (`episodic`, `declarative`, `procedural`, `prospective`).
- **`--status, -s`**: Filter by lifecycle status (`active`, `completed`, `archived`, `none`).
- **`--tag, -t`**: Filter by exact tag membership.
- **`--limit, -l`**: Result cap (default: `20`; use `0` for unlimited).
- **`--offset`**: Skip initial results for pagination.

### 2. DAG Edge Traversal (`navigate.py`)
Traverse indexed parent/child relationships:
```bash
uv run python scripts/navigate.py --node "<node_id>" --direction "down" --status "active" --limit 20 --offset 0
```
- **`--node`**: 8-character origin node ID.
- **`--direction`**: `down` to list children, `up` to list parents.
- **`--status, -s`**: Filter returned nodes by status.
- **`--limit, -l` & `--offset`**: Paginate traversal results.

### 3. Persona Adoption
When search or navigation returns a non-null `inherited_persona`, read that persona's memory Markdown file (`{id}-{persona}.md`) and adopt its instructions, tone, and constraints for all subsequent actions in that context.
