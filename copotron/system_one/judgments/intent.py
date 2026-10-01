import re
from typing import Optional, Dict, Any
from copotron.system_one.client import get_system_one_client, SystemOneClient
from copotron.system_one.types import ChoiceQuestion, NoulQuestion

def parse_search_intent(
    query_str: str,
    client: Optional[SystemOneClient] = None
) -> Dict[str, Any]:
    """
    Parse a natural language search query using System One judgments:
    1. Distinguishes direct 8-hex ID lookups from general search tokens.
    2. Extracts implied biological type filters.
    3. Extracts implied lifecycle status filters.
    4. Cleans the search keywords.
    """
    if not query_str or not query_str.strip():
        return {
            "clean_query": "",
            "direct_id": None,
            "type_filter": None,
            "status_filter": None,
        }

    raw = query_str.strip()
    candidate_hex_ids = re.findall(r"\b[0-9a-fA-F]{8}\b", raw)

    c = client or get_system_one_client()

    questions = {
        "implied_type": ChoiceQuestion(
            instructions="Does the query imply a specific cognitive memory type filter?",
            criteria={
                "declarative": "Looking for specs, architecture, verified facts, references",
                "procedural": "Looking for how-to, commands, scripts, SOPs, workflows",
                "prospective": "Looking for tasks, todos, upcoming action items, projects",
                "episodic": "Looking for daily logs, retrospectives, journal entries",
                "none": "No specific type filter intended"
            }
        ),
        "implied_status": ChoiceQuestion(
            instructions="Does the query imply a lifecycle status filter?",
            criteria={
                "active": "Active, ongoing, in-progress items",
                "completed": "Completed, done, resolved items",
                "archived": "Archived, legacy items",
                "none": "No specific status filter intended"
            }
        ),
    }

    if candidate_hex_ids:
        questions["is_id_lookup"] = NoulQuestion(
            instructions="Is the user explicitly searching for a specific memory by its 8-character ID code?"
        )

    resp = c.evaluate(state={"query": raw, "candidate_ids": candidate_hex_ids}, questions=questions)

    direct_id = None
    if candidate_hex_ids:
        noul_ans = resp.nouls.get("is_id_lookup")
        if noul_ans and noul_ans.noul >= 0.70:
            direct_id = candidate_hex_ids[0].lower()

    type_ans = resp.choices.get("implied_type")
    type_filter = type_ans.choice if (type_ans and type_ans.choice != "none" and type_ans.confidence >= 0.60) else None

    status_ans = resp.choices.get("implied_status")
    status_filter = status_ans.choice if (status_ans and status_ans.choice != "none" and status_ans.confidence >= 0.60) else None

    # Strip conversational noise words for clean FTS5 matching
    clean = re.sub(r"\b(find|search|show|get|list|all|me|notes?|memories|tasks?)\b", "", raw, flags=re.IGNORECASE)
    clean = " ".join(clean.split()).strip()

    return {
        "clean_query": clean or raw,
        "direct_id": direct_id,
        "type_filter": type_filter,
        "status_filter": status_filter,
    }
