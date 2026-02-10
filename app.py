"""
Research UI: controlled experiment Monolith vs Swarm.
Run tasks, show outputs, record human evaluation, display logged results.
No dashboards, charts, auth, or automation.
"""

import json
import os
import time
import uuid
from typing import Optional, Tuple

import streamlit as st

from run_logging import FailureReason, RUNS_PATH, log_event, write_run_summary
from metrics import load_summaries, success_rate, tokens_per_success, cost_per_success
from pipeline import SWARM_ROLES, cost_usd, run_baseline, run_swarm

TASK_BUCKETS = [
    "single-step",
    "multi-step",
    "tool-heavy",
    "high-ambiguity",
    "verification-heavy",
    "creative-but-constrained",
]

FAILURE_REASONS = [e.value for e in FailureReason]


def avg_quality(summaries, arm):
    subset = [s for s in summaries if s.get("arm") == arm]
    vals = [s.get("scores", {}).get("quality") for s in subset if s.get("scores", {}).get("quality") is not None]
    return sum(vals) / len(vals) if vals else None


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Swarm experiment — Monolith vs Swarm", layout="wide")

st.title("Swarm experiment — Monolith vs Swarm")

# 1) Task Input Section
st.header("1) Task Input")
task = st.text_area("Task prompt", height=120, placeholder="Enter task...")
task_bucket = st.selectbox("Task bucket", TASK_BUCKETS, index=0)
run_clicked = st.button("Run Experiment")

if run_clicked:
    if not (task or "").strip():
        st.error("Enter a task.")
    else:
        run_id = str(uuid.uuid4())
        task_id = str(uuid.uuid4())
        bucket = task_bucket.strip() or "single-step"

        col1, col2 = st.columns(2)
        with col1:
            with st.spinner("Monolith..."):
                t0 = time.perf_counter()
                monolith_out, mi_in, mi_out = run_baseline(task, run_id, task_id, bucket)
                monolith_time = time.perf_counter() - t0
        with col2:
            with st.spinner("Swarm..."):
                t0 = time.perf_counter()
                swarm_out, si_in, si_out = run_swarm(task, run_id, task_id, bucket)
                swarm_time = time.perf_counter() - t0

        st.session_state["last_run"] = {
            "run_id": run_id,
            "task_id": task_id,
            "task_bucket": bucket,
            "monolith_output": monolith_out,
            "swarm_output": swarm_out,
            "monolith_tokens_in": mi_in,
            "monolith_tokens_out": mi_out,
            "swarm_tokens_in": si_in,
            "swarm_tokens_out": si_out,
            "monolith_time_s": monolith_time,
            "swarm_time_s": swarm_time,
        }

# 2) Output Comparison Section
st.header("2) Output Comparison")
if st.session_state.get("last_run"):
    r = st.session_state["last_run"]
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Monolith")
        st.text_area("", value=r["monolith_output"], height=280, disabled=True, label_visibility="collapsed")
        st.caption(f"Tokens in: {r['monolith_tokens_in']} | out: {r['monolith_tokens_out']} | cost: ${cost_usd(r['monolith_tokens_in'], r['monolith_tokens_out']):.6f} | time: {r['monolith_time_s']:.2f}s")
    with c2:
        st.subheader("Swarm")
        st.text_area("", value=r["swarm_output"], height=280, disabled=True, label_visibility="collapsed")
        st.caption(f"Tokens in: {r['swarm_tokens_in']} | out: {r['swarm_tokens_out']} | cost: ${cost_usd(r['swarm_tokens_in'], r['swarm_tokens_out']):.6f} | time: {r['swarm_time_s']:.2f}s")
else:
    st.caption("Run an experiment to see outputs.")

# 3) Human Evaluation Section
st.header("3) Human Evaluation")
if st.session_state.get("last_run"):
    r = st.session_state["last_run"]
    st.caption("Rate and finalize this run (one evaluation per arm).")
    ev1, ev2 = st.columns(2)
    with ev1:
        st.markdown("**Monolith**")
        quality_mono = st.slider("Quality (0–5) — Monolith", 0.0, 5.0, 2.5, 0.5, key="q_mono")
        success_mono = st.checkbox("Success", value=True, key="s_mono")
        failure_mono = None
        if not success_mono:
            failure_mono = st.selectbox("Failure reason", FAILURE_REASONS, key="f_mono")
    with ev2:
        st.markdown("**Swarm**")
        quality_swarm = st.slider("Quality (0–5) — Swarm", 0.0, 5.0, 2.5, 0.5, key="q_swarm")
        success_swarm = st.checkbox("Success", value=True, key="s_swarm")
        failure_swarm = None
        if not success_swarm:
            failure_swarm = st.selectbox("Failure reason", FAILURE_REASONS, key="f_swarm")

    if st.button("Finalize Run"):
        if (not success_mono and failure_mono is None) or (not success_swarm and failure_swarm is None):
            st.error("Set failure reason for any failed arm.")
        else:
            def to_enum(s):
                return FailureReason(s) if s else None
            # Derive simple policy / hallucination flags from failure_reason when present
            def flags(fr: Optional[FailureReason]) -> Tuple[bool, bool]:
                if fr is None:
                    return False, False
                if fr == FailureReason.HALLUCINATION:
                    return False, True
                if fr == FailureReason.CONSTRAINT_BREAK:
                    return True, False
                return False, False

            pv_mono, hc_mono = flags(to_enum(failure_mono))
            pv_swarm, hc_swarm = flags(to_enum(failure_swarm))

            write_run_summary(
                run_id=r["run_id"], task_id=r["task_id"], arm="monolith", task_bucket=r["task_bucket"],
                n_agents=1, success=success_mono, failure_reason=to_enum(failure_mono), quality=quality_mono,
                tokens_in=r["monolith_tokens_in"], tokens_out=r["monolith_tokens_out"],
                cost_usd=cost_usd(r["monolith_tokens_in"], r["monolith_tokens_out"]), retry_count=0,
                wall_seconds=r["monolith_time_s"], policy_violation=pv_mono, hallucination_critical=hc_mono,
                path=RUNS_PATH,
            )
            write_run_summary(
                run_id=r["run_id"], task_id=r["task_id"], arm="swarm", task_bucket=r["task_bucket"],
                n_agents=len(SWARM_ROLES), success=success_swarm, failure_reason=to_enum(failure_swarm), quality=quality_swarm,
                tokens_in=r["swarm_tokens_in"], tokens_out=r["swarm_tokens_out"],
                cost_usd=cost_usd(r["swarm_tokens_in"], r["swarm_tokens_out"]), retry_count=0,
                wall_seconds=r["swarm_time_s"], policy_violation=pv_swarm, hallucination_critical=hc_swarm,
                path=RUNS_PATH,
            )
            st.success("Run written to runs.jsonl.")
else:
    st.caption("Run an experiment to evaluate.")

# 4) Results Table Section
st.header("4) Results Table")
runs_path = RUNS_PATH
if os.path.isfile(runs_path):
    rows = []
    with open(runs_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    if rows:
        table_data = []
        for s in rows:
            o = s.get("outcome", {})
            u = s.get("usage", {})
            c = s.get("cost_usd", {})
            sc = s.get("scores", {})
            table_data.append({
                "run_id": s.get("run_id", ""),
                "task_bucket": s.get("task_bucket", ""),
                "arm": s.get("arm", ""),
                "outcome.success": o.get("success"),
                "scores.quality": sc.get("quality"),
                "usage.tokens_in": u.get("tokens_in"),
                "cost_usd.total": c.get("total"),
                "outcome.failure_reason": o.get("failure_reason"),
            })
        st.dataframe(table_data, use_container_width=True, hide_index=True)
    else:
        st.caption("No runs yet.")
else:
    st.caption("No runs.jsonl yet. Finalize a run to create it.")

# 5) Aggregate Summary Section
st.header("5) Aggregate Summary")
summaries = load_summaries(runs_path)
if summaries:
    arms = ["monolith", "swarm"]
    agg = []
    for arm in arms:
        sr = success_rate(summaries=summaries, arm=arm)
        aq = avg_quality(summaries, arm)
        tps = tokens_per_success(summaries=summaries, arm=arm)
        cps = cost_per_success(summaries=summaries, arm=arm)
        agg.append({
            "arm": arm,
            "Success Rate": f"{sr:.2%}" if sr is not None else "—",
            "Avg Quality": f"{aq:.2f}" if aq is not None else "—",
            "Tokens per Success": f"{tps:.0f}" if tps else "—",
            "Cost per Success": f"${cps:.6f}" if cps else "—",
        })
    st.dataframe(agg, use_container_width=True, hide_index=True)
else:
    st.caption("No data. Finalize runs to see aggregates.")
