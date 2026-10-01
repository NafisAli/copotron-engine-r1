from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union, Literal

@dataclass
class ChoiceQuestion:
    instructions: str
    criteria: Dict[str, Optional[str]]
    question_type: Literal["choice"] = "choice"

@dataclass
class NoulQuestion:
    instructions: str
    criteria: Optional[Dict[str, str]] = None
    question_type: Literal["noul"] = "noul"

@dataclass
class ScoreQuestion:
    instructions: str
    criteria: Union[List[str], Dict[str, str]]
    question_type: Literal["score"] = "score"

Question = Union[ChoiceQuestion, NoulQuestion, ScoreQuestion]

@dataclass
class ChoiceAnswer:
    choice: str
    confidence: float = 1.0
    probabilities: Dict[str, float] = field(default_factory=dict)

@dataclass
class NoulAnswer:
    noul: float

@dataclass
class ScoreAnswer:
    score: float
    confidence: float = 1.0
    probabilities: Dict[str, float] = field(default_factory=dict)

Answer = Union[ChoiceAnswer, NoulAnswer, ScoreAnswer]

@dataclass
class SystemOneUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0

@dataclass
class SystemOneResponse:
    choices: Dict[str, ChoiceAnswer] = field(default_factory=dict)
    nouls: Dict[str, NoulAnswer] = field(default_factory=dict)
    scores: Dict[str, ScoreAnswer] = field(default_factory=dict)
    answers: Dict[str, Answer] = field(default_factory=dict)
    usage: SystemOneUsage = field(default_factory=SystemOneUsage)
    latency_ms: float = 0.0
    provider: str = "unknown"
    model: str = "unknown"

    def __post_init__(self):
        # Automatically populate answers dict combining all answer types
        if not self.answers:
            self.answers = {}
            self.answers.update(self.choices)
            self.answers.update(self.nouls)
            self.answers.update(self.scores)
