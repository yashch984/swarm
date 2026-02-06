"""
Event-level logging (JSONL) and run-summary persistence.
No dashboards or advanced analytics.
"""

import json
import os
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Failure reason (exactly one per failed run)
# ---------------------------------------------------------------------------

class FailureReason(str, Enum):
    PLANNING_ERROR = "planning_error"
    TOOL_MISUSE = "tool_misuse"
    HALLUCINATION = "hallucination"
    TIMEOUT = "timeout"
    CONSTRAINT_BREAK = "constraint_break"
    BUDGET_EXCEEDED = "budget_exceeded"


# ---------------------------------------------------------------------------
# Paths (append-only files)
# ---------------------------------------------------------------------------

EVENTS_PATH = os.environ.get("SWARM_EVENTS_PATH", "events.jsonl")
SUMMARIES_PATH = os.environ.get("SWARM_SUMMARIES_PATH", "run_summaries.jsonl")
RUNS_PATH = os.environ.get("SWARM_RUNS_PATH", "runs.jsonl")


def _ensure_dir(path: str) -> None:
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)


def _ts_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# Event schema (required fields only)
# ---------------------------------------------------------------------------

def log_event(
    run_id: str,
    task_id: str,
    arm: str,
    agent_id: str,
    versonality: str,
    phase: str,
    event: str,
    tokens_in: int = 0,
    tokens_out: int = 0,
    task_bucket: str = "",
    retry_count: int = 0,
    path: Optional[str] = None,
) -> None:
    """
    Emit one JSON event per meaningful state transition. Append-only JSONL.
    arm: "monolith" | "swarm"
    phase: "plan" | "act" | "tool" | "verify" | "decide" | "finalize"
    event: "message" | "tool_call" | "tool_result" | "error" | "retry" | "end"
    """
    out = path or EVENTS_PATH
    _ensure_dir(out)
    obj = {
        "ts": _ts_utc(),
        "run_id": run_id,
        "task_id": task_id,
        "arm": arm,
        "agent_id": agent_id,
        "versonality": versonality,
        "phase": phase,
        "event": event,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "metadata": {
            "task_bucket": task_bucket,
            "retry_count": retry_count,
        },
    }
    with open(out, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Run summary (one per attempt)
# ---------------------------------------------------------------------------

def write_run_summary(
    run_id: str,
    task_id: str,
    arm: str,
    task_bucket: str,
    n_agents: int,
    success: bool,
    failure_reason: Optional[FailureReason],
    quality: Optional[float],
    tokens_in: int,
    tokens_out: int,
    cost_usd: float,
    retry_count: int = 0,
    path: Optional[str] = None,
) -> None:
    """
    At end of run: emit one summary object. Persist separately from event logs.
    quality: 0–5 (manual input for now). failure_reason must be set iff success is False.
    """
    if not success and failure_reason is None:
        raise ValueError("failure_reason must be set when success is False")
    if success and failure_reason is not None:
        failure_reason = None
    out = path or SUMMARIES_PATH
    _ensure_dir(out)
    obj = {
        "run_id": run_id,
        "task_id": task_id,
        "arm": arm,
        "task_bucket": task_bucket,
        "n_agents": n_agents,
        "outcome": {
            "success": success,
            "failure_reason": failure_reason.value if failure_reason else None,
        },
        "scores": {"quality": quality},
        "usage": {"tokens_in": tokens_in, "tokens_out": tokens_out},
        "cost_usd": {"total": cost_usd},
        "retry_count": retry_count,
    }
    with open(out, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")
