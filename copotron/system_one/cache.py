import json
import time
import hashlib
from typing import Any, Dict, Optional
from pathlib import Path

from copotron.core.vault import get_vault_path
from copotron.core.db import get_db_path, init_db
from copotron.system_one.types import (
    Question,
    ChoiceQuestion,
    NoulQuestion,
    ScoreQuestion,
    SystemOneResponse,
    ChoiceAnswer,
    NoulAnswer,
    ScoreAnswer,
    SystemOneUsage,
)

def _serialize_question(q: Question) -> Dict[str, Any]:
    if isinstance(q, ChoiceQuestion):
        return {"type": "choice", "instructions": q.instructions, "criteria": q.criteria}
    elif isinstance(q, NoulQuestion):
        return {"type": "noul", "instructions": q.instructions, "criteria": q.criteria}
    elif isinstance(q, ScoreQuestion):
        return {"type": "score", "instructions": q.instructions, "criteria": q.criteria}
    return {"type": "unknown", "instructions": getattr(q, "instructions", "")}

def compute_cache_key(provider: str, model: str, state: Any, questions: Dict[str, Question]) -> str:
    """Generate a deterministic SHA-256 cache key."""
    canonical_state = json.dumps(state, sort_keys=True, default=str)
    canonical_questions = json.dumps(
        {k: _serialize_question(v) for k, v in sorted(questions.items())},
        sort_keys=True
    )
    raw = f"{provider}:{model}:{canonical_state}:{canonical_questions}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def serialize_response(resp: SystemOneResponse) -> str:
    """Serialize SystemOneResponse to JSON string."""
    data = {
        "provider": resp.provider,
        "model": resp.model,
        "latency_ms": resp.latency_ms,
        "usage": {
            "input_tokens": resp.usage.input_tokens,
            "output_tokens": resp.usage.output_tokens,
            "estimated_cost_usd": resp.usage.estimated_cost_usd,
        },
        "choices": {
            k: {
                "choice": v.choice,
                "confidence": v.confidence,
                "probabilities": v.probabilities,
            }
            for k, v in resp.choices.items()
        },
        "nouls": {
            k: {
                "noul": v.noul,
            }
            for k, v in resp.nouls.items()
        },
        "scores": {
            k: {
                "score": v.score,
                "confidence": v.confidence,
                "probabilities": v.probabilities,
            }
            for k, v in resp.scores.items()
        }
    }
    return json.dumps(data)

def deserialize_response(json_str: str) -> SystemOneResponse:
    """Deserialize JSON string back into SystemOneResponse."""
    data = json.loads(json_str)
    choices = {
        k: ChoiceAnswer(
            choice=v["choice"],
            confidence=v.get("confidence", 1.0),
            probabilities=v.get("probabilities", {})
        )
        for k, v in data.get("choices", {}).items()
    }
    nouls = {
        k: NoulAnswer(noul=v["noul"])
        for k, v in data.get("nouls", {}).items()
    }
    scores = {
        k: ScoreAnswer(
            score=v["score"],
            confidence=v.get("confidence", 1.0),
            probabilities=v.get("probabilities", {})
        )
        for k, v in data.get("scores", {}).items()
    }
    usage_data = data.get("usage", {})
    usage = SystemOneUsage(
        input_tokens=usage_data.get("input_tokens", 0),
        output_tokens=usage_data.get("output_tokens", 0),
        estimated_cost_usd=usage_data.get("estimated_cost_usd", 0.0),
    )
    return SystemOneResponse(
        choices=choices,
        nouls=nouls,
        scores=scores,
        usage=usage,
        latency_ms=data.get("latency_ms", 0.0),
        provider=data.get("provider", "cache"),
        model=data.get("model", "cached")
    )

class SystemOneCache:
    """
    Persistent judgment cache backed by SQLite (.index.sqlite3)
    with in-memory dictionary caching.
    """

    def __init__(self, db_path: Optional[Path] = None):
        self._memory_cache: Dict[str, SystemOneResponse] = {}
        self._db_path = db_path

    def _get_db_conn(self):
        if self._db_path is not None:
            return init_db(self._db_path)
        try:
            vault_dir = get_vault_path(require_root=False)
            if vault_dir and vault_dir.exists():
                db_p = get_db_path(vault_dir)
                return init_db(db_p)
        except Exception:
            pass
        return None

    def get(self, cache_key: str) -> Optional[SystemOneResponse]:
        if cache_key in self._memory_cache:
            return self._memory_cache[cache_key]

        conn = self._get_db_conn()
        if conn is None:
            return None

        try:
            cur = conn.execute("SELECT response_json FROM system_one_cache WHERE cache_key = ?;", (cache_key,))
            row = cur.fetchone()
            if row:
                resp = deserialize_response(row[0])
                self._memory_cache[cache_key] = resp
                return resp
        except Exception:
            pass
        finally:
            conn.close()

        return None

    def set(self, cache_key: str, response: SystemOneResponse):
        self._memory_cache[cache_key] = response
        conn = self._get_db_conn()
        if conn is None:
            return

        try:
            payload = serialize_response(response)
            with conn:
                conn.execute("""
                INSERT OR REPLACE INTO system_one_cache (cache_key, provider, model, response_json, created_at)
                VALUES (?, ?, ?, ?, ?);
                """, (cache_key, response.provider, response.model, payload, time.time()))
        except Exception:
            pass
        finally:
            conn.close()

    def clear(self):
        self._memory_cache.clear()
        conn = self._get_db_conn()
        if conn is not None:
            try:
                with conn:
                    conn.execute("DELETE FROM system_one_cache;")
            except Exception:
                pass
            finally:
                conn.close()
