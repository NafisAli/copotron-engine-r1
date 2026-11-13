from typing import Dict, Any, List, Optional
from pathlib import Path

from copotron.core.vault import get_vault_path
from copotron.core.schema import parse_frontmatter_and_body
from copotron.core.indexer import scan_vault_files
from copotron.core.personas import diagnose_persona_reference
from copotron.core.implants import diagnose_implant_reference, is_implant_instructions
from copotron.system_one.judgments.classification import infer_task_completed

def audit_vault_health(vault_dir: Optional[Path] = None, check_semantic: bool = True) -> Dict[str, Any]:
    """
    Run comprehensive health and consistency checks across the vault:
    1. Broken parent references
    2. Orphan nodes (isolated from domain hubs)
    3. Prospective completion drift (tasks marked active that appear done)
    4. Truncated slugs
    5. Dangling Personas (persona does not identify a Persona Definition)
    6. Dangling implant links (an implants entry does not identify Implant Instructions)
    """
    if vault_dir is None:
        vault_dir = get_vault_path(require_root=True)

    disk_files = scan_vault_files(vault_dir)

    all_ids = set()
    instructions_ids = set()
    node_records = []

    for rel_path, (abs_path, _) in disk_files.items():
        try:
            mem, body = parse_frontmatter_and_body(abs_path)
            all_ids.add(mem.id)
            if is_implant_instructions(mem.type, mem.model_extra or {}):
                instructions_ids.add(mem.id)
            node_records.append({
                "id": mem.id,
                "file_path": rel_path,
                "title": mem.title,
                "type": mem.type,
                "status": mem.status,
                "parents": mem.parents,
                "persona": mem.persona,
                "implants": mem.implants,
                "body": body,
            })
        except Exception:
            continue

    broken_parents = []
    orphan_nodes = []
    completion_drift = []
    truncated_slugs = []
    dangling_personas = []
    dangling_implant_links = []

    for rec in node_records:
        n_id = rec["id"]
        # 1. Broken parent check
        for p in rec["parents"]:
            if p not in all_ids:
                broken_parents.append({
                    "id": n_id,
                    "title": rec["title"],
                    "missing_parent": p
                })

        # 2. Orphan check (no parents and not root)
        if not rec["parents"] and n_id != "00000000":
            orphan_nodes.append({
                "id": n_id,
                "title": rec["title"]
            })

        # 5. Dangling Persona check (persona does not identify a Persona Definition)
        if rec["persona"] is not None:
            problem = diagnose_persona_reference(vault_dir, rec["persona"])
            if problem is not None:
                dangling_personas.append({
                    "id": n_id,
                    "title": rec["title"],
                    "persona": rec["persona"],
                    "problem": problem,
                })

        # 6. Dangling implant link check (an implants entry does not identify Implant Instructions)
        for reference in rec["implants"]:
            problem = diagnose_implant_reference(reference, all_ids, instructions_ids)
            if problem is not None:
                dangling_implant_links.append({
                    "id": n_id,
                    "title": rec["title"],
                    "implant": reference,
                    "problem": problem,
                })

        # 3. Truncated slug check (trailing hyphen or short chop)
        fname = Path(rec["file_path"]).stem
        slug_part = fname[9:] if len(fname) > 9 else ""
        if slug_part.endswith("-") or len(slug_part) == 50:
            truncated_slugs.append({
                "id": n_id,
                "slug": slug_part,
                "title": rec["title"]
            })

        # 4. Completion drift (only for prospective active tasks)
        if check_semantic and rec["type"] == "prospective" and rec["status"] == "active":
            if rec["body"] and infer_task_completed(rec["title"], rec["body"]):
                completion_drift.append({
                    "id": n_id,
                    "title": rec["title"],
                    "suggested_status": "completed"
                })

    return {
        "total_nodes": len(node_records),
        "broken_parent_references": broken_parents,
        "orphan_nodes": orphan_nodes,
        "truncated_slugs": truncated_slugs,
        "completion_drift": completion_drift,
        "dangling_personas": dangling_personas,
        "dangling_implant_links": dangling_implant_links,
        "healthy": not (
            broken_parents or orphan_nodes or completion_drift or dangling_personas or dangling_implant_links
        )
    }
