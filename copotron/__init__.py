"""
Copotron: Second Brain Cognitive Memory Engine.
"""

from copotron.schema import (
    MemorySchema,
    parse_frontmatter,
    dump_frontmatter,
    parse_frontmatter_and_body,
)
from copotron.vault import (
    get_vault_path,
    load_env,
    atomic_write_text,
    atomic_write_json,
)
from copotron.db import (
    get_db_path,
    init_db,
    get_readonly_db,
    INDEX_SCHEMA_VERSION,
)
from copotron.indexer import (
    load_vault,
    compute_frontmatter_hash,
)
from copotron.search import (
    search_graph,
    format_fts_query,
)
from copotron.navigate import (
    navigate,
)
from copotron.domains import (
    get_domain_hubs,
    resolve_auto_parent,
)
from copotron.validate import (
    validate_file,
    validate_vault,
)
from copotron.crystallize import (
    create_memory_node,
    update_memory_node,
    create_or_update_memory_node,
    crystallize_manifest,
)

__version__ = "0.1.0"

__all__ = [
    "MemorySchema",
    "parse_frontmatter",
    "dump_frontmatter",
    "parse_frontmatter_and_body",
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
    "search_graph",
    "format_fts_query",
    "navigate",
    "get_domain_hubs",
    "resolve_auto_parent",
    "validate_file",
    "validate_vault",
    "create_memory_node",
    "update_memory_node",
    "create_or_update_memory_node",
    "crystallize_manifest",
]
