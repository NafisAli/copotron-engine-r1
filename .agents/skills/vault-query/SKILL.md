---
name: vault-query
description: Search vault index or navigate the memory tree. Use to find memories or trace context.
---

Search the flat index:
`uv run python scripts/search.py -q "<keywords>" --type "prospective" --status "active"`
(Filters `--type`, `--tag`, and `--status` are optional. Query `-q` matches all keywords).

Navigate the graph to find parent projects or child nodes:
`uv run python scripts/navigate.py --node "<node_id>" --direction "up"`
(Use `down` for children. Output includes `status`, `tags`, and `inherited_persona`).

When search returns an `inherited_persona`, read that persona's `.md` file and adopt its theme, vocabulary, and instructions for all subsequent responses.
