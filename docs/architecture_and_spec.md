# Copotron R1: Second Brain Architecture & Spec

This document captures the architectural blueprint and operational model for the AI-driven Second Brain, aligned with the implementation in `copotron-engine`.

## 1. High-Level Architecture
The system separates logic from data:
* **The Vault (Data):** A completely flat directory of Markdown files (`copotron-vault`). No subfolders are used, ensuring relative links never break and file paths remain deterministic.
* **The Engine (Logic & Agent Hub):** A Python-based repository (`copotron-engine`, managed via `uv`) containing deterministic scripts that index, parse, search, and validate the Vault. The agent executes directly inside the engine directory.

## 2. The AI-First Flat Vault
The system abandons traditional folder hierarchies (like strict PARA). Relationships are formed entirely via **YAML Frontmatter** validated through Pydantic:
* Files are strictly flat and never moved.
* Files follow the naming convention: `{id}-{slug}.md` (where `{id}` is an 8-character identifier).
* Retrieval relies on indexed graph traversal and metadata rather than directory browsing.

## 3. Cognitive Memory Schema (`schema.py`)
The brain is modeled as a Directed Acyclic Graph (DAG) of "Memories". The schema enforces a **Strict Core, Open Tail** model:

### Core Fields:
* **`id`** (str): 8-character unique identifier (e.g. `00000000` or SHA-256 hash prefix).
* **`title`** (str): Name of the memory.
* **`date`** (str): Date in `YYYY-MM-DD` format.
* **`summary`** (str): Concise 1-2 sentence summary for AI context scanning.
* **`type`** (enum): Biological memory type:
  * `episodic`: Time-bound logs, daily journals, events.
  * `declarative`: Factual knowledge, reference, architecture docs.
  * `procedural`: How-tos, SOPs, workflows, cheat sheets.
  * `prospective`: Future intentions, projects, tasks, and action items.
* **`status`** (enum): Lifecycle status: `active`, `completed`, `archived`, `none`.
* **`parents`** (List[str]): List of parent 8-character node IDs.
* **`tags`** (List[str]): Semantic tags for taxonomy and filtering.
* **`persona`** (Optional[str]): 8-character id of a Persona Definition, attached to roots or branch overrides. Write paths reject any other value; indexing accepts any string, so a Dangling Persona still indexes.
* **`implants`** (List[str]): Ids of the Implant Instructions this memory attaches (see §7). Omitted from frontmatter when empty. The schema requires a list and coerces its entries like `parents`, so an entry that is not an id never fails the memory: it indexes as a dangling implant link, which the audit reports.

### Open Tail:
Additional arbitrary metadata keys may be included for semantic flexibility and must be preserved during migrations and re-indexing.

## 4. The Memory Tree & Task Hierarchy
Instead of explicit separate "Project" and "Task" schemas, the system uses the `prospective` type combined with the `parents` array:
* A `prospective` memory with a domain hub as parent represents a **Project**.
* A `prospective` memory that points to another prospective memory represents a **Task** / **Subtask**.
* This enables infinitely nestable hierarchy while keeping the schema lean.

## 5. Persona System & Cascading Inheritance
Personas dictate AI tone, domain instructions, and behavior:
* **Storage:** Each Persona lives in a Persona Definition: a `declarative` memory tagged `persona`. Other memories reference it by id (`persona: c19b60a6`), never by name. `copotron.core.personas` is the shared lookup: `find_persona_definition` resolves a reference, `require_persona_definition` guards write paths, and `diagnose_persona_reference` tells `copotron audit` which Dangling Persona case applies (see ADR 0002 in the control plane).
* **Attachment:** Defined on root nodes or domain hubs.
* **Inheritance:** `indexer.py` traverses the DAG. Child nodes inherit their parent's persona.
* **Nearest Override:** If a child node explicitly declares a persona, it overrides ancestor personas for itself and its subtree.

## 6. Progressive Disclosure Search & Navigation
To protect LLM context windows and prevent lost-in-the-middle degradation:
* **`search.py` (FTS5 & Metadata Search):** Returns matching nodes, BM25 ranking, `inherited_persona` and `inherited_implants` via SQLite FTS5 without surrounding tree bloat.
* **`navigate.py` (Indexed DAG Traversal):** Sub-millisecond indexed edge lookup stepping `up` (to parents) or `down` (to children) on demand when contextual depth is needed. Its results also carry `inherited_persona` and `inherited_implants`.

## 7. Implants (`implants/<name>/`)
An **Implant** couples the brain to an external world: it senses that world, acts on it, or both, and carries its own operating instructions. Implants are maintained alongside the engine, never inside a vault (see ADR 0003 in the control plane).
* **Source:** Each Implant lives in the engine repo under a top-level `implants/<name>/`, outside the `copotron/` package, and is covered by the same `pytest` run. The layout is a convention with no manifest file:
  * `<name>.py` is the entry point, with its dependencies declared inline (PEP 723). It runs as a separate process through `uv run`. Arguments pass straight through and output goes to stdout.
  * `instructions.md` is the template for the Implant Instructions. Its frontmatter supplies `title`, `summary` and `tags`, plus the Implant's permanent `implant_id` (8 lower-case hex characters, generated once and never changed).
* **Insertion:** A vault gets an Implant by Insertion. `instructions.md` is copied into the vault as a new `procedural` memory, the **Implant Instructions**, with a fresh memory id and the `implant_id` in its Open Tail. It is parented under a memory the user chooses, and that memory's `implants` field gains the new memory id. A vault holds one Implant Instructions memory per Implant. Implant code is never copied into a vault.
* **Attachment:** A memory attaches Implants through its `implants` Core Field: a list of Implant Instructions memory ids, never names, so renaming an Implant never breaks a link. The `implant_id` names the Implant itself and never goes in an `implants` field. Attaching the Implant somewhere else later only adds the id to that memory's `implants`. It creates no parent edge and no second copy.
* **Inherited Implants:** `indexer.py` resolves Inherited Implants as the union of every Implant attached to a memory or to any of its ancestors. Unlike persona there is no nearest override and no opt-out. A memory in or below a cycle takes the union over every ancestor it can reach. The index stores `implants` and `inherited_implants` beside `persona` and `inherited_persona`.
* **Dangling implant links:** `copotron.core.implants` decides what counts as Implant Instructions: a `procedural` memory with an `implant_id` in its Open Tail. An `implants` entry that identifies none is a dangling implant link. The indexer leaves it out of Inherited Implants and keeps the field as written. `copotron audit` reports it under `dangling_implant_links` with a problem code (`not_an_id`, `unknown_id` or `not_implant_instructions`). Reads stay lenient, so a dangling link is never fatal.
* **Agent use:** `navigate` and `search` return `inherited_implants` next to `inherited_persona`. For each Implant, its Implant Instructions memory is the only instruction surface an agent gets: there is no SKILL.md and no MCP tool manifest.
* **Lifecycle (`copotron implant` commands):**
  * `insert <name> --attach <memory-id>` performs Insertion (`copotron/system_two/insertion.py`). `<name>` is a folder under `implants/` holding an `instructions.md`. It refuses, leaving the vault untouched, when the name is no Implant, the template lacks a `title` or a well-formed `implant_id`, the `--attach` memory doesn't exist or can't be parsed, or the vault already holds Implant Instructions with that `implant_id`. Re-insertion (refreshing existing Implant Instructions from an updated template while keeping sections the user added) is not built yet.
  * Planned: `run <name> …` starts the entry point. It refuses unless some memory in the vault carries a matching `implant_id`.
  * `detach` performs **Detachment**: it removes the id from one memory. If that memory was the Implant Instructions' parent, they move under the oldest remaining attachment, so they never become an Orphan. Detaching the last attachment is an Implant Removal.
  * `remove` performs **Implant Removal**: it deletes the Implant Instructions and strips their id from every memory.

The skills under `.agents/skills/` (`vault-query`, `vault-editor`, `vault-crystallize`, `vault-admin`, `vault-setup`) are not Implants. They are the engine's own agent guidance for driving `copotron` against the vault, and they couple the brain to no external world.

## 8. Dual-Process Cognitive Architecture (`copotron.system_one` & `copotron.system_two`)
The engine is structured into three cognitive tiers mirroring human dual-process theory:
* **Substrate (`copotron.core`)**: Deterministic Pydantic schemas, atomic disk I/O, and SQLite FTS5 database indexing.
* **System 1 Fast Decision Layer (`copotron.system_one`)**: Fast, machine-native, non-autoregressive decision models (TypeSafe Jev) providing calibrated probabilistic judgments (`Choice`, `Noul`, `Score`) for domain parent routing, search intent extraction, candidate re-ranking, cognitive type classification, and word-boundary slugging, backed by persistent SQLite caching and local offline heuristics.
* **System 2 Deliberative Layer (`copotron.system_two`)**: Procedural memory consolidation, atomic manifest crystallization, surgical markdown section splicing, graph health auditing, and agent archivist orchestration.

