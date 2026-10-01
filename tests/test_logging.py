import os
import json
import zipfile
import pytest
from pathlib import Path
from unittest.mock import MagicMock

from copotron.core.logger import (
    get_log_dir,
    get_dedicated_logger,
    format_typesafe_log_entry,
    log_typesafe_call,
    DEFAULT_MAX_BYTES,
    DEFAULT_BACKUP_COUNT,
)
from copotron.system_one.types import (
    ChoiceQuestion,
    NoulQuestion,
    ScoreQuestion,
    ChoiceAnswer,
    NoulAnswer,
    ScoreAnswer,
    SystemOneResponse,
    SystemOneUsage,
)
from copotron.system_one.providers.typesafe import TypeSafeProvider


def test_log_dir_and_keep_file():
    log_dir = get_log_dir()
    assert log_dir.exists()
    assert log_dir.is_dir()

    keep_file = log_dir / ".keep"
    assert keep_file.exists()
    assert keep_file.is_file()


def test_dedicated_logger_writes_to_isolated_files(tmp_path):
    logger_a = get_dedicated_logger("subsystem_a", log_dir=tmp_path)
    logger_b = get_dedicated_logger("subsystem_b", log_dir=tmp_path)

    assert not logger_a.propagate
    assert not logger_b.propagate

    logger_a.info("Message for subsystem A")
    logger_b.info("Message for subsystem B")

    # Flush handlers
    for h in logger_a.handlers:
        h.flush()
    for h in logger_b.handlers:
        h.flush()

    file_a = tmp_path / "subsystem_a.log"
    file_b = tmp_path / "subsystem_b.log"

    assert file_a.exists()
    assert file_b.exists()

    content_a = file_a.read_text(encoding="utf-8")
    content_b = file_b.read_text(encoding="utf-8")

    assert "Message for subsystem A" in content_a
    assert "Message for subsystem B" not in content_a

    assert "Message for subsystem B" in content_b
    assert "Message for subsystem A" not in content_b


def test_zip_rotation_and_backup_count(tmp_path):
    # Set small max_bytes = 120 and backup_count = 10
    logger = get_dedicated_logger("rot_test", max_bytes=120, backup_count=10, log_dir=tmp_path)

    # Write enough lines to exceed threshold and trigger multiple rollovers
    for i in range(25):
        logger.info(f"Entry {i:03d} - padding text to ensure rotation happens accurately!")

    for h in logger.handlers:
        h.flush()

    # Verify active log and .zip archives
    files = list(tmp_path.iterdir())
    zip_files = [f for f in files if f.name.endswith(".zip")]
    log_files = [f for f in files if f.name.endswith(".log")]

    assert len(log_files) == 1
    assert len(zip_files) > 0
    # Backup retention should not exceed 10 archives
    assert len(zip_files) <= 10

    # Ensure zipped files are valid zip archives containing the log file
    first_zip = tmp_path / "rot_test.log.1.zip"
    assert first_zip.exists()
    with zipfile.ZipFile(first_zip, "r") as zf:
        namelist = zf.namelist()
        assert "rot_test.log" in namelist
        # Verify content can be read
        extracted = zf.read("rot_test.log").decode("utf-8")
        assert len(extracted) > 0


def test_typesafe_log_entry_format_success():
    questions = {
        "cat": ChoiceQuestion("Select category", {"p": "Physics", "c": "Chemistry"}),
        "conf": NoulQuestion("Rate confidence"),
        "rel": ScoreQuestion("Rate relevance", ["low", "high"]),
    }
    state = {"title": "Quantum Entanglement", "tags": ["quantum", "physics"]}
    usage = SystemOneUsage(input_tokens=150, output_tokens=25, estimated_cost_usd=0.000006)
    response = SystemOneResponse(
        choices={"cat": ChoiceAnswer(choice="p", confidence=0.95, probabilities={"p": 0.95, "c": 0.05})},
        nouls={"conf": NoulAnswer(noul=0.88)},
        scores={"rel": ScoreAnswer(score=1.0, confidence=0.9, probabilities={"low": 0.1, "high": 0.9})},
        usage=usage,
        latency_ms=125.5,
        model="jev-latest",
        provider="typesafe",
    )

    entry = format_typesafe_log_entry(
        model="jev-latest",
        state=state,
        questions=questions,
        response=response,
        latency_ms=125.5,
    )

    # Check scannable banner lines
    assert "================================================================================" in entry
    assert "TYPESAFE JEV DECISION CALL" in entry
    assert "Model:      jev-latest" in entry
    assert "Status:     SUCCESS" in entry
    assert "Latency:    125.50 ms" in entry
    assert "Usage:      150 input tokens, 25 output tokens (Total: 175) | Est. Cost: $0.000006" in entry

    # Check State section
    assert "STATE:" in entry
    assert "title: Quantum Entanglement" in entry
    assert "tags: [quantum, physics]" in entry

    # Check unified Evaluations section
    assert "EVALUATIONS (3 Questions):" in entry
    assert "[cat] Choice Question" in entry
    assert '-> RESULT:    "p" (Confidence: 95.0%)' in entry
    assert "p:  95.0%  (Physics)" in entry
    assert "c:   5.0%  (Chemistry)" in entry

    assert "[conf] Noul Question (Probability Scale 0.0 - 1.0)" in entry
    assert "-> RESULT:    0.88 (88.0% True / Declarative)" in entry

    assert "[rel] Score Question" in entry
    assert "-> RESULT:    Score 1.00 / 1.00 (Confidence: 90.0%)" in entry
    assert "[0] low:  10.0%" in entry
    assert "[1] high:  90.0%" in entry


def test_typesafe_log_entry_format_error():
    questions = {"q1": NoulQuestion("Is valid?")}
    state = "raw state query"
    err = ValueError("Invalid API payload provided")

    entry = format_typesafe_log_entry(
        model="jev-latest",
        state=state,
        questions=questions,
        error=err,
        latency_ms=45.2,
    )

    assert "Status:     ERROR" in entry
    assert "Latency:    45.20 ms" in entry
    assert "STATE:" in entry
    assert "raw state query" in entry
    assert "QUESTIONS SUBMITTED (1 Questions):" in entry
    assert "[q1] Noul Question" in entry
    assert "ERROR DETAILS:" in entry
    assert "Type:    ValueError" in entry
    assert "Message: Invalid API payload provided"


def test_typesafe_provider_logging_hook(tmp_path, monkeypatch):
    monkeypatch.setenv("COPOTRON_LOGS_DIR", str(tmp_path))
    # Clear cached logger if any
    from copotron.core.logger import _LOGGERS
    _LOGGERS.pop("typesafe", None)

    provider = TypeSafeProvider(api_key="test_dummy_key")

    mock_sdk_client = MagicMock()
    mock_raw_res = MagicMock()
    mock_raw_res.choices = {"cat": MagicMock(choice="opt_a", confidence=0.99, probabilities={"opt_a": 0.99})}
    mock_raw_res.nouls = {}
    mock_raw_res.scores = {}
    mock_raw_res.usage = MagicMock(input_tokens=100, output_tokens=10)

    mock_sdk_client.system_one.return_value = mock_raw_res
    provider._client = mock_sdk_client

    questions = {"cat": ChoiceQuestion("Pick", {"opt_a": "A", "opt_b": "B"})}
    resp = provider.evaluate(state="sample state", questions=questions)

    assert resp.choices["cat"].choice == "opt_a"

    # Verify typesafe.log was written
    log_file = tmp_path / "typesafe.log"
    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8")

    assert "TYPESAFE JEV DECISION CALL" in content
    assert "Status:     SUCCESS" in content
    assert "sample state" in content
    assert '-> RESULT:    "opt_a"' in content


def test_typesafe_provider_logging_on_exception(tmp_path, monkeypatch):
    monkeypatch.setenv("COPOTRON_LOGS_DIR", str(tmp_path))
    from copotron.core.logger import _LOGGERS
    _LOGGERS.pop("typesafe", None)

    provider = TypeSafeProvider(api_key="test_dummy_key")

    mock_sdk_client = MagicMock()
    mock_sdk_client.system_one.side_effect = RuntimeError("Upstream API connection refused")
    provider._client = mock_sdk_client

    questions = {"cat": ChoiceQuestion("Pick", {"opt_a": "A"})}

    with pytest.raises(RuntimeError, match="Upstream API connection refused"):
        provider.evaluate(state="error state", questions=questions)

    log_file = tmp_path / "typesafe.log"
    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8")

    assert "Status:     ERROR" in content
    assert "ERROR DETAILS:" in content
    assert "Upstream API connection refused" in content


def test_logging_failure_is_resilient(monkeypatch):
    # If get_dedicated_logger fails, log_typesafe_call must not raise
    def broken_logger(*args, **kwargs):
        raise PermissionError("Disk is read only")

    monkeypatch.setattr("copotron.core.logger.get_dedicated_logger", broken_logger)

    # Must complete smoothly without raising
    log_typesafe_call(
        model="jev-latest",
        state="test",
        questions={},
    )
