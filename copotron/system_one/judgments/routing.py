from typing import List, Dict, Any, Optional
from copotron.system_one.client import get_system_one_client, SystemOneClient
from copotron.system_one.types import ChoiceQuestion

def resolve_domain_parent(
    title: str,
    summary: str,
    hubs: List[Dict[str, Any]],
    client: Optional[SystemOneClient] = None,
    confidence_threshold: float = 0.65,
) -> List[str]:
    """
    Dynamically determine the most relevant domain hub for a note using System One Choice.
    Confidence-gated: if chosen domain confidence >= confidence_threshold, assigns that hub.
    Falls back to root node '00000000' if ambiguous or none fit.
    """
    if not hubs:
        return ["00000000"]

    criteria = {}
    for h in hubs:
        tags_str = f" [Tags: {', '.join(h.get('tags', []))}]" if h.get("tags") else ""
        criteria[h["id"]] = f"{h['title']}{tags_str}: {h.get('summary', '')}"
    criteria["none"] = "None of these domain hubs fit this topic."

    c = client or get_system_one_client()
    state = {
        "title": title,
        "summary": summary,
    }
    questions = {
        "domain_hub": ChoiceQuestion(
            instructions="Which domain hub is the primary category for this memory note?",
            criteria=criteria,
        )
    }

    resp = c.evaluate(state=state, questions=questions)
    ans = resp.choices.get("domain_hub")

    if ans and ans.choice != "none" and ans.confidence >= confidence_threshold:
        return [ans.choice]

    return ["00000000"]
