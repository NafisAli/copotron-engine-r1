from typing import List, Dict, Any, Optional
from copotron.system_one.client import get_system_one_client, SystemOneClient
from copotron.system_one.types import ScoreQuestion

def rerank_candidates(
    target_title: str,
    target_summary: str,
    candidates: List[Dict[str, Any]],
    purpose: str = "parent",
    client: Optional[SystemOneClient] = None,
    min_score: float = 1.0,
) -> List[Dict[str, Any]]:
    """
    Rerank a shortlist of candidate nodes (e.g. parent candidates or search results)
    in parallel using System One Score evaluation.
    """
    if not candidates:
        return []

    c = client or get_system_one_client()

    levels = [
        "Unrelated or poor match",
        "Tangentially related subject",
        "Good relevant match / container",
        "Ideal direct parent container / exact answer"
    ]

    questions = {}
    for item in candidates:
        item_id = item.get("id", "unknown")
        item_title = item.get("title", "")
        item_summary = item.get("summary", "")[:70]
        q_id = f"score_{item_id}"

        if purpose == "parent":
            inst = f"Rate how well node [{item_id}] '{item_title}' ({item_summary}) serves as a logical parent container for: '{target_title} — {target_summary}'"
        else:
            inst = f"Rate the relevance of note [{item_id}] '{item_title}' ({item_summary}) to query: '{target_title}'"

        questions[q_id] = ScoreQuestion(instructions=inst, criteria=levels)

    state = {
        "target_title": target_title,
        "target_summary": target_summary,
    }

    resp = c.evaluate(state=state, questions=questions)

    scored_candidates = []
    for item in candidates:
        item_id = item.get("id", "unknown")
        q_id = f"score_{item_id}"
        ans = resp.scores.get(q_id)
        score_val = ans.score if ans else 0.0
        confidence = ans.confidence if ans else 0.5
        scored_candidates.append({
            **item,
            "_rerank_score": score_val,
            "_rerank_confidence": confidence,
        })

    # Sort descending by score
    scored_candidates.sort(key=lambda x: x["_rerank_score"], reverse=True)
    return [c for c in scored_candidates if c["_rerank_score"] >= min_score]
