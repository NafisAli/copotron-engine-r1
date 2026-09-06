import os
import re
import yaml
import hashlib
from pathlib import Path
from typing import Dict, List, Any
from schema import MemorySchema, dump_frontmatter

def compute_id(source_key: str) -> str:
    """Generate a deterministic 8-character hex ID."""
    return hashlib.sha256(source_key.encode("utf-8")).hexdigest()[:8]

def clean_slug(title: str) -> str:
    """Generate a clean slug for filenames."""
    s = title.lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s).strip("-")
    return s[:50]

def main():
    source_vault = Path(r"c:\Users\digit\Documents\Obsidian\copotron")
    target_vault = Path(os.getenv("VAULT_PATH", r"c:\Users\digit\Documents\Programming\copotron-r1\copotron-vault"))
    
    if not source_vault.exists():
        print(f"Error: Source vault {source_vault} does not exist.")
        return
    if not target_vault.exists():
        target_vault.mkdir(parents=True, exist_ok=True)

    print(f"Migrating from {source_vault} -> {target_vault}")

    # 1. Parse connectome.md for pre-authored summaries
    connectome_path = source_vault / "connectome.md"
    connectome_entries: Dict[str, str] = {}
    if connectome_path.exists():
        with open(connectome_path, "r", encoding="utf-8") as f:
            for line in f:
                m = re.match(r"- \[\[([^\|]+)\|([^\]]+)\]\]\s*—\s*_(.*)_\s*\(`([^`]+)`\)", line.strip())
                if m:
                    uid, _, desc, _ = m.groups()
                    connectome_entries[uid] = desc.strip()

    # 2. Build ID Mapping
    domain_ids = {
        "work": "00000001",
        "psychology": "00000002",
        "gaming": "00000003",
        "learning": "00000004",
        "daily-logs": "00000005"
    }

    cortex_files = sorted((source_vault / "cortex").glob("*.md"))
    id_map: Dict[str, str] = {}
    for f in cortex_files:
        uid = f.stem.split("-")[0]
        id_map[uid] = compute_id(uid)

    episodic_files = sorted((source_vault / "episodic").glob("*.md"))
    for f in episodic_files:
        date_str = f.stem
        id_map[date_str] = compute_id(date_str)

    print(f"Mapped {len(id_map)} legacy IDs to new 8-character IDs.")

    def rewrite_wikilinks(text: str) -> str:
        def repl(match):
            target = match.group(1)
            alias = match.group(2) or ""
            new_target = id_map.get(target, target)
            return f"[[{new_target}{alias}]]"
        return re.sub(r"\[\[([^\|\]]+)(\|[^\]]+)?\]\]", repl, text)

    def clean_summary_text(text: str) -> str:
        # Strip wikilinks to label or target for clean summary prose
        def repl(match):
            target = match.group(1)
            alias = match.group(2)
            if alias:
                return alias.lstrip("|")
            return target
        cleaned = re.sub(r"\[\[([^\|\]]+)(\|[^\]]+)?\]\]", repl, text)
        return cleaned.strip()

    # 3. Create Domain Hub Memories
    domain_nodes = [
        {
            "id": domain_ids["work"],
            "filename": f"{domain_ids['work']}-work.md",
            "title": "Work",
            "date": "2026-06-25",
            "summary": "Domain hub for work-related projects, systems architecture, and engineering practices.",
            "type": "declarative",
            "status": "active",
            "parents": ["00000000"],
            "tags": ["domain", "work"],
            "body": "# Work\n\nCentral hub for work context, systems architecture, and engineering projects."
        },
        {
            "id": domain_ids["psychology"],
            "filename": f"{domain_ids['psychology']}-psychology.md",
            "title": "Psychology",
            "date": "2026-06-25",
            "summary": "Domain hub for psychology academic pathways, honors research, and admissions tracking.",
            "type": "declarative",
            "status": "active",
            "parents": ["00000000"],
            "tags": ["domain", "psychology"],
            "body": "# Psychology\n\nCentral hub for academic pathways, admissions research, and course evaluations."
        },
        {
            "id": domain_ids["gaming"],
            "filename": f"{domain_ids['gaming']}-gaming.md",
            "title": "Gaming",
            "date": "2026-06-25",
            "summary": "Domain hub for gaming projects, ship builds, material harvesting, and engineering unlocks.",
            "type": "declarative",
            "status": "active",
            "parents": ["00000000"],
            "tags": ["domain", "gaming"],
            "body": "# Gaming\n\nCentral hub for games, ship configurations, engineering roadmaps, and guides."
        },
        {
            "id": domain_ids["learning"],
            "filename": f"{domain_ids['learning']}-learning.md",
            "title": "Learning",
            "date": "2026-06-25",
            "summary": "Domain hub for technical learning, cheat sheets, and Linux/systems administration guides.",
            "type": "declarative",
            "status": "active",
            "parents": ["00000000"],
            "tags": ["domain", "learning"],
            "body": "# Learning\n\nCentral hub for technical documentation, reference material, and system administration."
        },
        {
            "id": domain_ids["daily-logs"],
            "filename": f"{domain_ids['daily-logs']}-daily-logs.md",
            "title": "Daily Logs",
            "date": "2026-06-25",
            "summary": "Domain hub for temporal episodic logs and daily journal entries.",
            "type": "declarative",
            "status": "active",
            "parents": ["00000000"],
            "tags": ["domain", "episodic"],
            "body": "# Daily Logs\n\nCentral hub for daily activity logs, stardates, and task snapshots."
        }
    ]

    for d in domain_nodes:
        schema_obj = MemorySchema(
            id=d["id"],
            title=d["title"],
            date=d["date"],
            summary=d["summary"],
            type=d["type"],
            status=d["status"],
            parents=d["parents"],
            tags=d["tags"],
            persona=None
        )
        content = dump_frontmatter(schema_obj, d["body"])
        out_file = target_vault / d["filename"]
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Created Domain Hub: {out_file.name}")

    # 4. Classifications
    procedural_uids = {"gmybf2", "rk7r8n", "36grzw", "5ywm7k"}
    build_spec_uids = {"zp9v2c"}

    # 5. Process Cortex Notes
    migrated_cortex = 0
    for f in cortex_files:
        raw = f.read_text(encoding="utf-8")
        parts = raw.split("---", 2)
        if len(parts) < 3:
            print(f"Skipping malformed file: {f}")
            continue

        meta = yaml.safe_load(parts[1]) or {}
        body = parts[2].lstrip()

        old_uid = meta.get("uid", f.stem.split("-")[0])
        new_id = id_map[old_uid]
        title = meta.get("title", f.stem)
        domain = meta.get("domain", "general")
        old_type = meta.get("type", "engram")

        created_str = str(meta.get("created", ""))
        m_date = re.search(r"\d{4}-\d{2}-\d{2}", created_str)
        date_val = m_date.group(0) if m_date else "2026-06-25"

        if old_uid in build_spec_uids:
            new_type = "prospective"
        elif old_type == "circuit":
            new_type = "prospective"
        elif old_uid in procedural_uids:
            new_type = "procedural"
        else:
            new_type = "declarative"

        old_status = meta.get("status") or meta.get("lifecycle")
        if old_status == "done":
            new_status = "completed"
        elif old_status == "active":
            new_status = "active"
        else:
            new_status = "active"

        # Summary resolution
        if old_uid in connectome_entries:
            summary = clean_summary_text(connectome_entries[old_uid])
        else:
            summary = ""
            obj_m = re.search(r"##\s+(?:Objective|Core Concept|Quick Read)\s*\n+(.*?)(?=\n##|\Z)", body, re.DOTALL)
            if obj_m:
                lines = [line.strip().lstrip("-* ").strip() for line in obj_m.group(1).splitlines() if line.strip()]
                for line in lines:
                    if line.lower().startswith("parent protocol"):
                        continue
                    if len(line) > 15:
                        summary = clean_summary_text(line)
                        break
            if not summary:
                for line in body.splitlines():
                    ls = line.strip().lstrip("-*# ").strip()
                    if ls.lower().startswith("parent protocol"):
                        continue
                    if ls and not ls.startswith("[") and len(ls) > 15:
                        summary = clean_summary_text(ls)
                        break
            if not summary:
                summary = f"{title} in domain {domain}."

        if not summary.endswith("."):
            summary += "."

        # Parents DAG resolution
        parents: List[str] = []
        if domain == "work":
            if old_uid in ("vbqyxq", "wkm84r"):
                parents = [domain_ids["work"]]
            elif old_uid in ("gmybf2", "492waj"):
                parents = [id_map["vbqyxq"]]
            elif old_uid in ("rkm72w", "46p4am"):
                parents = [id_map["wkm84r"]]
            else:
                parents = [domain_ids["work"]]
        elif domain == "psychology":
            if old_uid == "f8gv8w":
                parents = [domain_ids["psychology"]]
            else:
                parents = [id_map["f8gv8w"]]
        elif domain == "gaming":
            if old_uid == "jyd2r3":
                parents = [domain_ids["gaming"]]
            elif old_uid in ("m9v6av", "zp9v2c"):
                parents = [id_map["jyd2r3"]]
            elif old_uid == "aqaq5t":
                parents = [id_map["m9v6av"], id_map["jyd2r3"]]
            elif old_uid == "gzexjk":
                parents = [id_map["m9v6av"]]
            elif old_uid in ("36grzw", "5ywm7k"):
                parents = [id_map["aqaq5t"]]
            else:
                parents = [domain_ids["gaming"]]
        elif domain == "learning":
            parents = [domain_ids["learning"]]
        else:
            parents = ["00000000"]

        tags = meta.get("tags", [])
        if not isinstance(tags, list):
            tags = [tags] if tags else []
        if domain not in tags:
            tags.append(domain)

        updated_body = rewrite_wikilinks(body)
        slug = clean_slug(title)
        out_filename = f"{new_id}-{slug}.md"
        out_path = target_vault / out_filename

        schema_obj = MemorySchema(
            id=new_id,
            title=title,
            date=date_val,
            summary=summary,
            type=new_type,
            status=new_status,
            parents=parents,
            tags=tags,
            persona=None
        )

        content = dump_frontmatter(schema_obj, updated_body)
        with open(out_path, "w", encoding="utf-8") as out_f:
            out_f.write(content)

        migrated_cortex += 1

    print(f"Migrated {migrated_cortex} cortex notes.")

    # 6. Process Episodic Notes
    migrated_episodic = 0
    for f in episodic_files:
        raw = f.read_text(encoding="utf-8")
        parts = raw.split("---", 2)
        if len(parts) < 3:
            continue

        meta = yaml.safe_load(parts[1]) or {}
        body = parts[2].lstrip()

        date_str = f.stem
        new_id = id_map[date_str]
        title = f"Daily Log: {date_str}"
        summary = f"Stardate daily log for {date_str} tracking active and touched tasks."
        parents = [domain_ids["daily-logs"]]
        tags = ["daily", "episodic"]

        updated_body = rewrite_wikilinks(body)
        out_filename = f"{new_id}-daily-log-{date_str}.md"
        out_path = target_vault / out_filename

        schema_obj = MemorySchema(
            id=new_id,
            title=title,
            date=date_str,
            summary=summary,
            type="episodic",
            status="active",
            parents=parents,
            tags=tags,
            persona=None
        )

        content = dump_frontmatter(schema_obj, updated_body)
        with open(out_path, "w", encoding="utf-8") as out_f:
            out_f.write(content)

        migrated_episodic += 1

    print(f"Migrated {migrated_episodic} episodic notes.")
    total = len(domain_nodes) + migrated_cortex + migrated_episodic
    print(f"Migration finished. Successfully wrote {total} memories.")

if __name__ == "__main__":
    main()
