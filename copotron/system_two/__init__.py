"""
copotron.system_two: Deliberative procedural workflows, memory crystallization,
surgical markdown splicing, and vault health auditing.
"""

from copotron.system_two.crystallize import (
    clean_slug,
    generate_unique_id,
    suggest_parents,
    resolve_auto_parent,
    create_memory_node,
    update_memory_node,
    create_or_update_memory_node,
    crystallize_manifest,
)
from copotron.system_two.splicer import splice_markdown_sections
from copotron.system_two.audit import audit_vault_health

__all__ = [
    "clean_slug",
    "generate_unique_id",
    "suggest_parents",
    "resolve_auto_parent",
    "create_memory_node",
    "update_memory_node",
    "create_or_update_memory_node",
    "crystallize_manifest",
    "splice_markdown_sections",
    "audit_vault_health",
]
