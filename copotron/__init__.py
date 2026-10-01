"""
Copotron: Second Brain Cognitive Memory Engine.
Dual-Process Architecture (Core Substrate, System One, System Two).
"""

from copotron.core.schema import (
    MemorySchema,
    parse_frontmatter,
    dump_frontmatter,
    parse_frontmatter_and_body,
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
from copotron.system_two.search import (
    search_graph,
    format_fts_query,
)
from copotron.core.navigate import (
    navigate,
)
from copotron.system_two.domains import (
    get_domain_hubs,
    resolve_auto_parent,
)
from copotron.core.validate import (
    validate_file,
    validate_vault,
)
from copotron.system_two.crystallize import (
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
