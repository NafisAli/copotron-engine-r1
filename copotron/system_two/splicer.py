import re
from typing import Dict, List, Tuple, Optional
from copotron.system_one.client import get_system_one_client, SystemOneClient
from copotron.system_one.types import ChoiceQuestion

def parse_markdown_sections(text: str) -> List[Tuple[str, str, str]]:
    """
    Parse markdown into sections: (header_prefix, header_title, content).
    If text has preamble before the first header, it is returned as ('', '', preamble).
    """
    lines = text.split("\n")
    sections: List[Tuple[str, str, str]] = []

    current_prefix = ""
    current_title = ""
    current_lines: List[str] = []

    header_re = re.compile(r"^(#{1,6})\s+(.*)$")

    for line in lines:
        match = header_re.match(line)
        if match:
            # Commit previous section
            sections.append((current_prefix, current_title, "\n".join(current_lines).strip()))
            current_prefix = match.group(1)
            current_title = match.group(2).strip()
            current_lines = []
        else:
            current_lines.append(line)

    sections.append((current_prefix, current_title, "\n".join(current_lines).strip()))
    return [s for s in sections if s[0] or s[1] or s[2]]

def splice_markdown_sections(
    existing_body: str,
    incoming_body: str,
    client: Optional[SystemOneClient] = None,
) -> str:
    """
    Surgically splice incoming markdown into an existing markdown note without full rewriting:
    1. Compares incoming sections against existing sections.
    2. Uses System One judgment to decide if matching sections should replace or extend.
    3. Preserves unrelated existing sections intact.
    4. Code owns the string assembly; model only decides alignment.
    """
    if not existing_body or not existing_body.strip():
        return incoming_body.strip()
    if not incoming_body or not incoming_body.strip():
        return existing_body.strip()

    existing_sections = parse_markdown_sections(existing_body)
    incoming_sections = parse_markdown_sections(incoming_body)

    # If neither document has structured headers, fallback to clean concatenation
    has_existing_headers = any(s[1] for s in existing_sections)
    has_incoming_headers = any(s[1] for s in incoming_sections)

    if not has_existing_headers or not has_incoming_headers:
        return f"{existing_body.rstrip()}\n\n{incoming_body.lstrip()}".strip()

    c = client or get_system_one_client()

    # Build lookup table of existing sections by normalized title
    existing_map: Dict[str, int] = {}
    for idx, (prefix, title, content) in enumerate(existing_sections):
        if title:
            existing_map[title.lower()] = idx

    updated_sections = list(existing_sections)

    for in_prefix, in_title, in_content in incoming_sections:
        if not in_title:
            # Incoming preamble with no header -> append to top preamble or create note
            if updated_sections and not updated_sections[0][1]:
                p_pref, p_title, p_content = updated_sections[0]
                updated_sections[0] = (p_pref, p_title, f"{p_content}\n\n{in_content}".strip())
            continue

        norm_title = in_title.lower()
        if norm_title in existing_map:
            match_idx = existing_map[norm_title]
            ex_prefix, ex_title, ex_content = updated_sections[match_idx]

            # Ask System One whether to replace or extend this section
            q_id = f"splice_{norm_title[:20]}"
            questions = {
                q_id: ChoiceQuestion(
                    instructions=f"For section '{ex_title}', does the new content update/replace the existing content or extend/add to it?",
                    criteria={
                        "replace": "The new content is an updated, corrected, or superceding version of this section.",
                        "extend": "The new content is an addition, extra step, or supplementary detail to this section.",
                    }
                )
            }
            state = {
                "section": ex_title,
                "existing_text": ex_content[:300],
                "incoming_text": in_content[:300],
            }

            resp = c.evaluate(state=state, questions=questions)
            ans = resp.choices.get(q_id)
            action = ans.choice if ans else "extend"

            if action == "replace":
                updated_sections[match_idx] = (ex_prefix, ex_title, in_content)
            else:
                updated_sections[match_idx] = (ex_prefix, ex_title, f"{ex_content}\n\n{in_content}".strip())
        else:
            # Brand new section -> append
            updated_sections.append((in_prefix, in_title, in_content))

    # Assemble back to clean markdown
    blocks = []
    for prefix, title, content in updated_sections:
        if prefix and title:
            blocks.append(f"{prefix} {title}\n\n{content}".strip())
        elif content:
            blocks.append(content)

    return "\n\n".join(blocks).strip()
