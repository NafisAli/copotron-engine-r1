from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import List, Literal, Optional, Any
from datetime import date as DateType, datetime as DateTimeType
import yaml
from pathlib import Path

class MemorySchema(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    title: str
    date: str
    summary: str
    type: Literal["episodic", "declarative", "procedural", "prospective"]
    status: Literal["active", "completed", "archived", "none"]
    parents: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    persona: Optional[str] = None

    @field_validator("id", mode="before")
    @classmethod
    def coerce_id(cls, v: Any) -> str:
        if v is None:
            raise ValueError("ID is required.")
        if isinstance(v, int):
            return f"{v:08d}"
        return str(v).strip()

    @field_validator("date", mode="before")
    @classmethod
    def coerce_date(cls, v: Any) -> str:
        if isinstance(v, (DateType, DateTimeType)):
            return v.strftime("%Y-%m-%d")
        return str(v).strip()

    @field_validator("parents", mode="before")
    @classmethod
    def coerce_parents(cls, v: Any) -> List[str]:
        if v is None:
            return []
        if isinstance(v, (str, int)):
            v = [v]
        if isinstance(v, list):
            coerced = []
            for item in v:
                if isinstance(item, int):
                    coerced.append(f"{item:08d}")
                else:
                    coerced.append(str(item).strip())
            return coerced
        return v

    @field_validator("tags", mode="before")
    @classmethod
    def coerce_tags(cls, v: Any) -> List[str]:
        if v is None:
            return []
        if isinstance(v, str):
            return [v.strip()]
        if isinstance(v, list):
            return [str(item).strip() for item in v]
        return v

    @field_validator("persona", mode="before")
    @classmethod
    def coerce_persona(cls, v: Any) -> Optional[str]:
        if v is None:
            return None
        s = str(v).strip()
        return s if s else None

def _read_frontmatter_stream(f, file_path: str | Path) -> list[str]:
    found_start = False
    for line in f:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped == "---":
            found_start = True
            break
        else:
            raise ValueError(f"File {file_path} does not have valid YAML frontmatter (missing starting '---').")

    if not found_start:
        raise ValueError(f"File {file_path} does not have valid YAML frontmatter (missing starting '---').")

    yaml_lines = []
    found_end = False
    for line in f:
        if line.rstrip(" \t\r\n") == "---" and not line.startswith((" ", "\t")):
            found_end = True
            break
        yaml_lines.append(line)

    if not found_end:
        raise ValueError(f"File {file_path} frontmatter is malformed (missing closing '---').")

    return yaml_lines

def parse_frontmatter(file_path: str | Path) -> MemorySchema:
    # Use utf-8-sig to automatically strip UTF-8 BOM if present.
    # Streams lines and terminates immediately upon reading the closing '---'.
    with open(file_path, "r", encoding="utf-8-sig") as f:
        yaml_lines = _read_frontmatter_stream(f, file_path)

    yaml_content = "".join(yaml_lines)
    data = yaml.safe_load(yaml_content) or {}
    if not isinstance(data, dict):
        raise ValueError(f"File {file_path} frontmatter must be a YAML mapping/dictionary.")

    return MemorySchema(**data)

def parse_frontmatter_and_body(file_path: str | Path) -> tuple[MemorySchema, str]:
    """Parse frontmatter and return both MemorySchema and remaining body text."""
    with open(file_path, "r", encoding="utf-8-sig") as f:
        yaml_lines = _read_frontmatter_stream(f, file_path)
        body = f.read().lstrip("\r\n")

    yaml_content = "".join(yaml_lines)
    data = yaml.safe_load(yaml_content) or {}
    if not isinstance(data, dict):
        raise ValueError(f"File {file_path} frontmatter must be a YAML mapping/dictionary.")

    return MemorySchema(**data), body

def dump_frontmatter(memory: MemorySchema, body: str) -> str:
    yaml_content = yaml.dump(memory.model_dump(exclude_none=True), sort_keys=False)
    clean_body = body.lstrip("\r\n")
    if clean_body:
        return f"---\n{yaml_content}---\n\n{clean_body}"
    return f"---\n{yaml_content}---\n"
