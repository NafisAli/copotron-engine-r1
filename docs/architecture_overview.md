# Copotron R1: Second Brain Architecture Overview

This document captures the architectural blueprint and operational model for the AI-driven Second Brain, aligned with the implementation in `copotron-engine`.

## 1. High-Level Architecture

The system separates logic from data:

* **The Vault (Data):** A completely flat directory of Markdown files (`copotron-vault`). No nested subfolders are permitted. Non-memory documents are restricted to a root whitelist (`README.md`, `LICENSE.md`, `CONTRIBUTING.md`).
* **The Engine (Logic & Agent Hub):** A Python-based repository (`copotron-engine`, managed via `uv`) containing deterministic modules (`copotron/core/`) and AI-augmented capabilities (`copotron/system_one/`, `copotron/system_two/`) that index, parse, search, and validate the Vault. The agent executes directly inside the engine directory.

## 2. The AI-First Flat Vault

The system abandons traditional folder hierarchies (like strict PARA). Relationships are formed entirely via **YAML Frontmatter** validated through Pydantic:

* Files remain strictly flat at the vault root.
* Identity is bound to the 8-character lowercase hexadecimal identifier (`id`), not the filename.
* Files follow the naming convention `{id}-{slug}.md`. Updating a memory's title updates its slug (`{id}-{new-slug}.md`) without breaking graph integrity.
* Within the markdown body, cross-references to other memories are written as bracketed IDs (e.g. `[00000000]` or `[a1b2c3d4]`) rather than filepath links, ensuring references never break across renames and keeping graph topology strictly in frontmatter `parents`.
* Retrieval relies on indexed graph traversal and metadata rather than directory browsing.

## 3. Cognitive Memory Schema (`copotron/core/schema.py`)

The brain is modeled as a Directed Acyclic Graph (DAG) of **Memories**. The schema enforces a **Strict Core, Open Tail** model:

### Core Fields

* **`id`** (str): 8-character unique lowercase hexadecimal string (e.g. `00000000` for Root, or SHA-256 hash prefix).
* **`title`** (str): Concise title of the memory.
* **`date`** (str): Event or creation date in `YYYY-MM-DD` format (immutable across updates).
* **`summary`** (str): Concise 1-2 sentence summary for AI context scanning.
* **`type`** (enum): Biological memory type:
  * `episodic`: Time-bound logs, daily journals, events.
  * `declarative`: Factual knowledge, reference, architecture docs.
  * `procedural`: How-tos, SOPs, workflows, cheat sheets.
  * `prospective`: Future intentions, projects, tasks, and action items.
* **`status`** (enum): Lifecycle status: `active`, `completed`, `archived`, `none`.
* **`parents`** (List[str]): List of parent 8-character hex IDs forming directed edges.
* **`tags`** (List[str]): Semantic tags for taxonomy and filtering.
* **`persona`** (Optional[str]): Behavioral persona identifier attached to roots or branch overrides.
* **`implants`** (List[str]): Implant Instructions memory IDs, attaching those Implants to this memory and its subtree (see §8).

### Open Tail

Additional arbitrary metadata keys may be included for semantic flexibility and are preserved during migrations and re-indexing (stored in SQLite as JSON).

### Body & Inline References

The freeform markdown content below the YAML frontmatter delimiters is indexed into SQLite FTS5 for full-text search. Memories cite other memories inline using bracketed identifiers (`[<id>]`), which serve as reader citations without declaring graph topology.

## 4. The Memory DAG & Prospective Work

The system models organizational structure and initiatives dynamically through the Memory DAG rather than rigid issue-tracking schemas:

* **Domain Hubs:** Top-level declarative memories directly parented by Root (`00000000`) and carrying the `domain` tag. They define major organizational partitions (e.g. Work, Psychology, Gaming, Learning) and anchor behavioral personas.
* **Projects:** Prospective memories directly parented by a Domain Hub, representing overarching initiatives or multi-step goals.
* **Tasks:** Prospective memories parented by another prospective memory, representing actionable deliverables or sub-steps. This allows arbitrary nesting without dedicated database tables.
* **Completion Drift:** Monitored via `copotron audit`, identifying active prospective memories whose body content indicates that the work has already finished.

## 5. Persona System & Cascading Inheritance

Personas dictate AI tone, domain instructions, and behavior:

* **Storage:** Personas exist natively in the vault as memories (carrying the `persona` frontmatter field).
* **Attachment:** Defined on root nodes, domain hubs, or individual branch memories.
* **Inheritance:** `copotron/core/indexer.py` performs a topological sort over the Memory DAG during indexing. Child memories inherit their parent's persona.
* **Nearest Override:** If a child memory explicitly declares a `persona`, it overrides ancestor personas for itself and its downstream subtree.

## 6. Progressive Disclosure Search & Navigation

To protect LLM context windows and prevent lost-in-the-middle degradation:

* **`copotron/system_two/search.py` (FTS5 & Metadata Search):** Returns matching memories, BM25 ranking, `inherited_persona` and `inherited_implants` via SQLite FTS5 without surrounding graph bloat. Supports System One intent parsing and candidate reranking.
* **`copotron/core/navigate.py` (Indexed DAG Traversal):** Sub-millisecond indexed edge lookup stepping `up` (to parents) or `down` (to children) on demand when contextual depth is needed.

## 7. Crystallization & Cognitive Tiers

* **System One (`copotron/system_one/`):** Lightweight, parallel heuristic evaluation tier using provider adapters (e.g. TypeSafe, Mock, Fallback) for classification (biological memory type), intent extraction, candidate reranking, and domain routing.
* **System Two (`copotron/system_two/`):** Symbolic and algorithmic synthesis tier handling full vault audits (`audit.py`), semantic parent resolution, and memory crystallization (`crystallize.py`).
* **Section Splicer (`copotron/system_two/splicer.py`):** Surgically merges incoming markdown sections into existing memories by matching header titles and using model alignment to replace or append, preserving unrelated sections.

## 8. Implants (`implants/<name>/`)

An **Implant** couples the brain to an external world by sensing it, acting on it, or both, and carries its own operating instructions ([ADR 0003](adr/0003-implants-core-field.md)). This section is the overview. §7 of the [engine spec](architecture_and_spec.md) holds every lifecycle rule and refusal.

* **Source:** Each Implant lives in the engine repo under `implants/<name>/`, never inside a vault. `<name>.py` is the entry point, with its dependencies declared inline and run through `uv run`. `instructions.md` is the template for the Implant Instructions, and its frontmatter carries the Implant's permanent 8-character hex `implant_id`.
* **Insertion:** `copotron implant insert <name> --attach <memory-id>` copies the template into the vault as the **Implant Instructions**: a `procedural` memory with `implant_id` in its Open Tail, parented under the chosen memory, whose `implants` field gains the new memory ID. A vault holds one Implant Instructions per Implant, and it never has children.
* **Re-insertion:** Running `insert` again refreshes the Implant Instructions from the template deterministically. Template sections take the template's text, so a hand edit inside one is lost. Sections and tags added by hand are kept.
* **Attachment & Inheritance:** The `implants` Core Field lists Implant Instructions memory IDs, never names, so renaming an Implant breaks no link. The indexer resolves **Inherited Implants** as the union over a memory and all its ancestors, with no nearest override. `navigate` and `search` return them as `inherited_implants`, and an agent learns to use each Implant by reading its Implant Instructions. An entry that identifies no Implant Instructions is a dangling implant link: it is left out of inheritance and reported by `copotron audit`.
* **Run Guard:** `copotron implant run <name> …` starts the entry point with every argument passed through. It runs only when the vault holds that Implant's Instructions, and otherwise refuses with exit code 2.
* **Detachment & Implant Removal:** `copotron implant detach <name> --from <memory-id>` ends one memory's attachment. If that leaves the Implant Instructions with no parent, they move under the oldest remaining attachment, and detaching the last attachment is an Implant Removal. `copotron implant remove <name>` deletes the Implant Instructions and strips their ID from every memory.

The engine's agent skills under `.agents/skills/` (`vault-query`, `vault-editor`, `vault-crystallize`, `vault-admin`, `vault-setup`) are not Implants. They guide driving `copotron` against the vault and couple the brain to no external world.
