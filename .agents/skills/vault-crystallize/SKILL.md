---
name: vault-crystallize
description: Crystallize conversational decisions, technical specs, or task lists into validated DAG vault memories. Trigger on phase transition, session close, or explicit save request.
---

Extract durable insights from conversation and commit schema-compliant DAG memory nodes to `VAULT_PATH`.

### 1. Extraction Filter

Partition content into Copotron memory types:
- **`declarative`**: Verified facts, pinouts, component specs, architectural decisions, and rejected trade-offs.
- **`procedural`**: Tested commands, configuration steps, and reproducible scripts.
- **`prospective`**: Overarching project goals or concrete next-step action items.
- **`episodic`**: 2-3 sentence session retrospective (date, topic, context).

### 2. Execution Sequence

#### Step 1: Resolution & Search-Before-Create
- **Explicit IDs provided**: When node IDs are known or passed in the task, pass them directly to `--id <hex_id>` or the manifest. Do not search for known IDs.
- **New or unknown topics**: Query the vault to locate parent hubs or identify existing nodes to update:
  ```bash
  uv run python scripts/search.py -q "<topic keywords>" --limit 5
  ```
- **Revisiting a phase**: If a node for this topic already exists, update it in place using its ID.
- **New topic**: Use the matched domain hub as parent. Fall back to `00000000` (Root) if no hub matches.

#### Step 2: Manifest Creation via `write_to_file`
When batching multiple nodes or long bodies, write the manifest to a scratch JSON file using `write_to_file`:
```json
[
  {
    "id": "e7b76f80",
    "summary": "Updated architecture with S3 payload buffering.",
    "body": "Revisited decision: S3 pre-signed URLs bypass Redis RAM limits.",
    "append_body": true
  },
  {
    "temp_ref": "proj",
    "title": "Project Title",
    "type": "prospective",
    "summary": "Project summary.",
    "parents": ["00000004"],
    "tags": ["project"]
  }
]
```

#### Step 3: Commit via `scripts/crystallize.py`
Run the manifest:
```bash
uv run python scripts/crystallize.py --manifest <path_to_manifest.json>
```

#### Step 4: Ambient Receipt
Emit an unobtrusive footnote with verified node IDs:
- **Direct CLI Execution**: Append the footnote directly to your response.
- **Subagent Execution**: Do not emit a footnote during the dispatch turn. Emit the footnote only upon reactive wakeup after subagent completion.

```markdown
---
📌 *Memory crystallized: `00000042-pi-plant-monitor-spec.md` (`declarative` under `00000004`).*
```

### Pattern C: Mid-Flight Delta Updates
If an ongoing conversation rapidly pivots while crystallization is active:
1. The parent forwards the delta message via `send_message`.
2. The crystallizer incorporates the delta into its pending manifest or updates affected nodes in-place.
3. The crystallizer returns a single, consolidated list of all created and updated memories.

### Completion Criteria:
1. Every target insight is written or updated in a valid `{id}-{slug}.md` file via `crystallize.py` (exit code 0).
2. SQLite index is updated in `.index.sqlite3` (guaranteed automatically by `crystallize.py`).
3. Zero post-verification overhead: when `crystallize.py` exits with 0, proceed directly to receipt emission without re-reading files or running manual indexer/git checks.
