import json
import re
from pathlib import Path
from typing import List, Dict, Any, Optional

from copotron.vault import get_vault_path
from copotron.db import get_db_path, get_readonly_db


def get_domain_hubs(vault_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """
    Retrieve all domain hubs dynamically from the vault index.
    A domain hub is any direct child of root '00000000' tagged with 'domain'.
    """
    if vault_dir is None:
        vault_dir = get_vault_path(require_root=True)

    db_path = get_db_path(vault_dir)
    if not db_path.exists():
        return []

    conn = get_readonly_db(db_path)
    sql = """
    SELECT m.id, m.file_path, m.title, m.summary, m.type, m.status, m.tags_json, m.inherited_persona
    FROM memories m
    JOIN memory_edges e ON m.id = e.child_id
    WHERE e.parent_id = '00000000'
      AND EXISTS (SELECT 1 FROM json_each(m.tags_json) WHERE lower(value) = 'domain')
    ORDER BY m.id;
    """
    cur = conn.execute(sql)
    rows = cur.fetchall()

    hubs = []
    for r in rows:
        try:
            tags = json.loads(r["tags_json"])
        except Exception:
            tags = []
        hubs.append({
            "id": r["id"],
            "file_path": r["file_path"],
            "title": r["title"],
            "summary": r["summary"],
            "type": r["type"],
            "status": r["status"],
            "tags": tags,
            "inherited_persona": r["inherited_persona"],
        })

    conn.close()
    return hubs


def resolve_auto_parent(title: str, summary: str, vault_dir: Optional[Path] = None) -> List[str]:
    """
    Dynamically determine the most relevant domain hub for a note based on keyword overlap.
    Falls back to root node '00000000' if no specific domain hub matches.
    """
    if vault_dir is None:
        vault_dir = get_vault_path(require_root=True)

    hubs = get_domain_hubs(vault_dir)
    if not hubs:
        root_file = vault_dir / "00000000-root.md"
        return ["00000000"] if root_file.is_file() else []

    text_to_match = f"{title} {summary}".lower()
    tokens = set(re.findall(r"\w+", text_to_match))
    significant_tokens = {t for t in tokens if len(t) > 2}

    best_hub = None
    best_score = 0

    for hub in hubs:
        hub_text = f"{hub['title']} {hub['summary']} {' '.join(hub['tags'])}".lower()
        hub_tokens = set(re.findall(r"\w+", hub_text))

        # Score by token intersection weighted by tag matches
        score = len(significant_tokens.intersection(hub_tokens))
        for tag in hub["tags"]:
            if tag.lower() in significant_tokens:
                score += 3

        if score > best_score:
            best_score = score
            best_hub = hub["id"]

    if best_hub and best_score > 0:
        return [best_hub]

    # Fallback to root
    root_file = vault_dir / "00000000-root.md"
    return ["00000000"] if root_file.is_file() else []
