---
name: vault-query
description: Search vault index or navigate the memory tree. Use to find memories or trace context.
---

Search the flat index:
`uv run python scripts/search.py -q "<keywords>" --type "prospective" --status "active" --limit 20 --offset 0`
(Filters `--type`, `--tag`, and `--status` are optional. Query `-q` matches all keywords. Use `--limit` / `-l` to bound output [default: 20; 0 for unlimited] and `--offset` to paginate).

Navigate the graph to find parent projects or child nodes:
`uv run python scripts/navigate.py --node "<node_id>" --direction "down" --status "active" --limit 20 --offset 0`
(Use `down` for children, `up` for parents. Output includes `status`, `tags`, and `inherited_persona`. Filter results by `--status` / `-s`, and paginate with `--limit` / `-l` and `--offset`).

When search returns an `inherited_persona`, read that persona's `.md` file and adopt its theme, vocabulary, and instructions for all subsequent responses.
