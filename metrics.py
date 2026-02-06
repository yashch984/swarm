"""
Derived metrics computed from persisted run summaries.
Computed on read; not logged. Clear boundaries for Phase 2 extensions.
"""

import json
import os
from typing import List, Optional

from run_logging import SUMMARIES_PATH


def load_summaries(path: Optional[str] = None) -> List[dict]:
    """Load run summaries from JSONL. Returns list of summary dicts."""
    p = path or SUMMARIES_PATH
    if not os.path.isfile(p):
        return []
    out = []
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            out.append(json.loads(line))
    return out


def _filter(
    summaries: List[dict],
    arm: Optional[str] = None,
    task_bucket: Optional[str] = None,
    first_pass_only: bool = False,
) -> List[dict]:
    subset = summaries
    if arm is not None:
        subset = [s for s in subset if s.get("arm") == arm]
    if task_bucket is not None:
        subset = [s for s in subset if s.get("task_bucket") == task_bucket]
    if first_pass_only:
        subset = [s for s in subset if s.get("retry_count", 0) == 0]
    return subset


def success_rate(
    summaries: Optional[List[dict]] = None,
    path: Optional[str] = None,
    arm: Optional[str] = None,
    task_bucket: Optional[str] = None,
) -> float:
    """Fraction of runs that succeeded. 0.0 if no runs."""
    data = summaries if summaries is not None else load_summaries(path)
    data = _filter(data, arm=arm, task_bucket=task_bucket)
    if not data:
        return 0.0
    return sum(1 for s in data if s.get("outcome", {}).get("success")) / len(data)


def first_pass_success(
    summaries: Optional[List[dict]] = None,
    path: Optional[str] = None,
    arm: Optional[str] = None,
    task_bucket: Optional[str] = None,
) -> float:
    """Fraction of first-pass runs (retry_count==0) that succeeded. 0.0 if no first-pass runs."""
    data = summaries if summaries is not None else load_summaries(path)
    data = _filter(data, arm=arm, task_bucket=task_bucket, first_pass_only=True)
    if not data:
        return 0.0
    return sum(1 for s in data if s.get("outcome", {}).get("success")) / len(data)


def tokens_per_success(
    summaries: Optional[List[dict]] = None,
    path: Optional[str] = None,
    arm: Optional[str] = None,
    task_bucket: Optional[str] = None,
) -> float:
    """Mean (tokens_in + tokens_out) per successful run. 0.0 if no successes."""
    data = summaries if summaries is not None else load_summaries(path)
    data = _filter(data, arm=arm, task_bucket=task_bucket)
    successful = [s for s in data if s.get("outcome", {}).get("success")]
    if not successful:
        return 0.0
    total = 0
    for s in successful:
        u = s.get("usage") or {}
        total += u.get("tokens_in", 0) + u.get("tokens_out", 0)
    return total / len(successful)


def cost_per_success(
    summaries: Optional[List[dict]] = None,
    path: Optional[str] = None,
    arm: Optional[str] = None,
    task_bucket: Optional[str] = None,
) -> float:
    """Mean cost_usd.total per successful run. 0.0 if no successes."""
    data = summaries if summaries is not None else load_summaries(path)
    data = _filter(data, arm=arm, task_bucket=task_bucket)
    successful = [s for s in data if s.get("outcome", {}).get("success")]
    if not successful:
        return 0.0
    total = sum((s.get("cost_usd") or {}).get("total", 0.0) for s in successful)
    return total / len(successful)
