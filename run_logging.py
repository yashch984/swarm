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
    TOOL_FAILURE = "tool_failure"
    HALLUCINATION = "hallucination"
    TIMEOUT = "timeout"
    CONSTRAINT_BREAK = "constraint_break"
    BUDGET_EXCEEDED = "budget_exceeded"
    UNRESOLVED_DISAGREEMENT = "unresolved_disagreement"


# ---------------------------------------------------------------------------
# Paths (append-only files) — Instrumentation Appendix v0.1
# ---------------------------------------------------------------------------

_BASE = os.path.dirname(os.path.abspath(__file__))
_LOGS_DIR = os.path.join(_BASE, "logs")
EVENTS_PATH = os.environ.get("SWARM_EVENTS_PATH", os.path.join(_LOGS_DIR, "events.jsonl"))
SUMMARIES_PATH = os.environ.get("SWARM_SUMMARIES_PATH", os.path.join(_LOGS_DIR, "runs.jsonl"))
RUNS_PATH = os.environ.get("SWARM_RUNS_PATH", os.path.join(_LOGS_DIR, "runs.jsonl"))


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
    tool: Optional[str] = None,
    tool_ok: Optional[bool] = None,
    seed: Optional[int] = None,
    handoff_to: Optional[str] = None,
    path: Optional[str] = None,
) -> None:
    """
    Emit one JSON event per meaningful state transition. Append-only JSONL.
    arm: "monolith" | "swarm"
    phase: "plan" | "act" | "tool" | "verify" | "decide" | "finalize"
    event: "message" | "tool_call" | "tool_result" | "error" | "retry" | "escalation" | "judge_score" | "end"
    tool / tool_ok: when a tool is invoked, pass tool="tool_name" and tool_ok=True|False so
    event-level logging tracks tool correctness (Instrumentation Appendix v0.1).
    Matches Instrumentation Appendix v0.1 (ts, run_id, task_id, arm, agent_id, versonality,
    phase, event, tokens_in/out, tool/tool_ok, metadata.{task_bucket, seed, retry_count, handoff_to}).
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
        "tool": tool,
        "tool_ok": tool_ok,
        "metadata": {
            "task_bucket": task_bucket,
            "retry_count": retry_count,
            "seed": seed,
            "handoff_to": handoff_to,
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
    *,
    seed: Optional[int] = None,
    max_tokens: Optional[int] = None,
    max_seconds: Optional[float] = None,
    constraint_adherence: Optional[float] = None,
    policy_violation: bool = False,
    hallucination_critical: bool = False,
    wall_seconds: Optional[float] = None,
    tool_calls: int = 0,
    tool_calls_ok: int = 0,
    swarm_conflict: Optional[bool] = None,
    consensus_seconds: Optional[float] = None,
    handoffs: Optional[int] = None,
    duplicate_work: Optional[bool] = None,
    cost_model: float = 0.0,
    cost_tools: float = 0.0,
    path: Optional[str] = None,
) -> None:
    """
    At end of run: emit one summary object. Persist separately from event logs.
    Matches Instrumentation Appendix v0.1 run summary schema:
    - budgets {max_tokens, max_seconds}
    - outcome {success, failure_reason, policy_violation, hallucination_critical}
    - scores {quality, constraint_adherence}
    - usage {wall_seconds, tokens_in, tokens_out, tool_calls, tool_calls_ok}
    - swarm {conflict, consensus_seconds, handoffs, duplicate_work}
    - cost_usd {model, tools, total}
    quality: 0–5 (manual input for now). failure_reason must be set iff success is False.
    """
    if not success and failure_reason is None:
        raise ValueError("failure_reason must be set when success is False")
    if success and failure_reason is not None:
        failure_reason = None
    out = path or SUMMARIES_PATH
    _ensure_dir(out)
    swarm_block: Optional[dict[str, Any]] = None
    if any(v is not None for v in (swarm_conflict, consensus_seconds, handoffs, duplicate_work)):
        swarm_block = {
            "conflict": swarm_conflict,
            "consensus_seconds": consensus_seconds,
            "handoffs": handoffs,
            "duplicate_work": duplicate_work,
        }
    obj: dict[str, Any] = {
        "run_id": run_id,
        "task_id": task_id,
        "arm": arm,
        "seed": seed,
        "task_bucket": task_bucket,
        "n_agents": n_agents,
        "budgets": {
            "max_tokens": max_tokens,
            "max_seconds": max_seconds,
        },
        "outcome": {
            "success": success,
            "failure_reason": failure_reason.value if failure_reason else None,
            "policy_violation": policy_violation,
            "hallucination_critical": hallucination_critical,
        },
        "scores": {
            "quality": quality,
            "constraint_adherence": constraint_adherence,
        },
        "usage": {
            "wall_seconds": wall_seconds,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "tool_calls": tool_calls,
            "tool_calls_ok": tool_calls_ok,
        },
        "swarm": swarm_block,
        "cost_usd": {
            "model": cost_model,
            "tools": cost_tools,
            "total": cost_usd,
        },
        "retry_count": retry_count,
    }
    with open(out, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")
