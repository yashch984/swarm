"""
Streamlit dashboard for Swarm Versonalities v1.

Shows, in one place:
- Task list and run coverage (tasks_v1.json vs runs/*.json)
- Aggregate benchmark metrics (results/summary_v1.json, logs/runs.jsonl)
- Moltbook post content (combined post with prompt + results)
- Bintly orchestrator state and recent errors
- External reports count (if any)
"""

import json
import os
from typing import Any, Dict, List, Optional

import streamlit as st

from metrics import (
    average_quality,
    cost_per_success,
    load_summaries,
    success_rate,
    first_pass_success,
    tokens_per_success,
    tool_correctness,
    policy_violation_rate,
    critical_hallucination_rate,
)


_BASE = os.path.dirname(os.path.abspath(__file__))
TASKS_V1_PATH = os.path.join(_BASE, "tasks_v1.json")
BENCHMARK_PATH = os.path.join(_BASE, "benchmark_v1.json")
RUNS_DIR = os.path.join(_BASE, "runs")
RESULTS_DIR = os.path.join(_BASE, "results")
SUMMARY_V1_PATH = os.path.join(RESULTS_DIR, "summary_v1.json")
ARTIFACT_JSON_PATH = os.path.join(RESULTS_DIR, "internal_evaluation.json")
COMBINED_POST_PATH = os.path.join(_BASE, "moltbook_combined_post.txt")
LAUNCH_POST_PATH = os.path.join(_BASE, "moltbook_launch_post.txt")
RESULTS_POST_PATH = os.path.join(_BASE, "moltbook_results_post.txt")
EXTERNAL_REPORTS_PATH = os.path.join(_BASE, "external_reports.json")
BINTLY_STATE_PATH = os.path.join(_BASE, ".bintly_orchestrator_state.json")
BINTLY_ERRORS_PATH = os.path.join(_BASE, "logs", "bintly_errors.log")


def _load_json(path: str) -> Optional[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _load_tasks() -> List[Dict[str, Any]]:
    """Load tasks from tasks_v1.json (or benchmark_v1.json as fallback)."""
    path = TASKS_V1_PATH if os.path.isfile(TASKS_V1_PATH) else BENCHMARK_PATH
    data = _load_json(path) or {}
    return data.get("tasks", [])


def _load_run_file(task_id: str) -> Optional[Dict[str, Any]]:
    if not os.path.isdir(RUNS_DIR):
        return None
    path = os.path.join(RUNS_DIR, f"{task_id}.json")
    return _load_json(path)


def _load_summary_v1() -> Optional[Dict[str, Any]]:
    return _load_json(SUMMARY_V1_PATH)


def _load_artifact() -> Optional[Dict[str, Any]]:
    return _load_json(ARTIFACT_JSON_PATH)


def _read_text(path: str, default: str = "") -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except (FileNotFoundError, OSError):
        return default


def _tail_file(path: str, max_lines: int = 50) -> List[str]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except (FileNotFoundError, OSError):
        return []
    if len(lines) <= max_lines:
        return [ln.rstrip("\n") for ln in lines]
    return [ln.rstrip("\n") for ln in lines[-max_lines:]]


def main() -> None:
    st.set_page_config(page_title="Swarm Versonalities v1 — Dashboard", layout="wide")
    st.title("Swarm Versonalities v1 — Dashboard")

    # ------------------------------------------------------------------
    # 1) Benchmark tasks and run coverage
    # ------------------------------------------------------------------
    st.header("1) Benchmark tasks and run coverage")
    tasks = _load_tasks()
    if not tasks:
        st.warning("No tasks_v1.json / benchmark_v1.json found or tasks list is empty.")
    else:
        rows = []
        for t in tasks:
            tid = t.get("id", "")
            bucket = t.get("task_bucket", "")
            prompt = t.get("prompt", "")
            run = _load_run_file(tid)
            has_run = run is not None
            run_success = None
            if run:
                metrics = run.get("metrics") or {}
                run_success = metrics.get("success")
            rows.append(
                {
                    "task_id": tid,
                    "task_bucket": bucket,
                    "has_run_file": has_run,
                    "run_success": run_success,
                    "prompt": prompt,
                }
            )
        st.caption(f"{len(tasks)} tasks in tasks_v1/benchmark_v1; {sum(1 for r in rows if r['has_run_file'])} have run outputs in runs/.")
        st.dataframe(rows, use_container_width=True, hide_index=True)

    # ------------------------------------------------------------------
    # 2) Aggregate metrics (summary_v1 + run summaries)
    # ------------------------------------------------------------------
    st.header("2) Aggregate metrics")

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Internal summary (results/summary_v1.json)")
        summary = _load_summary_v1()
        if not summary:
            st.caption("No results/summary_v1.json yet. Run batch_runner.py then aggregate_results.py.")
        else:
            st.json(summary)

    with c2:
        st.subheader("Run summary metrics (logs/runs.jsonl)")
        summaries = load_summaries()
        if not summaries:
            st.caption("No run summaries found in logs/runs.jsonl.")
        else:
            arms = ["monolith", "swarm"]
            table: List[Dict[str, Any]] = []
            for arm in arms:
                sr = success_rate(summaries=summaries, arm=arm)
                fps = first_pass_success(summaries=summaries, arm=arm)
                aq = average_quality(summaries=summaries, arm=arm)
                tps = tokens_per_success(summaries=summaries, arm=arm)
                cps = cost_per_success(summaries=summaries, arm=arm)
                tc = tool_correctness(summaries=summaries, arm=arm)
                pvr = policy_violation_rate(summaries=summaries, arm=arm)
                chr_ = critical_hallucination_rate(summaries=summaries, arm=arm)
                table.append(
                    {
                        "arm": arm,
                        "SR": f"{sr:.2%}",
                        "FPS": f"{fps:.2%}",
                        "Avg Quality": "—" if aq is None else f"{aq:.2f}",
                        "Tokens/Success": "—" if not tps else f"{tps:.0f}",
                        "Cost/Success": "—" if not cps else f"${cps:.6f}",
                        "Tool Correctness": f"{tc:.2%}",
                        "Policy Violation Rate": f"{pvr:.2%}",
                        "Critical Hallucination Rate": f"{chr_:.2%}",
                    }
                )
            st.dataframe(table, use_container_width=True, hide_index=True)

    # ------------------------------------------------------------------
    # 3) Evaluation artifact (where versonalities helped/hurt)
    # ------------------------------------------------------------------
    st.header("3) Evaluation artifact")
    artifact = _load_artifact()
    if not artifact:
        st.caption("No results/internal_evaluation.json yet. Run generate_evaluation_artifact.py after aggregate_results.py.")
    else:
        c3, c4 = st.columns(2)
        with c3:
            st.subheader("Structured artifact")
            st.json(artifact)
        with c4:
            st.subheader("Where versonalities helped / hurt")
            helped = artifact.get("where_versonalities_helped") or []
            hurt = artifact.get("where_versonalities_hurt") or []
            st.markdown(f"**Helped** ({len(helped)}):")
            if helped:
                st.table([{"task_id": x.get("task_id"), "task_bucket": x.get("task_bucket"), "reason": x.get("reason")} for x in helped])
            else:
                st.caption("No tasks where versonalities helped recorded.")
            st.markdown(f"**Hurt** ({len(hurt)}):")
            if hurt:
                st.table([{"task_id": x.get("task_id"), "task_bucket": x.get("task_bucket"), "reason": x.get("reason")} for x in hurt])
            else:
                st.caption("No tasks where versonalities hurt recorded.")

    # ------------------------------------------------------------------
    # 4) Moltbook posts (prompt + results)
    # ------------------------------------------------------------------
    st.header("4) Moltbook posts (prompt + results)")

    combined = _read_text(COMBINED_POST_PATH).strip()
    if combined:
        st.subheader("Combined post (canonical prompt + results)")
        st.caption(f"Source: {COMBINED_POST_PATH}")
        st.text_area("moltbook_combined_post.txt", value=combined, height=260)
    else:
        st.caption("No moltbook_combined_post.txt found. Run build_moltbook_post.py to generate it.")

    with st.expander("Launch and results posts (separate files)", expanded=False):
        launch = _read_text(LAUNCH_POST_PATH).strip()
        results_post = _read_text(RESULTS_POST_PATH).strip()
        st.markdown("**Launch post (moltbook_launch_post.txt)**")
        if launch:
            st.text_area("Launch post", value=launch, height=180, key="launch_post_view")
        else:
            st.caption("Launch post file not found.")
        st.markdown("**Results post (moltbook_results_post.txt)**")
        if results_post:
            st.text_area("Results post", value=results_post, height=180, key="results_post_view")
        else:
            st.caption("Results post file not found.")

    # ------------------------------------------------------------------
    # 5) Bintly orchestrator state and errors
    # ------------------------------------------------------------------
    st.header("5) Bintly orchestrator state")
    state = _load_json(BINTLY_STATE_PATH)
    if state:
        c5, c6 = st.columns(2)
        with c5:
            st.subheader("State")
            st.json(state)
        with c6:
            st.subheader("Recent errors (logs/bintly_errors.log)")
            lines = _tail_file(BINTLY_ERRORS_PATH, max_lines=50)
            if lines:
                st.text("\n".join(lines))
            else:
                st.caption("No bintly_errors.log found or file is empty.")
    else:
        st.caption("No .bintly_orchestrator_state.json found yet. Run bintly_orchestrator.py at least once.")

    # ------------------------------------------------------------------
    # 6) External reports
    # ------------------------------------------------------------------
    st.header("6) External reports")
    reports_obj = _load_json(EXTERNAL_REPORTS_PATH)
    if not reports_obj:
        st.caption("No external_reports.json found or file is empty.")
    else:
        if isinstance(reports_obj, list):
            st.caption(f"{len(reports_obj)} external reports normalized.")
            st.dataframe(reports_obj, use_container_width=True, hide_index=True)
        else:
            st.json(reports_obj)


if __name__ == "__main__":
    main()

