"""
copotron.core: Deterministic substrate for the Second Brain engine.
Provides Pydantic frontmatter schemas, atomic file I/O, SQLite FTS5 database management,
and DAG topological graph indexing.
"""

from copotron.core.schema import (
    MemorySchema,
    parse_frontmatter,
    parse_frontmatter_and_body,
    dump_frontmatter,
)
from copotron.core.vault import (
    get_vault_path,
    load_env,
    atomic_write_text,
    atomic_write_json,
)
from copotron.core.db import (
    get_db_path,
    init_db,
    get_readonly_db,
    INDEX_SCHEMA_VERSION,
)
from copotron.core.indexer import (
    load_vault,
    compute_frontmatter_hash,
)

__all__ = [
    "MemorySchema",
    "parse_frontmatter",
    "parse_frontmatter_and_body",
    "dump_frontmatter",
    "get_vault_path",
    "load_env",
    "atomic_write_text",
    "atomic_write_json",
    "get_db_path",
    "init_db",
    "get_readonly_db",
    "INDEX_SCHEMA_VERSION",
    "load_vault",
    "compute_frontmatter_hash",
]
