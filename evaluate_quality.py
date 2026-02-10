"""
Populate quality (0-5) and constraint_adherence (0-1) for batch runs in runs/*.json.

Reads each runs/{task_id}.json; for baseline_output and swarm_output that exist,
calls the same LLM (Groq) with a short rubric to score quality and constraint adherence.
Writes metrics.baseline_quality_score, metrics.swarm_quality_score,
metrics.baseline_constraint_adherence, metrics.swarm_constraint_adherence back into the run file.

Run after batch_runner.py and before aggregate_results.py so ASR uses these scores.
Requires GROQ_API_KEY.
"""

import json
import os
import re

from pipeline import call_api

_BASE = os.path.dirname(os.path.abspath(__file__))
RUNS_DIR = os.path.join(_BASE, "runs")

EVAL_SYSTEM = """You are an evaluator. Reply with exactly two numbers on one line: quality constraint_adherence.
- quality: 0 to 5 (5 = excellent, correct, complete; 0 = wrong or empty).
- constraint_adherence: 0 to 1 (1 = fully followed instructions/constraints; 0 = ignored).
Output format: two numbers separated by a space, e.g. 4.0 0.95"""


def _score_output(task_prompt: str, output: str, arm: str) -> tuple[float | None, float | None]:
    """Call LLM to score one output. Returns (quality, constraint_adherence) or (None, None) on parse failure."""
    if not (output or "").strip():
        return None, None
    user = f"Task:\n{task_prompt[:2000]}\n\nOutput ({arm}):\n{output[:4000]}\n\nScore quality 0-5 and constraint_adherence 0-1. One line: quality constraint_adherence"
    try:
        content, _, _ = call_api([{"role": "system", "content": EVAL_SYSTEM}, {"role": "user", "content": user}])
    except Exception:
        return None, None
    # Parse "3.5 0.9" or "4 1.0"
    numbers = re.findall(r"[0-9]+\.?[0-9]*", (content or "").strip())
    if len(numbers) >= 2:
        try:
            q = max(0.0, min(5.0, float(numbers[0])))
            c = max(0.0, min(1.0, float(numbers[1])))
            return round(q, 2), round(c, 2)
        except ValueError:
            pass
    return None, None


def evaluate_run(run: dict, task_prompt: str) -> dict:
    """Update run['metrics'] with quality and constraint_adherence for baseline and swarm when output exists."""
    metrics = run.get("metrics") or {}
    updated = dict(metrics)

    if run.get("baseline_output") is not None:
        q, c = _score_output(task_prompt, run["baseline_output"], "baseline")
        if q is not None:
            updated["baseline_quality_score"] = q
        if c is not None:
            updated["baseline_constraint_adherence"] = c

    if run.get("swarm_output") is not None:
        q, c = _score_output(task_prompt, run["swarm_output"], "swarm")
        if q is not None:
            updated["swarm_quality_score"] = q
        if c is not None:
            updated["swarm_constraint_adherence"] = c

    run["metrics"] = updated
    return run


def main():
    if not os.path.isdir(RUNS_DIR):
        print("No runs/ directory. Run batch_runner.py first.")
        return
    tasks_by_id = {}
    try:
        with open(os.path.join(_BASE, "tasks_v1.json"), "r", encoding="utf-8") as f:
            tasks_by_id = {t["id"]: t.get("prompt", "") for t in json.load(f).get("tasks", [])}
    except Exception:
        pass
    if not tasks_by_id:
        try:
            with open(os.path.join(_BASE, "benchmark_v1.json"), "r", encoding="utf-8") as f:
                tasks_by_id = {t["id"]: t.get("prompt", "") for t in json.load(f).get("tasks", [])}
        except Exception:
            pass

    n_updated = 0
    for name in sorted(os.listdir(RUNS_DIR)):
        if not name.endswith(".json"):
            continue
        path = os.path.join(RUNS_DIR, name)
        task_id = name[:-5]
        prompt = tasks_by_id.get(task_id, "")
        try:
            with open(path, "r", encoding="utf-8") as f:
                run = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        evaluate_run(run, prompt)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(run, f, indent=2, ensure_ascii=False)
        n_updated += 1
    print(f"Updated quality/constraint_adherence in {n_updated} run files under {RUNS_DIR}")


if __name__ == "__main__":
    main()
