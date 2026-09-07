# Second Brain Engine

Vault data lives at `VAULT_PATH` in `.env`. Run all commands via `uv` in `copotron-engine-r1/`.

## Black-Box CLI Discipline

Treat the engine strictly as a black-box CLI tool (`copotron`).
- **CLI Commands**: Execute all operations via `uv run copotron <subcommand>`. Probe options and flags using `uv run copotron --help` and `uv run copotron <subcommand> --help`.
- **Hard Boundary**: Never read, inspect, or edit engine Python source code (`copotron/*.py`) or `.env` during normal memory operations. The CLI exposes all necessary query, navigation, domain discovery, indexing, and crystallization capabilities.

## Retrieval

Query context through the CLI before opening files:
- **Domains**: `uv run copotron domains` (dynamically list active domain hubs under root).
- **Search**: `uv run copotron search "<query>"` (BM25 FTS5 ranking across titles, summaries, tags, bodies).
- **Navigate**: `uv run copotron navigate "<id>" --direction <up|down>` (DAG edge traversal).
- **Inspect**: Read target Markdown files directly only after resolving IDs.
- **Persona**: Adopt instructions from any returned `inherited_persona`.

## Authoring & Editing

- **Direct edit**: Author `{id}-{slug}.md` in vault, validate with `uv run copotron validate <path>`, and index with `uv run copotron index`.
- **Crystallize**: Run `uv run copotron crystallize --manifest <path>` for atomic creation or in-place node updates.

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
