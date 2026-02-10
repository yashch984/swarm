"""
Aggregate run results from runs/*.json. Computes SR, FPS, Quality, Time p50/p95,
Cost per Success, ASR, VPD, Coordination Overhead. Writes results/summary_v1.json
(Evaluation Spec v0.1, Instrumentation Appendix v0.1).
"""

import json
import os
from collections import defaultdict

_BASE = os.path.dirname(os.path.abspath(__file__))
RUNS_DIR = os.path.join(_BASE, "runs")
RESULTS_DIR = os.path.join(_BASE, "results")
BENCHMARK_PATH = os.path.join(_BASE, "benchmark_v1.json")
SUMMARY_V1_PATH = os.path.join(RESULTS_DIR, "summary_v1.json")


def load_runs():
    """Load all JSON files from runs/ and return list of result dicts."""
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


def get_benchmark_version():
    """Read benchmark_version from benchmark_v1.json if present."""
    try:
        with open(BENCHMARK_PATH, "r", encoding="utf-8") as f:
            return json.load(f).get("benchmark_version", "sv-v1")
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return "sv-v1"


def percentile(sorted_values, p):
    """Return p-th percentile (0–100). Uses linear interpolation."""
    if not sorted_values:
        return None
    n = len(sorted_values)
    idx = (p / 100.0) * (n - 1)
    i, frac = int(idx), idx % 1
    if i >= n - 1:
        return float(sorted_values[-1])
    return float(sorted_values[i]) + frac * (float(sorted_values[i + 1]) - float(sorted_values[i]))


def asr_per_run(success, quality, constraint_adherence):
    """Adjusted Success Rate for one run: SR × (quality/5) × constraint_adherence."""
    s = 1.0 if success else 0.0
    q = float(quality) if quality is not None else 0.0
    c = float(constraint_adherence) if constraint_adherence is not None else 0.0
    return s * (q / 5.0) * c


def aggregate(runs):
    """Compute all summary metrics from a list of run dicts."""
    n = len(runs)
    if n == 0:
        return {
            "benchmark_version": get_benchmark_version(),
            "task_count": 0,
            "baseline_metrics": {},
            "swarm_metrics": {},
            "deltas": {},
            "wall_time_seconds": {},
            "coordination_overhead": None,
            "vpd_asr": None,
            "notable_failures": {},
        }

    baseline_successes = sum(1 for r in runs if r.get("baseline_output") is not None)
    swarm_successes = sum(1 for r in runs if r.get("swarm_output") is not None)
    success_rate_baseline = baseline_successes / n
    success_rate_swarm = swarm_successes / n

    wall_times = sorted(r["metrics"]["wall_time_seconds"] for r in runs)
    p50_wall = percentile(wall_times, 50)
    p95_wall = percentile(wall_times, 95)

    baseline_tokens = [r["metrics"].get("baseline_tokens_used") for r in runs]
    swarm_tokens = [r["metrics"].get("swarm_tokens_used") for r in runs]
    baseline_tokens = [t for t in baseline_tokens if t is not None]
    swarm_tokens = [t for t in swarm_tokens if t is not None]
    avg_baseline_tokens = sum(baseline_tokens) / len(baseline_tokens) if baseline_tokens else None
    avg_swarm_tokens = sum(swarm_tokens) / len(swarm_tokens) if swarm_tokens else None
    token_delta = None
    if avg_baseline_tokens is not None and avg_swarm_tokens is not None:
        token_delta = avg_swarm_tokens - avg_baseline_tokens

    quality_scores_b = [r["metrics"].get("baseline_quality_score") for r in runs]
    quality_scores_s = [r["metrics"].get("swarm_quality_score") for r in runs]
    pairs = [(b, s) for b, s in zip(quality_scores_b, quality_scores_s) if b is not None and s is not None]
    quality_delta = None
    if pairs:
        quality_delta = sum(s - b for b, s in pairs) / len(pairs)

    # ASR = SR × (quality/5) × constraint_adherence per run, then average. Use per-arm quality when present.
    asr_baseline = sum(
        asr_per_run(
            r.get("baseline_output") is not None,
            r["metrics"].get("baseline_quality_score") or r["metrics"].get("quality_score"),
            r["metrics"].get("constraint_adherence"),
        )
        for r in runs
    ) / n
    asr_swarm = sum(
        asr_per_run(
            r.get("swarm_output") is not None,
            r["metrics"].get("swarm_quality_score") or r["metrics"].get("quality_score"),
            r["metrics"].get("constraint_adherence"),
        )
        for r in runs
    ) / n

    error_counts = defaultdict(list)
    for r in runs:
        et = r["metrics"].get("error_type")
        if et:
            error_counts[et].append(r["task_id"])
    notable_failures = {k: {"count": len(v), "task_ids": v} for k, v in sorted(error_counts.items())}

    # FPS: first-pass success (no retry); batch_runner does not set retry_count, so FPS = SR for now
    fps_baseline = success_rate_baseline
    fps_swarm = success_rate_swarm

    # VPD: Versonality Performance Delta = swarm ASR − baseline ASR
    vpd_asr = (asr_swarm - asr_baseline) if (asr_swarm is not None and asr_baseline is not None) else None

    # Coordination overhead: token and time delta (swarm − baseline)
    coordination_overhead = {}
    if token_delta is not None:
        coordination_overhead["token_delta"] = round(token_delta, 2)
    # Time delta would need per-arm wall time; we have combined wall_time_seconds per task. Omit or approximate.

    summary = {
        "benchmark_version": get_benchmark_version(),
        "task_count": n,
        "baseline_metrics": {
            "success_rate": round(success_rate_baseline, 4),
            "fps": round(fps_baseline, 4),
            "avg_tokens_used": round(avg_baseline_tokens, 2) if avg_baseline_tokens is not None else None,
            "asr": round(asr_baseline, 4),
        },
        "swarm_metrics": {
            "success_rate": round(success_rate_swarm, 4),
            "fps": round(fps_swarm, 4),
            "avg_tokens_used": round(avg_swarm_tokens, 2) if avg_swarm_tokens is not None else None,
            "asr": round(asr_swarm, 4),
        },
        "deltas": {
            "quality_delta": round(quality_delta, 4) if quality_delta is not None else None,
            "token_cost_delta": round(token_delta, 2) if token_delta is not None else None,
        },
        "wall_time_seconds": {
            "p50": round(p50_wall, 4) if p50_wall is not None else None,
            "p95": round(p95_wall, 4) if p95_wall is not None else None,
        },
        "coordination_overhead": coordination_overhead if coordination_overhead else None,
        "vpd_asr": round(vpd_asr, 4) if vpd_asr is not None else None,
        "notable_failures": notable_failures,
    }
    return summary


def main():
    runs = load_runs()
    summary = aggregate(runs)
    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(SUMMARY_V1_PATH, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"Wrote {SUMMARY_V1_PATH} (task_count={summary['task_count']})")


if __name__ == "__main__":
    main()
