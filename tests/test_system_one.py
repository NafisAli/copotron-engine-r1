import pytest
from pathlib import Path

from copotron.system_one.types import (
    ChoiceQuestion,
    NoulQuestion,
    ScoreQuestion,
    ChoiceAnswer,
    NoulAnswer,
    ScoreAnswer,
    SystemOneResponse,
)
from copotron.system_one.providers.mock import MockProvider
from copotron.system_one.providers.fallback import HeuristicFallbackProvider
from copotron.system_one.cache import SystemOneCache, compute_cache_key
from copotron.system_one.client import SystemOneClient
from copotron.system_one.judgments.routing import resolve_domain_parent
from copotron.system_one.judgments.intent import parse_search_intent
from copotron.system_one.judgments.rerank import rerank_candidates
from copotron.system_one.judgments.classification import infer_memory_type, infer_task_completed
from copotron.system_one.judgments.slug import generate_clean_slug


def test_system_one_canonical_types():
    cq = ChoiceQuestion("Choose one", {"a": "Option A", "b": "Option B"})
    nq = NoulQuestion("Is this true?")
    sq = ScoreQuestion("Rate relevance", ["Low", "Medium", "High"])

    resp = SystemOneResponse(
        choices={"c1": ChoiceAnswer(choice="a", confidence=0.9)},
        nouls={"n1": NoulAnswer(noul=0.85)},
        scores={"s1": ScoreAnswer(score=2.0, confidence=1.0)},
    )
    assert resp.answers["c1"].choice == "a"
    assert resp.answers["n1"].noul == 0.85
    assert resp.answers["s1"].score == 2.0


def test_mock_provider():
    mock = MockProvider()
    mock.set_answer("my_choice", ChoiceAnswer(choice="custom_pick", confidence=0.99))
    mock.set_answer("my_noul", NoulAnswer(noul=0.12))

    questions = {
        "my_choice": ChoiceQuestion("Select", {"custom_pick": "desc"}),
        "my_noul": NoulQuestion("Question?"),
        "default_q": NoulQuestion("Another?"),
    }
    resp = mock.evaluate(state="sample state", questions=questions)
    assert resp.choices["my_choice"].choice == "custom_pick"
    assert resp.nouls["my_noul"].noul == 0.12
    assert resp.nouls["default_q"].noul == 1.0
    assert len(mock.calls) == 1


def test_fallback_provider_heuristics():
    fallback = HeuristicFallbackProvider()
    questions = {
        "domain": ChoiceQuestion(
            instructions="Select domain",
            criteria={
                "hardware": "Microcontrollers and pinouts",
                "software": "Python code and databases",
                "none": "Neither"
            }
        ),
        "is_id": NoulQuestion(instructions="Is this an ID lookup?"),
        "score": ScoreQuestion(instructions="Rate relevance", criteria=["irrelevant", "relevant"])
    }
    resp = fallback.evaluate(state="ESP32 GPIO 21 pinout wiring", questions=questions)
    assert resp.choices["domain"].choice == "hardware"
    assert resp.choices["domain"].confidence > 0.5
    assert resp.nouls["is_id"].noul < 0.5

    # Test ID lookup detection
    id_resp = fallback.evaluate(state="lookup 2d19791b note", questions=questions)
    assert id_resp.nouls["is_id"].noul > 0.8


def test_cache_hit_and_miss(tmp_path):
    db_file = tmp_path / "test_cache.sqlite3"
    cache = SystemOneCache(db_path=db_file)

    mock = MockProvider()
    mock.set_answer("q", ChoiceAnswer(choice="val1", confidence=1.0))

    client = SystemOneClient(provider=mock, cache=cache)
    questions = {"q": ChoiceQuestion("Pick", {"val1": None})}

    # First call: miss -> evaluates mock
    resp1 = client.evaluate(state="stateA", questions=questions)
    assert resp1.choices["q"].choice == "val1"
    assert len(mock.calls) == 1

    # Second call with identical state & questions: hit -> mock NOT called again
    resp2 = client.evaluate(state="stateA", questions=questions)
    assert resp2.choices["q"].choice == "val1"
    assert len(mock.calls) == 1  # Still 1 call!


def test_client_graceful_fallback_on_provider_error():
    class FailingProvider(MockProvider):
        @property
        def provider_name(self) -> str:
            return "failing"

        def evaluate(self, state, questions, model=None, **kwargs):
            raise ConnectionError("Network down")

    client = SystemOneClient(provider=FailingProvider(), use_cache=False)
    questions = {
        "domain": ChoiceQuestion(
            instructions="Select domain",
            criteria={"hardware": "ESP32", "software": "Python"}
        )
    }
    # Should catch error, print warning, and fall back to local heuristics
    resp = client.evaluate(state="ESP32 hardware", questions=questions)
    assert resp.provider == "fallback"
    assert resp.choices["domain"].choice == "hardware"


def test_judgment_routing_domain():
    mock = MockProvider()
    mock.set_answer("domain_hub", ChoiceAnswer(choice="00000001", confidence=0.85))
    client = SystemOneClient(provider=mock, use_cache=False)

    hubs = [{"id": "00000001", "title": "Work", "summary": "Work projects", "tags": ["work"]}]
    res = resolve_domain_parent("Sprint Planning", "EC2 deployment", hubs, client=client)
    assert res == ["00000001"]

    # Low confidence falls back to root
    mock.set_answer("domain_hub", ChoiceAnswer(choice="00000001", confidence=0.40))
    res_low = resolve_domain_parent("Vague Note", "Nothing clear", hubs, client=client, confidence_threshold=0.65)
    assert res_low == ["00000000"]


def test_judgment_search_intent():
    mock = MockProvider()
    mock.set_answer("is_id_lookup", NoulAnswer(noul=0.95))
    mock.set_answer("implied_type", ChoiceAnswer(choice="declarative", confidence=0.8))
    mock.set_answer("implied_status", ChoiceAnswer(choice="active", confidence=0.8))
    client = SystemOneClient(provider=mock, use_cache=False)

    intent = parse_search_intent("find 2d19791b declarative active notes", client=client)
    assert intent["direct_id"] == "2d19791b"
    assert intent["type_filter"] == "declarative"
    assert intent["status_filter"] == "active"


def test_judgment_rerank_candidates():
    mock = MockProvider()
    mock.set_answer("score_1", ScoreAnswer(score=1.0))
    mock.set_answer("score_2", ScoreAnswer(score=3.0))
    mock.set_answer("score_3", ScoreAnswer(score=0.2))
    client = SystemOneClient(provider=mock, use_cache=False)

    candidates = [
        {"id": "1", "title": "Partial Match"},
        {"id": "2", "title": "Ideal Match"},
        {"id": "3", "title": "Unrelated Match"},
    ]
    reranked = rerank_candidates("Query", "Summary", candidates, client=client, min_score=0.5)
    assert len(reranked) == 2
    assert reranked[0]["id"] == "2"
    assert reranked[1]["id"] == "1"


def test_clean_slug_word_boundary():
    # Long title that would be sliced mid-word by s[:50]
    long_title = "Federation Bachelor of Psychological Science Honours Degree Pathway"
    slug = generate_clean_slug(long_title, max_length=50)
    # Must NOT cut words in half (e.g. no 'honou' or 'degre')
    assert not slug.endswith("-")
    words = slug.split("-")
    for w in words:
        assert w in long_title.lower()
    assert len(slug) <= 50
