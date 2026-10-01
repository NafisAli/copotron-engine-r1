import re

def generate_clean_slug(title: str, max_length: int = 50) -> str:
    """
    Generate a clean, lower-case, hyphenated slug without cutting words in half.
    Breaks on whole word boundaries to prevent truncated suffixes (e.g. 'honou' or trailing hyphens).
    """
    s = title.lower()
    s = re.sub(r"[^\w\s-]", "", s)
    words = [w for w in re.split(r"[\s_]+", s) if w]

    if not words:
        return "untitled"

    slug_parts = []
    current_len = 0

    for w in words:
        added_len = len(w) if not slug_parts else len(w) + 1
        if current_len + added_len > max_length:
            break
        slug_parts.append(w)
        current_len += added_len

    if not slug_parts:
        slug_parts = [words[0][:max_length]]

    slug = "-".join(slug_parts).strip("-")
    return slug or "untitled"
