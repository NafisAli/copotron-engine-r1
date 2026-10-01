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


def _format_state_block(state: Any, indent_level: int = 2) -> list[str]:
    """Format state dictionary or object into clean YAML-like indented lines."""
    pad = " " * indent_level
    lines = []
    if isinstance(state, dict):
        for k, v in state.items():
            if isinstance(v, dict):
                lines.append(f"{pad}{k}:")
                lines.extend(_format_state_block(v, indent_level + 2))
            elif isinstance(v, list):
                if all(not isinstance(x, (dict, list)) for x in v):
                    items_str = ", ".join(str(x) for x in v)
                    lines.append(f"{pad}{k}: [{items_str}]")
                else:
                    lines.append(f"{pad}{k}:")
                    for x in v:
                        lines.append(f"{pad}  - {x}")
            else:
                lines.append(f"{pad}{k}: {v}")
    elif isinstance(state, list):
        for item in state:
            lines.append(f"{pad}- {item}")
    elif state is not None:
        for sline in str(state).splitlines():
            lines.append(f"{pad}{sline}")
    if not lines:
        lines.append(f"{pad}(none)")
    return lines


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
    Format a TypeSafe Jev API call into a readable, un-JSONified block that
    unifies question instructions, criteria, resulting decision, confidence,
    probabilities, and state.
    """
    ts = timestamp or datetime.now(timezone.utc)
    ts_str = ts.strftime("%Y-%m-%d %H:%M:%S UTC")
    status = "SUCCESS" if error is None else "ERROR"

    banner = "=" * 80
    divider = "-" * 80

    lines = [
        banner,
        "TYPESAFE JEV DECISION CALL",
        f"Timestamp:  {ts_str}",
        f"Model:      {model}",
        f"Status:     {status}",
        f"Latency:    {latency_ms:.2f} ms",
    ]

    # Usage details
    usage_obj = None
    if response and hasattr(response, "usage") and response.usage:
        usage_obj = response.usage
    elif raw_res and hasattr(raw_res, "usage") and raw_res.usage:
        usage_obj = raw_res.usage

    if usage_obj:
        in_tokens = getattr(usage_obj, "input_tokens", 0)
        out_tokens = getattr(usage_obj, "output_tokens", 0)
        total_tokens = in_tokens + out_tokens
        cost = getattr(usage_obj, "estimated_cost_usd", 0.0)
        lines.append(
            f"Usage:      {in_tokens} input tokens, {out_tokens} output tokens (Total: {total_tokens}) | Est. Cost: ${cost:.6f}"
        )

    lines.append(divider)
    lines.append("STATE:")
    lines.extend(_format_state_block(state, indent_level=2))
    lines.append(divider)

    if error is not None:
        lines.append(f"QUESTIONS SUBMITTED ({len(questions)} Questions):\n")
        for idx, (qid, q) in enumerate(questions.items(), start=1):
            q_type = getattr(q, "question_type", getattr(q, "type", "question")).capitalize()
            instructions = getattr(q, "instructions", str(q))
            criteria = getattr(q, "criteria", None)

            lines.append(f"{idx}. [{qid}] {q_type} Question")
            lines.append(f"   Instructions: {instructions}")
            if criteria:
                lines.append("   Criteria:")
                if isinstance(criteria, dict):
                    for ck, cv in criteria.items():
                        lines.append(f"     * {ck}: {cv}")
                elif isinstance(criteria, list):
                    for c_idx, cv in enumerate(criteria):
                        lines.append(f"     * [{c_idx}] {cv}")
            lines.append("")

        lines.append(divider)
        lines.append("ERROR DETAILS:")
        lines.append(f"Type:    {error.__class__.__name__}")
        lines.append(f"Message: {str(error)}")
        details = getattr(error, "details", None)
        if details:
            lines.append(f"Details: {details}")
    else:
        lines.append(f"EVALUATIONS ({len(questions)} Questions):\n")
        for idx, (qid, q) in enumerate(questions.items(), start=1):
            q_type = str(getattr(q, "question_type", getattr(q, "type", "question"))).lower()
            instructions = getattr(q, "instructions", str(q))
            criteria = getattr(q, "criteria", None)

            if q_type == "choice":
                lines.append(f"{idx}. [{qid}] Choice Question")
                lines.append(f"   Instructions: {instructions}")

                ans = None
                if response and hasattr(response, "choices"):
                    ans = response.choices.get(qid)
                elif response and hasattr(response, "answers"):
                    ans = response.answers.get(qid)
                elif raw_res and hasattr(raw_res, "choices"):
                    ans = raw_res.choices.get(qid)
                elif raw_res and hasattr(raw_res, "answers"):
                    ans = raw_res.answers.get(qid)

                if ans:
                    choice = getattr(ans, "choice", str(ans))
                    conf = getattr(ans, "confidence", 1.0)
                    lines.append(f'   -> RESULT:    "{choice}" (Confidence: {conf * 100:.1f}%)')

                    probs = getattr(ans, "probabilities", {}) or {}
                    keys = list(criteria.keys()) if isinstance(criteria, dict) else list(probs.keys())
                    if keys:
                        lines.append("   Probabilities:")
                        for k in keys:
                            p = probs.get(k, 0.0)
                            desc = criteria.get(k) if isinstance(criteria, dict) else None
                            desc_str = f"  ({desc})" if desc else ""
                            lines.append(f"     * {k}: {p * 100:>5.1f}%{desc_str}")

            elif q_type == "score":
                lines.append(f"{idx}. [{qid}] Score Question")
                lines.append(f"   Instructions: {instructions}")

                ans = None
                if response and hasattr(response, "scores"):
                    ans = response.scores.get(qid)
                elif response and hasattr(response, "answers"):
                    ans = response.answers.get(qid)
                elif raw_res and hasattr(raw_res, "scores"):
                    ans = raw_res.scores.get(qid)
                elif raw_res and hasattr(raw_res, "answers"):
                    ans = raw_res.answers.get(qid)

                if ans:
                    score = getattr(ans, "score", 0.0)
                    conf = getattr(ans, "confidence", 1.0)
                    max_scale = len(criteria) - 1 if isinstance(criteria, (list, dict)) and len(criteria) > 1 else 1.0
                    lines.append(f"   -> RESULT:    Score {score:.2f} / {max_scale:.2f} (Confidence: {conf * 100:.1f}%)")

                    probs = getattr(ans, "probabilities", {}) or {}
                    if criteria or probs:
                        lines.append("   Scale & Probabilities:")
                        if isinstance(criteria, list):
                            for c_idx, desc in enumerate(criteria):
                                p = probs.get(c_idx, probs.get(str(c_idx), probs.get(desc, 0.0)))
                                lines.append(f"     * [{c_idx}] {desc}: {p * 100:>5.1f}%")
                        elif isinstance(criteria, dict):
                            for ck, desc in criteria.items():
                                p = probs.get(ck, probs.get(str(ck), probs.get(desc, 0.0)))
                                lines.append(f"     * [{ck}] {desc}: {p * 100:>5.1f}%")
                        elif probs:
                            for pk, pv in probs.items():
                                lines.append(f"     * [{pk}]: {pv * 100:>5.1f}%")

            elif q_type == "noul":
                lines.append(f"{idx}. [{qid}] Noul Question (Probability Scale 0.0 - 1.0)")
                lines.append(f"   Instructions: {instructions}")

                ans = None
                if response and hasattr(response, "nouls"):
                    ans = response.nouls.get(qid)
                elif response and hasattr(response, "answers"):
                    ans = response.answers.get(qid)
                elif raw_res and hasattr(raw_res, "nouls"):
                    ans = raw_res.nouls.get(qid)
                elif raw_res and hasattr(raw_res, "answers"):
                    ans = raw_res.answers.get(qid)

                if ans:
                    noul_val = getattr(ans, "noul", 0.0)
                    try:
                        noul_num = float(noul_val)
                    except (ValueError, TypeError):
                        noul_num = 0.0
                    lines.append(f"   -> RESULT:    {noul_num:.2f} ({noul_num * 100:.1f}% True / Declarative)")

            else:
                lines.append(f"{idx}. [{qid}] {q_type.capitalize()} Question")
                lines.append(f"   Instructions: {instructions}")

            lines.append("")

    lines.append(banner)
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
