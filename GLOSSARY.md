# Second Brain

A personal cognitive memory system organizing knowledge, logs, workflows, and tasks into an AI-navigable directed acyclic graph.

## Memory & Vault Structure

**Memory**:
The atomic unit of knowledge or intention in the vault, stored as a flat markdown file with YAML frontmatter.
_Avoid_: Node, Note, Entry, Item

**Document**:
A whitelisted non-memory markdown file at the vault root (`README.md`, `LICENSE.md`, `CONTRIBUTING.md`).
_Avoid_: Memory, Note, Text File

**Vault**:
The flat directory of markdown files housing all memories and whitelisted documents without nested subfolders.
_Avoid_: Notebook, Knowledge Base, Workspace, Folder

**Root**:
The mandatory origin memory with fixed identifier `00000000` and no parents from which all memory paths branch.
_Avoid_: Home, Master, Index

**Orphan**:
Any memory other than the Root that has no parent references.
_Avoid_: Dangling Node, Unlinked Note

## Memory Anatomy

**Core Fields**:
The ten strictly validated frontmatter keys (`id`, `title`, `date`, `summary`, `type`, `status`, `parents`, `tags`, `persona`, `implants`) governing engine indexing and graph resolution.
_Avoid_: Base Properties, Fixed Schema

**Open Tail**:
Arbitrary, schema-flexible frontmatter keys preserved by the engine alongside the Core Fields without structural validation.
_Avoid_: Custom Fields, Extra Metadata, Arbitrary Attributes

**Body**:
The freeform markdown content below the YAML frontmatter delimiters, indexed for full-text search.
_Avoid_: Content, Note Text

**Reference**:
An inline citation in the Body pointing to another memory by its identifier in square brackets (e.g. `[00000000]`), carrying no graph edge semantics.
_Avoid_: Link, Markdown Link, Wikilink

## Memory Graph & Organization

**Memory DAG**:
The directed acyclic graph formed by memories as vertices and their frontmatter `parents` declarations as directed edges.
_Avoid_: Tree, Memory Tree, Hierarchy

**Domain Hub**:
A declarative memory directly descending from the Root (`parents: ["00000000"]`) tagged `domain`, anchoring a major knowledge partition.
_Avoid_: Category, Area, Section, Subject, Folder

**Project**:
A prospective memory parented by a Domain Hub, representing an overarching goal or multi-step initiative.
_Avoid_: Epic, Milestone, Objective

**Task**:
A prospective memory parented by another prospective memory, representing an actionable deliverable or work item.
_Avoid_: Subtask, Todo, Action Item, Ticket

## Cognitive Memory Types

**Declarative Memory**:
A memory recording verified facts, architecture specifications, reference materials, or conceptual knowledge.
_Avoid_: Fact, Reference Note, Concept Note, Doc

**Procedural Memory**:
A memory detailing configurations, command cheat sheets, runbooks, or reproducible step-by-step workflows.
_Avoid_: How-To, SOP, Guide, Cheat Sheet, Script

**Prospective Memory**:
A memory capturing a future intention, project goal, deliverable, or actionable task.
_Avoid_: Todo, Action Item, Ticket, Issue

**Episodic Memory**:
A memory capturing a time-bound event, daily log, journal entry, or retrospective.
_Avoid_: Journal, Log, Diary, Meeting Note

## Cognitive Processing & Architecture

**System One**:
The sub-symbolic inference tier providing fast, low-latency heuristic judgments such as classification, intent parsing, and candidate reranking.
_Avoid_: Fast Brain, Heuristics Engine, LLM Layer

**System Two**:
The symbolic and algorithmic cognition tier providing graph indexing, topological traversal, SQLite FTS5 querying, vault health auditing, and multi-step synthesis.
_Avoid_: Slow Brain, Logic Engine, Search Engine

**Judgment**:
A single structured evaluation produced by System One against an explicit question and evaluation criteria.
_Avoid_: Prompt, Inference Call, LLM Response

## Crystallization & Splicing

**Crystallization**:
The process of capturing and consolidating thoughts, working notes, or session state into durable, indexed memories.
_Avoid_: Ingestion, Import, Archiving, Note Creation

**Section Splicer**:
The update mechanism that merges new markdown content into an existing memory's body by matching header sections rather than rewriting the entire file.
_Avoid_: Appender, Merger, Overwriter

**Parent Resolution**:
The algorithmic and heuristic process of discovering and linking logical parent memories for an unattached or newly created memory.
_Avoid_: Categorization, Linking, Filing

## Persona System

**Persona**:
A behavioral and instructional profile defining AI voice, tone, and operational guidelines, which a memory can name to govern itself and its subtree.
_Avoid_: Role, Agent Prompt, Tone, Character

**Persona Definition**:
The declarative memory, tagged `persona`, holding a Persona's profile, which other memories name by its identifier rather than by any label.
_Avoid_: Persona Spec, Persona Note, Persona File

**Inherited Persona**:
The Persona in effect for a memory, resolved at indexing time via top-down topological propagation through the Memory DAG, with nearest ancestor overrides taking precedence.
_Avoid_: Cascaded Persona, Effective Role

**Dangling Persona**:
A memory's persona reference that does not identify an existing Persona Definition.
_Avoid_: Broken Persona, Missing Persona, Unknown Persona

## Retrieval & Auditing

**Progressive Disclosure**:
The retrieval pattern of querying minimal memory metadata and summaries first, expanding context via DAG navigation only when deeper detail is required.
_Avoid_: Truncated Retrieval, Paging

**Completion Drift**:
The divergence where a prospective memory remains marked active despite its body text describing completed or resolved work.
_Avoid_: Stale Task, Desync, Task Lag

## Implants

**Implant**:
An attachable apparatus, maintained alongside the engine rather than inside any vault, that couples the brain to an external world by sensing it, acting on it, or both, and carries its own operating instructions.
_Avoid_: Organ, Plugin, Skill, Tool, MCP Server, Extension

**Insertion**:
The act of giving a vault an Implant by copying the Implant's operating instructions into that vault as a new Procedural Memory attached beneath a memory of the user's choosing.
_Avoid_: Install, Enable, Mount, Register

**Implant Instructions**:
The Procedural Memory created by Insertion, unique per Implant per vault, which other memories attach to by its identifier rather than by any name. It never has children.
_Avoid_: Implant Spec, Implant Definition, Implant Skill, Runbook

**Inherited Implants**:
The set of Implants in effect for a memory, resolved at indexing time as the union of every Implant attached to it or to any of its ancestors.
_Avoid_: Cascaded Implants, Active Implants, Effective Implants

**Detachment**:
Ending one memory's attachment to an Implant, leaving the Implant Instructions in the vault as long as any attachment remains.
_Avoid_: Unlink, Unmount, Disable

**Implant Removal**:
Taking an Implant out of a vault by deleting its Implant Instructions and every attachment to it.
_Avoid_: Uninstall, Ejection, Explant
