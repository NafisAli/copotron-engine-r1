import os
import time
from typing import Any, Dict, Optional

from copotron.system_one.protocol import SystemOneProvider
from copotron.core.logger import log_typesafe_call
from copotron.system_one.types import (
    Question,
    ChoiceQuestion,
    NoulQuestion,
    ScoreQuestion,
    ChoiceAnswer,
    NoulAnswer,
    ScoreAnswer,
    SystemOneResponse,
    SystemOneUsage,
)

PRICE_PER_MILLION_INPUT = 0.042

class TypeSafeProvider(SystemOneProvider):
    """
    TypeSafe Jev System One Provider.
    Executes non-autoregressive parallel decision questions via typesafe-sdk.
    """

    DEFAULT_MODEL = "jev-latest"

    def __init__(self, api_key: Optional[str] = None, timeout: float = 30.0):
        self._api_key = api_key or os.getenv("TYPESAFE_API_KEY")
        self._timeout = timeout
        self._client = None

    @property
    def provider_name(self) -> str:
        return "typesafe"

    def is_available(self) -> bool:
        return bool(self._api_key or os.getenv("TYPESAFE_API_KEY"))

    def _get_client(self):
        if self._client is None:
            try:
                from typesafe_sdk import TypeSafeClient
                key = self._api_key or os.getenv("TYPESAFE_API_KEY")
                self._client = TypeSafeClient(api_key=key, timeout=self._timeout)
            except Exception as e:
                raise RuntimeError(f"Failed to initialize TypeSafeClient: {e}") from e
        return self._client

    def evaluate(
        self,
        state: Any,
        questions: Dict[str, Question],
        model: Optional[str] = None,
        **kwargs
    ) -> SystemOneResponse:
        client = self._get_client()
        target_model = model or os.getenv("SYSTEM_ONE_MODEL", self.DEFAULT_MODEL)

        try:
            from typesafe_sdk import Choice, Noul, Score, NoulCriteria
        except ImportError as e:
            raise RuntimeError("typesafe-sdk is not installed. Install via 'uv add typesafe-sdk'.") from e

        sdk_questions = {}
        for q_id, q in questions.items():
            if isinstance(q, ChoiceQuestion):
                sdk_questions[q_id] = Choice(instructions=q.instructions, criteria=q.criteria)
            elif isinstance(q, NoulQuestion):
                criteria = NoulCriteria(**q.criteria) if q.criteria else None
                sdk_questions[q_id] = Noul(instructions=q.instructions, criteria=criteria)
            elif isinstance(q, ScoreQuestion):
                criteria = list(q.criteria.values()) if isinstance(q.criteria, dict) else list(q.criteria)
                sdk_questions[q_id] = Score(instructions=q.instructions, criteria=criteria)
            else:
                raise ValueError(f"Unsupported question type: {type(q)}")

        start_time = time.perf_counter()
        raw_res = None
        error = None
        resp = None

        try:
            raw_res = client.system_one(state=state, questions=sdk_questions, model=target_model)
            choices = {}
            nouls = {}
            scores = {}

            for q_id, q in questions.items():
                if isinstance(q, ChoiceQuestion):
                    ans = raw_res.choices.get(q_id) or raw_res.answers.get(q_id)
                    if ans:
                        choices[q_id] = ChoiceAnswer(
                            choice=getattr(ans, "choice", str(ans)),
                            confidence=getattr(ans, "confidence", 1.0),
                            probabilities=getattr(ans, "probabilities", {}) or {}
                        )
                elif isinstance(q, NoulQuestion):
                    ans = raw_res.nouls.get(q_id) or raw_res.answers.get(q_id)
                    if ans:
                        nouls[q_id] = NoulAnswer(
                            noul=float(getattr(ans, "noul", ans))
                        )
                elif isinstance(q, ScoreQuestion):
                    ans = raw_res.scores.get(q_id) or raw_res.answers.get(q_id)
                    if ans:
                        scores[q_id] = ScoreAnswer(
                            score=float(getattr(ans, "score", ans)),
                            confidence=getattr(ans, "confidence", 1.0),
                            probabilities=getattr(ans, "probabilities", {}) or {}
                        )

            in_tokens = getattr(raw_res.usage, "input_tokens", 0) if hasattr(raw_res, "usage") else 0
            out_tokens = getattr(raw_res.usage, "output_tokens", 0) if hasattr(raw_res, "usage") else 0
            est_cost = (in_tokens / 1_000_000.0) * PRICE_PER_MILLION_INPUT

            usage = SystemOneUsage(
                input_tokens=in_tokens,
                output_tokens=out_tokens,
                estimated_cost_usd=est_cost
            )

            latency_ms = (time.perf_counter() - start_time) * 1000.0
            resp = SystemOneResponse(
                choices=choices,
                nouls=nouls,
                scores=scores,
                usage=usage,
                latency_ms=round(latency_ms, 2),
                provider=self.provider_name,
                model=target_model
            )
            return resp
        except Exception as e:
            error = e
            raise
        finally:
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            try:
                log_typesafe_call(
                    model=target_model,
                    state=state,
                    questions=questions,
                    response=resp,
                    raw_res=raw_res,
                    error=error,
                    latency_ms=latency_ms,
                )
            except Exception:
                pass

