---
name: vault-query
description: Search memories via FTS5 full-text or traverse DAG parent/child relationships. Trigger when finding relevant notes, exploring parent projects, or discovering tasks.
---

### 1. Dynamic Domain Hubs
List active domain hubs dynamically registered under root:
```bash
uv run copotron domains
```

### 2. Full-Text & Metadata Search
Search the index with keyword queries and relational filters:
```bash
uv run copotron search "<keywords>" --type "prospective" --status "active" --limit 20 --offset 0
```
- **`<query>` / `-q, --query`**: Full-text keyword matching across title, summary, tags, and note body with Porter stemming and BM25 relevance ranking. Also accepts direct 8-character hex IDs.
- **`--type`**: Filter by memory type (`episodic`, `declarative`, `procedural`, `prospective`).
- **`--status, -s`**: Filter by lifecycle status (`active`, `completed`, `archived`, `none`).
- **`--tag, -t`**: Filter by exact tag membership.
- **`--limit, -l`**: Result cap (default: `20`; use `0` for unlimited).
- **`--offset`**: Skip initial results for pagination.

### 3. DAG Edge Traversal
Traverse indexed parent/child relationships:
```bash
uv run copotron navigate "<node_id>" --direction "down" --status "active" --limit 20 --offset 0
```
- **`<node_id>` / `-n, --node`**: 8-character origin node ID.
- **`--direction, -d`**: `down` to list children (default), `up` to list parents.
- **`--status, -s`**: Filter returned nodes by status.
- **`--limit, -l` & `--offset`**: Paginate traversal results.

### 4. Persona Adoption
When search or navigation returns a non-null `inherited_persona`, read that persona's memory Markdown file (`{id}-{persona}.md`) and adopt its instructions, tone, and constraints for all subsequent actions in that context.
