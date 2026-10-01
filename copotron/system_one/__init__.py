"""
copotron.system_one: Non-autoregressive decision layer for fast, structured judgments.
Powered by TypeSafe Jev and pluggable decision providers with local heuristic fallback.
"""

from copotron.system_one.types import (
    ChoiceQuestion,
    NoulQuestion,
    ScoreQuestion,
    ChoiceAnswer,
    NoulAnswer,
    ScoreAnswer,
    SystemOneResponse,
    SystemOneUsage,
    Question,
    Answer,
)
from copotron.system_one.protocol import SystemOneProvider
from copotron.system_one.client import SystemOneClient, get_system_one_client

__all__ = [
    "ChoiceQuestion",
    "NoulQuestion",
    "ScoreQuestion",
    "ChoiceAnswer",
    "NoulAnswer",
    "ScoreAnswer",
    "SystemOneResponse",
    "SystemOneUsage",
    "Question",
    "Answer",
    "SystemOneProvider",
    "SystemOneClient",
    "get_system_one_client",
]
