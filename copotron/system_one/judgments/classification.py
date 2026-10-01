from typing import Optional, Literal
from copotron.system_one.client import get_system_one_client, SystemOneClient
from copotron.system_one.types import ChoiceQuestion, NoulQuestion

def infer_memory_type(
    title: str,
    summary: str = "",
    body: str = "",
    client: Optional[SystemOneClient] = None,
) -> Literal["declarative", "procedural", "prospective", "episodic"]:
    """
    Infer the biological memory type using System One Choice:
    - declarative: architecture, specs, verified facts, references
    - procedural: how-tos, commands, reproducible scripts, SOPs
    - prospective: future tasks, upcoming projects, action items
    - episodic: dated journals, daily logs, session retrospectives
    """
    c = client or get_system_one_client()

    criteria = {
        "declarative": "Verified facts, pinouts, component specs, architectural decisions, and rejected trade-offs",
        "procedural": "Tested commands, configuration steps, cheat sheets, and reproducible scripts",
        "prospective": "Overarching project goals, future intentions, tasks, or concrete next-step action items",
        "episodic": "Time-bound event logs, dated journals, meeting notes, or session retrospectives",
    }

    sample_text = f"{title}\n{summary}\n{body[:300]}".strip()
    questions = {
        "mem_type": ChoiceQuestion(
            instructions="Classify this cognitive memory note into its primary biological memory type:",
            criteria=criteria,
        )
    }

    resp = c.evaluate(state={"content": sample_text}, questions=questions)
    ans = resp.choices.get("mem_type")
    if ans and ans.choice in criteria:
        return ans.choice  # type: ignore

    return "declarative"

def infer_task_completed(
    title: str,
    body: str,
    client: Optional[SystemOneClient] = None,
) -> bool:
    """
    Determine if the body content indicates that the prospective task/goal has been completed.
    """
    c = client or get_system_one_client()

    questions = {
        "is_completed": NoulQuestion(
            instructions="Does the body text describe that this task, deliverable, or goal has been completed, merged, or fully resolved?"
        )
    }

    resp = c.evaluate(state={"title": title, "body": body[:500]}, questions=questions)
    ans = resp.nouls.get("is_completed")
    return bool(ans and ans.noul >= 0.80)
