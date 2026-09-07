# Second Brain Engine

Vault data lives at `VAULT_PATH` in `.env`. Run all commands via `uv` in `copotron-engine-r1/`.

## Black-Box CLI Discipline

Treat `copotron` strictly as a compiled binary tool.
- **CLI Commands**: Execute all operations via `uv run copotron <subcommand>`. Probe options and flags using `uv run copotron <subcommand> --help`.
- **Hard Boundary**: Never read, inspect, or edit engine Python source code (`copotron/*.py`) or `.env` during normal memory operations. The CLI exposes all necessary query, navigation, domain discovery, indexing, and crystallization capabilities.

## Memory Operations

- **Domains**: `uv run copotron domains` (dynamically list active domain hubs under root).
- **Search**: `uv run copotron search "<query>"` (BM25 FTS5 ranking across titles, summaries, tags, bodies).
- **Navigate**: `uv run copotron navigate "<id>" --direction <up|down>` (DAG edge traversal).
- **Crystallize**: `uv run copotron crystallize --manifest <path>` (atomic batch creation or in-place node updates).
- **Validate & Index**: `uv run copotron validate [path]` and `uv run copotron index`.
- **Persona**: Adopt instructions from any returned `inherited_persona`.

## Progressive Memory Formation

Accumulate context across conversation turns. Crystallize only on phase transitions, session close, or explicit user request.
- **Single-flight router (Pattern C + B)**: Check if a `vault-crystallizer` is already active (`running` or `idle`).
  - Active: Forward new phase context via `send_message(Recipient=conv_id, Message="...")`. Never launch concurrent crystallizers.
  - Inactive: Dispatch via `invoke_subagent` (model: `flash`).
- **Zero blocking**: Respond to the user immediately in the main dialogue.
- **Zero pre-flight**: Dispatch without prior search or file reads; the subagent resolves references independently.
- **Receipt timing**: Emit the consolidated receipt footnote (`📌 *Memory crystallized: [id-slug]*`) only upon subagent completion wakeup.
