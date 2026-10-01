from typing import Any, Dict, Optional, List
from copotron.system_one.protocol import SystemOneProvider
from copotron.system_one.types import (
    Question,
    ChoiceQuestion,
    NoulQuestion,
    ScoreQuestion,
    ChoiceAnswer,
    NoulAnswer,
    ScoreAnswer,
    Answer,
    SystemOneResponse,
    SystemOneUsage,
)

class MockProvider(SystemOneProvider):
    """
    Programmable Mock Provider for unit testing.
    Records calls and returns predefined answers.
    """

    def __init__(self):
        self._preset_answers: Dict[str, Answer] = {}
        self.calls: List[Dict[str, Any]] = []

    @property
    def provider_name(self) -> str:
        return "mock"

    def is_available(self) -> bool:
        return True

    def set_answer(self, question_id: str, answer: Answer):
        self._preset_answers[question_id] = answer

    def evaluate(
        self,
        state: Any,
        questions: Dict[str, Question],
        model: Optional[str] = None,
        **kwargs
    ) -> SystemOneResponse:
        self.calls.append({
            "state": state,
            "questions": questions,
            "model": model,
            "kwargs": kwargs
        })

        choices = {}
        nouls = {}
        scores = {}

        for q_id, q in questions.items():
            if q_id in self._preset_answers:
                ans = self._preset_answers[q_id]
                if isinstance(ans, ChoiceAnswer):
                    choices[q_id] = ans
                elif isinstance(ans, NoulAnswer):
                    nouls[q_id] = ans
                elif isinstance(ans, ScoreAnswer):
                    scores[q_id] = ans
            else:
                # Default fallback mock response
                if isinstance(q, ChoiceQuestion):
                    first_opt = next(iter(q.criteria.keys())) if q.criteria else "none"
                    choices[q_id] = ChoiceAnswer(choice=first_opt, confidence=1.0)
                elif isinstance(q, NoulQuestion):
                    nouls[q_id] = NoulAnswer(noul=1.0)
                elif isinstance(q, ScoreQuestion):
                    scores[q_id] = ScoreAnswer(score=1.0, confidence=1.0)

        return SystemOneResponse(
            choices=choices,
            nouls=nouls,
            scores=scores,
            usage=SystemOneUsage(input_tokens=10, output_tokens=5, estimated_cost_usd=0.0001),
            latency_ms=0.5,
            provider=self.provider_name,
            model=model or "mock-model"
        )
