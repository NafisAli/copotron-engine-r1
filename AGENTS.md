# Second Brain Engine

Vault data lives at `VAULT_PATH` in `.env`. Run all commands via `uv` in `copotron-engine-r1/`.

## Retrieval

Query context through engine CLI scripts before opening files:
- **Search**: `uv run python scripts/search.py -q "<query>"` (BM25 FTS5 ranking across titles, summaries, tags, bodies).
- **Navigate**: `uv run python scripts/navigate.py --node "<id>" --direction <up|down>` (DAG edge traversal).
- **Inspect**: Read target Markdown files directly only after resolving IDs.
- **Persona**: Adopt instructions from any returned `inherited_persona`.

## Authoring & Editing

- **Direct edit**: Author `{id}-{slug}.md` in vault, validate with `uv run python scripts/validate.py <path>`, and index with `uv run python scripts/indexer.py`.
- **Crystallize**: Run `uv run python scripts/crystallize.py` for atomic creation or in-place node updates.

## Progressive Memory Formation

Accumulate context across turns within an active discussion phase. Avoid premature turn-by-turn memory creation.

Trigger crystallization on:
- **Phase transition**: Shifting between exploration, architecture, implementation, or testing—including looping back to revise earlier decisions.
- **Session close**: User signals a break ("talk later", "ordering parts now"), or 5-minute inactivity timer fires.
- **Explicit request**: User asks to save or crystallize.

Execution discipline:
- **Single-flight router (Pattern C + B)**: Check if a `vault-crystallizer` is already active (`running` or `idle`).
  - If active: Forward new phase context via `send_message(Recipient=conv_id, Message="...")`. Do not launch concurrent crystallizers.
  - If inactive: Dispatch via `invoke_subagent` (model: `flash`).
- **Zero blocking**: Respond to the user immediately in the main dialogue.
- **Zero pre-flight calls**: Dispatch without prior search or file reads; the subagent resolves references independently.
- **Receipt timing**: Emit the consolidated receipt footnote (`📌 *Memory crystallized: [id-slug]*`) only upon the subagent's completion wakeup.
