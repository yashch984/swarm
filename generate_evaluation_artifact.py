"""
Generate internal evaluation artifact from results/summary_v1.json and runs/*.json.
Summarizes: deltas, where versonalities helped or hurt, cost/efficiency tradeoffs.
Per Evaluation Spec v0.1. Does not run tasks or modify benchmarks.
"""

import json
import os
from datetime import datetime, timezone

_BASE = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(_BASE, "results")
RUNS_DIR = os.path.join(_BASE, "runs")
SUMMARY_V1_PATH = os.path.join(RESULTS_DIR, "summary_v1.json")
ARTIFACT_JSON_PATH = os.path.join(RESULTS_DIR, "internal_evaluation.json")
ARTIFACT_TXT_PATH = os.path.join(RESULTS_DIR, "internal_evaluation.txt")


def _load_summary():
    try:
        with open(SUMMARY_V1_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _load_runs():
    if not os.path.isdir(RUNS_DIR):
        return []
    runs = []
    for name in sorted(os.listdir(RUNS_DIR)):
        if not name.endswith(".json"):
            continue
        path = os.path.join(RUNS_DIR, name)
        try:
            with open(path, "r", encoding="utf-8") as f:
                runs.append(json.load(f))
        except (json.JSONDecodeError, OSError):
            continue
    return runs


def _ts():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def generate():
    """Build evaluation artifact (structured + narrative). Returns (dict, str) or (None, None)."""
    summary = _load_summary()
    if not summary:
        return None, None

    runs = _load_runs()
    baseline_sr = summary.get("baseline_metrics") or {}
    swarm_sr = summary.get("swarm_metrics") or {}
    deltas = summary.get("deltas") or {}
    overhead = summary.get("coordination_overhead") or {}
    vpd = summary.get("vpd_asr")
    failures = summary.get("notable_failures") or {}
    n = summary.get("task_count", 0)

    # Per-task: where did swarm do better/worse (by success and token delta)
    helped = []
    hurt = []
    neutral = []
    for r in runs:
        tid = r.get("task_id", "")
        bucket = r.get("task_bucket", "")
        b_ok = r.get("baseline_output") is not None
        s_ok = r.get("swarm_output") is not None
        m = r.get("metrics") or {}
        bt = m.get("baseline_tokens_used") or 0
        st = m.get("swarm_tokens_used") or 0
        if s_ok and not b_ok:
            helped.append({"task_id": tid, "task_bucket": bucket, "reason": "swarm_success_baseline_failed"})
        elif b_ok and not s_ok:
            hurt.append({"task_id": tid, "task_bucket": bucket, "reason": "baseline_success_swarm_failed"})
        elif s_ok and b_ok:
            if st < bt:
                helped.append({"task_id": tid, "task_bucket": bucket, "reason": "swarm_fewer_tokens"})
            elif st > bt:
                hurt.append({"task_id": tid, "task_bucket": bucket, "reason": "swarm_more_tokens"})
            else:
                neutral.append({"task_id": tid, "task_bucket": bucket})
        else:
            neutral.append({"task_id": tid, "task_bucket": bucket})

    token_delta = deltas.get("token_cost_delta") or overhead.get("token_delta")
    quality_delta = deltas.get("quality_delta")

    artifact = {
        "generated_at": _ts(),
        "benchmark_version": summary.get("benchmark_version"),
        "task_count": n,
        "deltas": {
            "quality_delta": quality_delta,
            "token_cost_delta": token_delta,
        },
        "vpd_asr": vpd,
        "coordination_overhead": overhead,
        "where_versonalities_helped": helped,
        "where_versonalities_hurt": hurt,
        "neutral": neutral,
        "cost_efficiency_tradeoff": {
            "swarm_uses_more_tokens": token_delta is not None and token_delta > 0,
            "token_delta": token_delta,
            "baseline_avg_tokens": baseline_sr.get("avg_tokens_used"),
            "swarm_avg_tokens": swarm_sr.get("avg_tokens_used"),
        },
        "notable_failures": failures,
    }

    # Short narrative
    lines = [
        "Internal evaluation artifact (Evaluation Spec v0.1)",
        "Generated: " + artifact["generated_at"],
        "",
        "Deltas:",
        "  Quality delta: " + str(quality_delta),
        "  Token cost delta (swarm − baseline): " + str(token_delta),
        "  VPD (ASR delta): " + str(vpd),
        "",
        "Cost/efficiency:",
        "  Swarm uses more tokens: " + str(artifact["cost_efficiency_tradeoff"]["swarm_uses_more_tokens"]),
        "  Baseline avg tokens: " + str(baseline_sr.get("avg_tokens_used")),
        "  Swarm avg tokens: " + str(swarm_sr.get("avg_tokens_used")),
        "",
        "Where versonalities helped (task_ids): " + str([x["task_id"] for x in helped]),
        "Where versonalities hurt (task_ids): " + str([x["task_id"] for x in hurt]),
        "Neutral (task_ids): " + str([x["task_id"] for x in neutral]),
        "",
        "Notable failures: " + str(failures),
    ]
    narrative = "\n".join(lines)

    return artifact, narrative


def main():
    os.makedirs(RESULTS_DIR, exist_ok=True)
    artifact, narrative = generate()
    if artifact is None:
        print("No summary_v1.json found. Run batch_runner.py then aggregate_results.py first.")
        return
    with open(ARTIFACT_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(artifact, f, indent=2, ensure_ascii=False)
    with open(ARTIFACT_TXT_PATH, "w", encoding="utf-8") as f:
        f.write(narrative)
    print("Wrote", ARTIFACT_JSON_PATH, "and", ARTIFACT_TXT_PATH)


if __name__ == "__main__":
    main()
