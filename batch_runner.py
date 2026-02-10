"""
Batch runner: run baseline and swarm for each benchmark task, write results to runs/{task_id}.json.
Uses shared pipeline (no Streamlit/UI dependencies). No retries, no parallelization.
"""

import json
import os
import time
import uuid

from pipeline import SWARM_ROLES, run_baseline, run_swarm
from run_logging import FailureReason, RUNS_PATH, write_run_summary

_BASE = os.path.dirname(__file__)
TASKS_V1_PATH = os.path.join(_BASE, "tasks_v1.json")
BENCHMARK_PATH = os.path.join(_BASE, "benchmark_v1.json")
RUNS_DIR = os.path.join(_BASE, "runs")


def load_benchmark(path=None):
    path = path or (TASKS_V1_PATH if os.path.isfile(TASKS_V1_PATH) else BENCHMARK_PATH)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def run_task(task):
    """Run baseline and swarm for one task. Return result dict for runs/{task_id}.json.

    Also emits run summaries to logs/runs.jsonl using the Instrumentation Appendix schema
    (quality/constraint_adherence left null; failure_reason derived from exceptions when any).
    """
    task_id = task["id"]
    task_bucket = task["task_bucket"]
    prompt = task["prompt"]
    run_id = str(uuid.uuid4())

    baseline_output = None
    swarm_output = None
    baseline_tokens_in = baseline_tokens_out = 0
    swarm_tokens_in = swarm_tokens_out = 0
    baseline_error_type = None
    swarm_error_type = None
    t0 = time.perf_counter()

    try:
        baseline_output, baseline_tokens_in, baseline_tokens_out = run_baseline(
            prompt, run_id, task_id, task_bucket
        )
    except Exception as e:
        baseline_error_type = type(e).__name__
        baseline_output = None

    t1 = time.perf_counter()

    if baseline_error_type is None:
        try:
            swarm_output, swarm_tokens_in, swarm_tokens_out = run_swarm(
                prompt, run_id, task_id, task_bucket
            )
        except Exception as e:
            swarm_error_type = type(e).__name__
            swarm_output = None

    t2 = time.perf_counter()
    baseline_time = t1 - t0
    swarm_time = t2 - t1
    wall_time_seconds = t2 - t0
    baseline_tokens_used = baseline_tokens_in + baseline_tokens_out
    swarm_tokens_used = swarm_tokens_in + swarm_tokens_out
    tokens_used = baseline_tokens_used + swarm_tokens_used

    baseline_success = baseline_output is not None
    swarm_success = swarm_output is not None

    # Map Python error types to FailureReason when possible (best-effort) per arm
    def map_error(err: str | None) -> FailureReason | None:
        if not err:
            return None
        name = err.lower()
        if "timeout" in name:
            return FailureReason.TIMEOUT
        if "budget" in name:
            return FailureReason.BUDGET_EXCEEDED
        if "tool" in name:
            return FailureReason.TOOL_FAILURE
        return FailureReason.PLANNING_ERROR

    failure_reason_baseline = map_error(baseline_error_type)
    # If swarm was never attempted (baseline failed), fall back to baseline error for swarm arm
    failure_reason_swarm = map_error(swarm_error_type or baseline_error_type)

    # Overall success flag kept for backward compatibility (used in runs/{task_id}.json)
    success = baseline_success and swarm_success

    # Emit run summaries for each arm with null quality/constraint_adherence and cost (tokens-only cost can be added later)
    cost_baseline = 0.0
    cost_swarm = 0.0
    write_run_summary(
        run_id=run_id,
        task_id=task_id,
        arm="monolith",
        task_bucket=task_bucket,
        n_agents=1,
        success=baseline_success,
        failure_reason=failure_reason_baseline,
        quality=None,
        tokens_in=baseline_tokens_in,
        tokens_out=baseline_tokens_out,
        cost_usd=cost_baseline,
        retry_count=0,
        wall_seconds=baseline_time,
        path=RUNS_PATH,
    )
    write_run_summary(
        run_id=run_id,
        task_id=task_id,
        arm="swarm",
        task_bucket=task_bucket,
        n_agents=len(SWARM_ROLES),
        success=swarm_success,
        failure_reason=failure_reason_swarm,
        quality=None,
        tokens_in=swarm_tokens_in,
        tokens_out=swarm_tokens_out,
        cost_usd=cost_swarm,
        retry_count=0,
        wall_seconds=swarm_time,
        path=RUNS_PATH,
    )

    return {
        "task_id": task_id,
        "task_bucket": task_bucket,
        "baseline_output": baseline_output,
        "swarm_output": swarm_output,
        "metrics": {
            "success": success,
            "quality_score": None,
            "constraint_adherence": None,
            "wall_time_seconds": round(wall_time_seconds, 4),
            "tokens_used": tokens_used,
            "baseline_tokens_used": baseline_tokens_used,
            "swarm_tokens_used": swarm_tokens_used,
            "error_type": baseline_error_type or swarm_error_type,
        },
    }


def main(benchmark_path=None):
    os.makedirs(RUNS_DIR, exist_ok=True)
    data = load_benchmark(benchmark_path)
    tasks = data.get("tasks", [])

    for task in tasks:
        task_id = task["id"]
        out_path = os.path.join(RUNS_DIR, f"{task_id}.json")
        result = run_task(task)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"Wrote {out_path} (success={result['metrics']['success']})")


if __name__ == "__main__":
    main()
