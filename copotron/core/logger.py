import os
import sys
import json
import time
import zipfile
import logging
import logging.handlers
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Union

DEFAULT_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
DEFAULT_BACKUP_COUNT = 10

_LOGGERS: Dict[str, logging.Logger] = {}


def get_log_dir() -> Path:
    """
    Resolve and ensure the dedicated logs directory exists.
    Checks COPOTRON_LOGS_DIR or LOGS_DIR environment variables,
    defaulting to copotron-engine-r1/logs.
    """
    env_dir = os.getenv("COPOTRON_LOGS_DIR") or os.getenv("LOGS_DIR")
    if env_dir:
        log_dir = Path(env_dir).resolve()
    else:
        # Resolve to <engine_root>/logs
        log_dir = Path(__file__).resolve().parent.parent.parent / "logs"

    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def _zip_rotator(source: str, dest: str) -> None:
    """
    Compress the rotated source log file directly into a .zip archive at dest.
    Removes the uncompressed source upon successful zip creation.
    Falls back to normal file rename if compression fails.
    """
    try:
        with open(source, "rb") as f_in:
            with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                zf.writestr(os.path.basename(source), f_in.read())
        try:
            os.remove(source)
        except OSError:
            pass
    except Exception:
        # Fallback to direct replacement if zipping fails
        try:
            if os.path.exists(dest):
                os.remove(dest)
            os.rename(source, dest)
        except OSError:
            pass


def _zip_namer(default_name: str) -> str:
    """
    Append '.zip' to the default rotated log name (e.g. typesafe.log.1 -> typesafe.log.1.zip).
    """
    return default_name + ".zip"


def get_dedicated_logger(
    name: str,
    max_bytes: Optional[int] = None,
    backup_count: Optional[int] = None,
    log_dir: Optional[Path] = None,
) -> logging.Logger:
    """
    Retrieve or initialize an isolated dedicated subsystem logger.
    Writes strictly to <log_dir>/<name>.log with automatic zip rotation.
    Logs do not propagate to stdout/stderr or the root logger.
    """
    if name in _LOGGERS:
        return _LOGGERS[name]

    logger_name = f"copotron.{name}"
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    target_dir = log_dir if log_dir is not None else get_log_dir()
    filepath = target_dir / f"{name}.log"

    if max_bytes is None:
        try:
            max_bytes = int(os.getenv("COPOTRON_LOG_MAX_BYTES", str(DEFAULT_MAX_BYTES)))
        except (ValueError, TypeError):
            max_bytes = DEFAULT_MAX_BYTES

    if backup_count is None:
        try:
            backup_count = int(os.getenv("COPOTRON_LOG_BACKUP_COUNT", str(DEFAULT_BACKUP_COUNT)))
        except (ValueError, TypeError):
            backup_count = DEFAULT_BACKUP_COUNT

    handler = logging.handlers.RotatingFileHandler(
        str(filepath),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    handler.rotator = _zip_rotator
    handler.namer = _zip_namer
    handler.setFormatter(logging.Formatter("%(message)s"))

    logger.handlers.clear()
    logger.addHandler(handler)
    _LOGGERS[name] = logger
    return logger


def _serialize_question(q: Any) -> Dict[str, Any]:
    """Serialize a Question dataclass or object into a JSON-friendly dict."""
    q_type = getattr(q, "question_type", None) or getattr(q, "type", "question")
    instructions = getattr(q, "instructions", str(q))
    criteria = getattr(q, "criteria", None)
    if isinstance(criteria, dict):
        clean_criteria = criteria
    elif isinstance(criteria, list):
        clean_criteria = criteria
    else:
        clean_criteria = criteria

    res = {
        "type": str(q_type),
        "instructions": instructions,
    }
    if clean_criteria is not None:
        res["criteria"] = clean_criteria
    return res


def format_typesafe_log_entry(
    model: str,
    state: Any,
    questions: Dict[str, Any],
    response: Optional[Any] = None,
    raw_res: Optional[Any] = None,
    error: Optional[Exception] = None,
    latency_ms: float = 0.0,
    timestamp: Optional[datetime] = None,
) -> str:
    """
    Format a TypeSafe Jev API call into a hybrid scannable banner with
    indented JSON blocks for request and response/error sections.
    """
    ts = timestamp or datetime.now(timezone.utc)
    iso_ts = ts.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    status = "SUCCESS" if error is None else "ERROR"

    # 1. Format Request JSON block
    serialized_questions = {
        qid: _serialize_question(q) for qid, q in questions.items()
    }
    req_dict = {
        "state": state,
        "questions": serialized_questions,
    }
    req_json = json.dumps(req_dict, indent=2, default=str)

    # 2. Format Response or Error JSON block
    if error is not None:
        err_dict = {
            "type": error.__class__.__name__,
            "message": str(error),
            "details": getattr(error, "details", None),
        }
        resp_section_header = "<<< ERROR:"
        resp_json = json.dumps(err_dict, indent=2, default=str)
    else:
        resp_dict: Dict[str, Any] = {}
        # Extract usage
        if response and hasattr(response, "usage") and response.usage:
            resp_dict["usage"] = {
                "input_tokens": getattr(response.usage, "input_tokens", 0),
                "output_tokens": getattr(response.usage, "output_tokens", 0),
                "estimated_cost_usd": getattr(response.usage, "estimated_cost_usd", 0.0),
            }
        elif raw_res and hasattr(raw_res, "usage") and raw_res.usage:
            resp_dict["usage"] = {
                "input_tokens": getattr(raw_res.usage, "input_tokens", 0),
                "output_tokens": getattr(raw_res.usage, "output_tokens", 0),
                "estimated_cost_usd": 0.0,
            }

        # Extract answers
        answers_dict: Dict[str, Any] = {}
        if response:
            if hasattr(response, "choices") and response.choices:
                for qid, ans in response.choices.items():
                    answers_dict[qid] = {
                        "type": "choice",
                        "choice": getattr(ans, "choice", str(ans)),
                        "confidence": getattr(ans, "confidence", 1.0),
                        "probabilities": getattr(ans, "probabilities", {}),
                    }
            if hasattr(response, "nouls") and response.nouls:
                for qid, ans in response.nouls.items():
                    noul_val = getattr(ans, "noul", None)
                    if noul_val is None:
                        try:
                            noul_val = float(ans)
                        except (ValueError, TypeError):
                            noul_val = str(ans)
                    answers_dict[qid] = {
                        "type": "noul",
                        "noul": noul_val,
                    }
            if hasattr(response, "scores") and response.scores:
                for qid, ans in response.scores.items():
                    score_val = getattr(ans, "score", None)
                    if score_val is None:
                        try:
                            score_val = float(ans)
                        except (ValueError, TypeError):
                            score_val = str(ans)
                    answers_dict[qid] = {
                        "type": "score",
                        "score": score_val,
                        "confidence": getattr(ans, "confidence", 1.0),
                        "probabilities": getattr(ans, "probabilities", {}),
                    }
        elif raw_res and hasattr(raw_res, "answers"):
            answers_dict = raw_res.answers

        resp_dict["answers"] = answers_dict
        resp_section_header = "<<< RESPONSE:"
        resp_json = json.dumps(resp_dict, indent=2, default=str)

    divider = "-" * 80
    banner = "=" * 80

    lines = [
        banner,
        f"[{iso_ts}] TYPESAFE JEV API CALL | Model: {model} | Status: {status} | Latency: {latency_ms:.2f}ms",
        divider,
        ">>> REQUEST:",
        req_json,
        divider,
        resp_section_header,
        resp_json,
        banner,
    ]
    return "\n".join(lines)


def log_typesafe_call(
    model: str,
    state: Any,
    questions: Dict[str, Any],
    response: Optional[Any] = None,
    raw_res: Optional[Any] = None,
    error: Optional[Exception] = None,
    latency_ms: float = 0.0,
    logger_name: str = "typesafe",
) -> None:
    """
    Safely format and log a TypeSafe Jev API call to the dedicated logger.
    Errors during logging will not raise or interrupt program flow.
    """
    try:
        logger = get_dedicated_logger(logger_name)
        entry = format_typesafe_log_entry(
            model=model,
            state=state,
            questions=questions,
            response=response,
            raw_res=raw_res,
            error=error,
            latency_ms=latency_ms,
        )
        logger.info(entry)
    except Exception:
        # Guardrail: Never let logging failure break application logic
        pass
