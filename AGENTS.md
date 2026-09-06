# Second Brain Engine

The vault data (Memories) is located at the `VAULT_PATH` defined in `.env`.

**Modifying Memories:** Agents should write and modify vault markdown files directly. Scripts in `scripts/` are supportive and should be used to parse, index (`indexer.py`), and validate the YAML frontmatter against the schema after making direct modifications.

**Reading Memories:** Reading vault files should be explicitly gated by graph traversal. Use the knowledge graph (e.g. `graph.json`) to navigate and narrow down the list of relevant files to read. 

**Restrictions:** Strongly avoid grepping or running mass searches across the vault files. Use the graph traversal strategy instead.
