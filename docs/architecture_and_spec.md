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
* **`persona`** (Optional[str]): Behavioral persona identifier attached to roots or branch overrides.

### Open Tail:
Additional arbitrary metadata keys may be included for semantic flexibility and must be preserved during migrations and re-indexing.

## 4. The Memory Tree & Task Hierarchy
Instead of explicit separate "Project" and "Task" schemas, the system uses the `prospective` type combined with the `parents` array:
* A `prospective` memory with a domain hub as parent represents a **Project**.
* A `prospective` memory that points to another prospective memory represents a **Task** / **Subtask**.
* This enables infinitely nestable hierarchy while keeping the schema lean.

## 5. Persona System & Cascading Inheritance
Personas dictate AI tone, domain instructions, and behavior:
* **Storage:** Personas exist natively in the vault as memories (tagged with `persona`).
* **Attachment:** Defined on root nodes or domain hubs.
* **Inheritance:** `indexer.py` traverses the DAG. Child nodes inherit their parent's persona.
* **Nearest Override:** If a child node explicitly declares a persona, it overrides ancestor personas for itself and its subtree.

## 6. Progressive Disclosure Search & Navigation
To protect LLM context windows and prevent lost-in-the-middle degradation:
* **`search.py` (FTS5 & Metadata Search):** Returns matching nodes, BM25 ranking, and `inherited_persona` via SQLite FTS5 without surrounding tree bloat.
* **`navigate.py` (Indexed DAG Traversal):** Sub-millisecond indexed edge lookup stepping `up` (to parents) or `down` (to children) on demand when contextual depth is needed.

## 7. Modular Agent Skills (`.agents/skills/`)
Agent capabilities are organized into focused skills within the engine:
* **`vault-query`**: Governs index searching (`search.py`) and hierarchy traversal (`navigate.py`), with directives to adopt inherited personas.
* **`vault-editor`**: Governs direct markdown authoring and editing in the vault, enforced by validation (`validate.py`).
* **`vault-admin`**: Governs graph re-indexing (`indexer.py`).
* **`vault-setup`**: Handles initialization of new vaults and root node bootstrapping (`setup.py`).

## 8. Dual-Process Cognitive Architecture (`copotron.system_one` & `copotron.system_two`)
The engine is structured into three cognitive tiers mirroring human dual-process theory:
* **Substrate (`copotron.core`)**: Deterministic Pydantic schemas, atomic disk I/O, and SQLite FTS5 database indexing.
* **System 1 Fast Decision Layer (`copotron.system_one`)**: Fast, machine-native, non-autoregressive decision models (TypeSafe Jev) providing calibrated probabilistic judgments (`Choice`, `Noul`, `Score`) for domain parent routing, search intent extraction, candidate re-ranking, cognitive type classification, and word-boundary slugging, backed by persistent SQLite caching and local offline heuristics.
* **System 2 Deliberative Layer (`copotron.system_two`)**: Procedural memory consolidation, atomic manifest crystallization, surgical markdown section splicing, graph health auditing, and agent archivist orchestration.

