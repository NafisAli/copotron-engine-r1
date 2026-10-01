import re
import time
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
    SystemOneResponse,
    SystemOneUsage,
)

class HeuristicFallbackProvider(SystemOneProvider):
    """
    Deterministic Local Heuristic Provider.
    Guarantees 100% offline functionality without external dependencies or API keys.
    """

    @property
    def provider_name(self) -> str:
        return "fallback"

    def is_available(self) -> bool:
        return True

    def _extract_tokens(self, text: str) -> set[str]:
        words = re.findall(r"\w+", text.lower())
        tokens = set()
        for w in words:
            if len(w) > 2:
                tokens.add(w)
                if w.endswith("s") and len(w) > 3:
                    tokens.add(w[:-1])
                elif w.endswith("ing") and len(w) > 4:
                    tokens.add(w[:-3])
        return tokens

    def evaluate(
        self,
        state: Any,
        questions: Dict[str, Question],
        model: Optional[str] = None,
        **kwargs
    ) -> SystemOneResponse:
        start_time = time.perf_counter()

        # Normalize state to text
        if isinstance(state, str):
            state_text = state
        elif isinstance(state, dict):
            state_text = " ".join(f"{k}: {v}" for k, v in state.items())
        elif isinstance(state, list):
            state_text = " ".join(str(item) for item in state)
        else:
            state_text = str(state)

        state_tokens = self._extract_tokens(state_text)

        choices = {}
        nouls = {}
        scores = {}

        for q_id, q in questions.items():
            if isinstance(q, ChoiceQuestion):
                best_choice = None
                best_score = -1.0
                probs = {}

                for opt, desc in q.criteria.items():
                    opt_text = f"{opt} {desc or ''}"
                    opt_tokens = self._extract_tokens(opt_text)
                    intersection = state_tokens.intersection(opt_tokens)
                    score = float(len(intersection))
                    probs[opt] = score
                    if score > best_score:
                        best_score = score
                        best_choice = opt

                if best_choice is None or (best_score == 0 and "none" in q.criteria):
                    best_choice = "none" if "none" in q.criteria else next(iter(q.criteria))

                total_score = sum(probs.values())
                if total_score > 0:
                    prob_dist = {k: round(v / total_score, 3) for k, v in probs.items()}
                    confidence = round(best_score / total_score, 2)
                else:
                    count = len(q.criteria) or 1
                    prob_dist = {k: round(1.0 / count, 3) for k in q.criteria}
                    confidence = 0.5

                choices[q_id] = ChoiceAnswer(
                    choice=best_choice,
                    confidence=confidence,
                    probabilities=prob_dist
                )

            elif isinstance(q, NoulQuestion):
                # Basic heuristic for yes/no propositions
                q_inst = q.instructions.lower()
                prob = 0.5
                if any(w in q_inst for w in ("is this an id", "id lookup")):
                    has_hex = bool(re.search(r"\b[0-9a-fA-F]{8}\b", state_text))
                    prob = 0.95 if has_hex else 0.05
                elif "durable" in q_inst or "spec" in q_inst:
                    has_tech = any(w in state_text.lower() for w in ("arch", "config", "command", "api", "code"))
                    prob = 0.85 if has_tech else 0.25
                nouls[q_id] = NoulAnswer(noul=prob)

            elif isinstance(q, ScoreQuestion):
                # Score evaluation based on token overlap against levels
                best_level = 0.0
                if isinstance(q.criteria, list):
                    levels = {str(i): c for i, c in enumerate(q.criteria)}
                else:
                    levels = q.criteria

                best_match = 0
                for idx, (lvl_key, lvl_desc) in enumerate(levels.items()):
                    lvl_tokens = self._extract_tokens(f"{lvl_key} {lvl_desc}")
                    overlap = len(state_tokens.intersection(lvl_tokens))
                    if overlap > best_match:
                        best_match = overlap
                        try:
                            best_level = float(lvl_key)
                        except ValueError:
                            best_level = float(idx)

                scores[q_id] = ScoreAnswer(
                    score=best_level,
                    confidence=0.75,
                    probabilities={k: 0.25 for k in levels}
                )

        latency_ms = (time.perf_counter() - start_time) * 1000.0

        return SystemOneResponse(
            choices=choices,
            nouls=nouls,
            scores=scores,
            usage=SystemOneUsage(input_tokens=0, output_tokens=0, estimated_cost_usd=0.0),
            latency_ms=round(latency_ms, 2),
            provider=self.provider_name,
            model="heuristic-rule-engine"
        )
