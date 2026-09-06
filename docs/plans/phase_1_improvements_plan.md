# Phase 1 Engine Improvements Plan: Scalability & Algorithmic Hardening

## 1. Overview & Objectives

The goal of Phase 1 is to eliminate critical computational, I/O, and data integrity bottlenecks in `copotron-engine` without breaking existing CLI contracts or schema requirements. These improvements transition the engine from a prototype capable of handling ~50 notes to a robust, sub-second engine capable of handling several thousand notes with multi-parent DAG relationships.

### Objectives
1. **Algorithmic Graph Traversal**: Replace recursive backtracking DFS ($\mathcal{O}(2^D)$ path explosion on multi-parent DAGs) with a strictly linear $\mathcal{O}(V + E)$ Topological Sort (Kahn's Algorithm) with cycle detection and deterministic conflict resolution.
2. **Streaming Frontmatter I/O**: Stream markdown files line-by-line during metadata parsing, terminating immediately upon reading the closing `---`, preventing large note bodies from inflating heap allocations.
3. **Set-Based Graph Construction**: Replace $\mathcal{O}(K)$ list membership scans for child deduplication with constant-time set accumulation, serializing deterministically sorted lists.
4. **Atomic File Persistence**: Wrap all file writes (`graph.json`, migrated markdown files) in atomic temporary-write and rename sequences (`os.replace`) to prevent file corruption during concurrent operations or process interruption.
5. **Bounded Query Output (Progressive Disclosure)**: Add pagination (`--limit`, `--offset`) and status filtering to `search.py` and `navigate.py` to protect LLM context windows from high-fanout node dumps.

---

## 2. Detailed Technical Specifications

### Component 1: Linear Topological Persona Inheritance (`scripts/indexer.py`)

#### Problem
In `scripts/indexer.py:dfs_persona`, the function uses a recursive DFS where `visiting.remove(node_id)` is called on backtrack. In a multi-parent DAG (e.g. node $D$ reachable via parents $B$ and $C$), subtrees are re-traversed along every distinct ancestor path, yielding exponential $\mathcal{O}(2^D)$ complexity, non-deterministic persona assignment, and potential `RecursionError` on deep graphs.

#### Solution
Implement topological sorting using Kahn's algorithm:
1. **In-Degree Calculation**: Calculate each node's in-degree based on parent links: $\text{in\_degree}[u] = |\{p \in u.\text{parents} \mid p \in \text{graph}\}|$.
2. **Root Initialization**: Collect all nodes with $\text{in\_degree} == 0$ into a processing queue (sorted by ID for deterministic execution).
3. **Linear Propagation**:
   - For each dequeued node $u$:
     - If $u$ explicitly defines `persona`, set $u[\text{"inherited\_persona"}] = u[\text{"persona"}]$.
     - Else, inspect parents in the declared order of $u[\text{"parents"}]$. Assign $u[\text{"inherited\_persona"}]$ from the first parent that has a non-null `inherited_persona`. If none, set to `None`.
     - For each child $v \in u[\text{"children"}]$:
       - Decrement $\text{in\_degree}[v]$ by 1.
       - If $\text{in\_degree}[v] == 0$, push $v$ to the queue.
4. **Cycle Detection**: If the count of processed nodes is less than the total graph size, identify remaining nodes with $\text{in\_degree} > 0$. Log a clear warning listing cyclic node IDs and assign fallback persona values rather than crashing or looping indefinitely.
5. **Complexity**: $\mathcal{O}(V + E)$ time, $\mathcal{O}(V)$ memory.

---

### Component 2: Streaming Frontmatter Parser (`scripts/schema.py`)

#### Problem
`scripts/schema.py:parse_frontmatter` reads entire files into memory via `f.read().lstrip()` and splits on `---`. For notes containing long transcripts, code dumps, or embedded data (100KB to 5MB), this wastes memory and disk I/O when only the first 10–20 lines of YAML metadata are required.

#### Solution
Implement a streaming parser:
1. Open the file using `utf-8-sig` encoding.
2. Iterate line-by-line using a generator:
   - Discard leading whitespace / empty lines.
   - Assert the first non-empty line is exactly `---`.
   - Accumulate lines until the matching terminating `---` line is reached.
   - Immediately break and close the file handle without reading the remaining body lines.
3. Parse the extracted YAML chunk with `yaml.safe_load`.
4. Retain full compatibility with `parse_frontmatter(file_path)` returning a validated `MemorySchema`.
5. For utilities that require the body (e.g., `migrate.py`), provide a dedicated helper `parse_frontmatter_and_body(file_path)` that splits frontmatter and body cleanly.

---

### Component 3: Set-Based Child Accumulation (`scripts/indexer.py`)

#### Problem
Pass 2 of `indexer.py` uses `node_id not in graph[parent_id]["children"]` on Python lists. For domain hubs (e.g., `00000005-daily-logs.md` or root) accumulating hundreds or thousands of nodes, each insertion incurs an $\mathcal{O}(K)$ linear scan, leading to $\mathcal{O}(K^2)$ cost.

#### Solution
1. In Pass 1, initialize children as empty sets: `children_sets = {node_id: set() for node_id in graph}`.
2. In Pass 2, perform constant-time additions: `children_sets[parent_id].add(node_id)`.
3. Before serialization, assign sorted lists: `graph[node_id]["children"] = sorted(children_sets[node_id])`.
4. Ensures $\mathcal{O}(1)$ child registration and stable, deterministic JSON outputs.

---

### Component 4: Atomic File Persistence (`scripts/vault.py` & callers)

#### Problem
`indexer.py` and `migrate.py` write directly to destination files with `open(path, "w")`. If a process is terminated (e.g. user interrupt, test cancellation, power interruption) or if another process reads concurrently, `graph.json` or markdown notes can be corrupted or read in an incomplete state.

#### Solution
Add reusable atomic write utilities in `scripts/vault.py`:
1. `atomic_write_text(target_path: Path, content: str, encoding: str = "utf-8")`:
   - Write to a unique sibling temporary file: `target_path.with_suffix(f".tmp.{os.getpid()}")`.
   - Flush buffers and execute `os.fsync(f.fileno())`.
   - Use `os.replace(tmp_path, target_path)` for atomic swap.
   - Clean up temporary files on exception.
2. `atomic_write_json(target_path: Path, data: Any, indent: int = 2)`:
   - Serialize JSON to sibling temporary file and atomically replace.
3. Apply `atomic_write_json` in `indexer.py` and `atomic_write_text` in `migrate.py` and `setup.py`.

---

### Component 5: Progressive Disclosure: Bounded Search & Navigation (`scripts/search.py`, `scripts/navigate.py`)

#### Problem
Both scripts output all matching results without pagination. A broad search or navigating `down` on a hub with 500 children dumps all nodes to stdout, exceeding LLM context windows and violating the progressive disclosure design.

#### Solution
1. **`scripts/search.py`**:
   - Add `--limit` / `-l` (default: 20; `0` for unlimited).
   - Add `--offset` (default: 0).
   - Apply slicing after filtering: `results = results[offset : offset + limit if limit > 0 else None]`.
2. **`scripts/navigate.py`**:
   - Add `--limit` / `-l` (default: 20; `0` for unlimited).
   - Add `--offset` (default: 0).
   - Add `--status` / `-s` flag to filter children by status (e.g. `--status active`).
   - Apply filtering and pagination to the returned children or parents.
3. **Skill Updates**:
   - Update `copotron-engine/.agents/skills/vault-query/SKILL.md` to document the new `--limit` and `--status` flags.

---

## 3. Implementation Order & Step-by-Step Execution

| Step | Target Files | Key Actions | Completion Check |
| :--- | :--- | :--- | :--- |
| **1** | [`scripts/vault.py`](file:///c:/Users/digit/Documents/Programming/copotron-r1/copotron-engine/scripts/vault.py) | Add `atomic_write_text` and `atomic_write_json`. | Unit test verifying atomic swap and error cleanup. |
| **2** | [`scripts/schema.py`](file:///c:/Users/digit/Documents/Programming/copotron-r1/copotron-engine/scripts/schema.py) | Implement streaming frontmatter reading in `parse_frontmatter`; add `parse_frontmatter_and_body`. | Existing unit tests pass; test with large 5MB dummy file runs in < 5ms. |
| **3** | [`scripts/indexer.py`](file:///c:/Users/digit/Documents/Programming/copotron-r1/copotron-engine/scripts/indexer.py) | Implement Kahn's algorithm in Pass 3; use `set` in Pass 2; use `atomic_write_json` in Pass 4. | Diamond DAG tests pass; cyclic graph tests warn and exit cleanly; output matches deterministic order. |
| **4** | [`scripts/migrate.py`](file:///c:/Users/digit/Documents/Programming/copotron-r1/copotron-engine/scripts/migrate.py) | Use `parse_frontmatter_and_body` and `atomic_write_text`. Add dirty-check (skip writing if content is unchanged). | Migration runs without touching unchanged files; `mtime` preserved for untouched notes. |
| **5** | [`scripts/search.py`](file:///c:/Users/digit/Documents/Programming/copotron-r1/copotron-engine/scripts/search.py)<br>[`scripts/navigate.py`](file:///c:/Users/digit/Documents/Programming/copotron-r1/copotron-engine/scripts/navigate.py) | Add `--limit`, `--offset`, and `--status` (in navigate) CLI arguments and slicing logic. | CLI tests verifying limit, offset, and status filtering. |
| **6** | [`copotron-engine/.agents/skills/vault-query/SKILL.md`](file:///c:/Users/digit/Documents/Programming/copotron-r1/copotron-engine/.agents/skills/vault-query/SKILL.md) | Update query skill documentation to include `--limit` and `--status` examples. | Skill accurately reflects updated CLI contracts. |
| **7** | [`tests/test_engine.py`](file:///c:/Users/digit/Documents/Programming/copotron-r1/copotron-engine/tests/test_engine.py) | Add comprehensive test cases for all new functionality. | `uv run pytest` passes 100% with all new and existing tests. |

---

## 4. Verification & Testing Plan

### 4.1 Automated Pytest Suite (`tests/test_engine.py`)
1. **Topological Persona Tests**:
   - Create diamond DAG ($A \to B, C \to D$) where $A$ has persona `work`. Verify $D$ inherits `work`.
   - Multi-parent conflict resolution: $A$ (persona `work`), $B$ (persona `gaming`), child $C$ with `parents: [A, B]`. Verify $C$ deterministically inherits `work` based on declared parent order.
   - Cycle detection: $A \to B \to A$. Verify indexer logs cycle warning and completes without infinite recursion.
2. **Streaming Frontmatter Tests**:
   - Generate temporary markdown file with 10 lines of frontmatter and 50,000 lines of body text.
   - Assert `parse_frontmatter` completes in < 10ms and only consumes memory for frontmatter.
   - Edge case: frontmatter with embedded triple hyphens in multiline strings.
3. **Atomic File Write Tests**:
   - Verify `atomic_write_text` and `atomic_write_json` replace destination atomically and leave no orphaned `.tmp` files.
4. **Pagination & Filter Tests**:
   - Search with `--limit 5 --offset 0` vs `--limit 5 --offset 5`. Verify distinct non-overlapping slices.
   - Navigate `down` on a node with mixed active/completed children using `--status active`. Verify completed children are omitted.
5. **Migration Dirty-Check Tests**:
   - Run `migrate_vault()` twice on a test directory. Verify second run reports 0 modified files and preserves file timestamps.

### 4.2 Benchmark Verification
Run execution timing comparison before and after Phase 1 on `copotron-vault`:
- `uv run python scripts/indexer.py` (ensure < 300ms total runtime).
- `uv run python scripts/search.py -q "work" --limit 10`.
- Full test suite: `uv run pytest`.
