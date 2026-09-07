---
name: vault-crystallize
description: Crystallize conversational decisions and specs into DAG memory nodes. Trigger on phase transition, session close, or save request.
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
- **Domain Discovery**: List active domain hubs dynamically via `uv run copotron domains`.
- **Explicit IDs**: Pass known IDs directly to `--id <hex_id>` or in the manifest. Skip searching on known IDs.
- **New or unknown topics**: Query the vault with `uv run copotron search "<keywords>" --limit 5`.
- **Revisiting a phase**: Update existing notes in place via `id`.
- **New topic**: Parent to the matched domain hub (or use `--auto-parent`). Fall back to `00000000` (Root) if no hub matches.

#### Step 2: Manifest Creation via `write_to_file`
For multiple nodes or structured content, write a scratch JSON manifest:
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
    "title": "ESP32 Weather Station",
    "type": "prospective",
    "summary": "Outdoor telemetry project using ESP-NOW.",
    "parents": ["00000004"],
    "tags": ["esp32", "hardware"]
  }
]
```

#### Step 3: Commit via `copotron crystallize`
Run the manifest:
```bash
uv run copotron crystallize --manifest <path_to_manifest.json>
```
Or create a single node directly:
```bash
uv run copotron crystallize --title "..." --summary "..." --type declarative --parents "00000004"
```

#### Step 4: Ambient Receipt
Emit an unobtrusive footnote with verified node IDs:
- **Direct CLI Execution**: Append the footnote directly to your response.
- **Subagent Execution**: Emit footnote only upon completion wakeup; never during dispatch.

```markdown
---
📌 *Memory crystallized: `00000042-pi-plant-monitor-spec.md` (`declarative` under `00000004`).*
```

### Pattern C: Mid-Flight Delta Updates
When conversation pivots while crystallization is active:
1. Parent agent forwards the delta message via `send_message`.
2. Crystallizer incorporates changes into the manifest or runs in-place updates.
3. Crystallizer returns a single, consolidated receipt of all created and updated memories.

### Completion Contract
A successful `copotron crystallize` execution (exit code 0) is authoritative: schema validation and SQLite indexing are guaranteed. Immediately emit your receipt; skip redundant file inspection, manual validation, and git status checks.
