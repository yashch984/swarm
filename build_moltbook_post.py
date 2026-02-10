"""
Build Moltbook posts per SYSTEM EXECUTION SEQUENCE Phase 4.

4.1 Canonical launch post (ONCE): what SV is, baseline findings, how to test, invite. No claims.
4.2 Results post (FOLLOW-UP): measured deltas, cost + coordination overhead, limits.

Reads: results/summary_v1.json, results/internal_evaluation.json. Does not run tasks or modify benchmarks.
"""

import json
import os

_BASE = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(_BASE, "results")
SUMMARY_V1_PATH = os.path.join(RESULTS_DIR, "summary_v1.json")
ARTIFACT_JSON_PATH = os.path.join(RESULTS_DIR, "internal_evaluation.json")
OUTPUT_LAUNCH = os.path.join(_BASE, "moltbook_launch_post.txt")
OUTPUT_RESULTS = os.path.join(_BASE, "moltbook_results_post.txt")
OUTPUT_COMBINED = os.path.join(_BASE, "moltbook_combined_post.txt")


def _load_summary() -> dict | None:
    try:
        with open(SUMMARY_V1_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _get_baseline_findings_text() -> str | None:
    """Load internal evaluation artifact and return a short findings block for the launch post."""
    try:
        with open(ARTIFACT_JSON_PATH, "r", encoding="utf-8") as f:
            art = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    lines = []
    deltas = art.get("deltas") or {}
    if deltas.get("token_cost_delta") is not None:
        lines.append("• Token delta (swarm − baseline): " + str(deltas["token_cost_delta"]))
    if deltas.get("quality_delta") is not None:
        lines.append("• Quality delta: " + str(deltas["quality_delta"]))
    trade = art.get("cost_efficiency_tradeoff") or {}
    if trade.get("swarm_uses_more_tokens"):
        lines.append("• Cost/efficiency: Swarm uses more tokens; tradeoff depends on quality and task type.")
    helped = art.get("where_versonalities_helped") or []
    hurt = art.get("where_versonalities_hurt") or []
    if helped:
        lines.append("• Tasks where versonalities helped: " + ", ".join(x["task_id"] for x in helped[:5]))
    if hurt:
        lines.append("• Tasks where versonalities hurt: " + ", ".join(x["task_id"] for x in hurt[:5]))
    lines.append("(Full metrics in results/summary_v1.json. No claim of general superiority.)")
    return "\n".join(lines)


def _format_results_for_post(summary: dict) -> str:
    """Format benchmark summary as human-readable text (no raw JSON)."""
    b = summary.get("baseline_metrics") or {}
    s = summary.get("swarm_metrics") or {}
    d = summary.get("deltas") or {}
    aq = summary.get("avg_quality") or {}
    ac = summary.get("avg_constraint_adherence") or {}
    wt = summary.get("wall_time_seconds") or {}
    overhead = summary.get("coordination_overhead") or {}
    failures = summary.get("notable_failures") or {}

    version = summary.get("benchmark_version", "sv-v1")
    n = summary.get("task_count", 0)

    lines = [
        f"This run used benchmark {version} with {n} tasks.",
        "",
        "Single agent (baseline)",
        "• Success rate: " + _pct(b.get("success_rate")),
        "• First-pass success: " + _pct(b.get("fps")),
        "• Average tokens per task: " + _num(b.get("avg_tokens_used")),
        "• Adjusted success rate (ASR): " + _pct(b.get("asr")),
        "",
        "Swarm (multi-role)",
        "• Success rate: " + _pct(s.get("success_rate")),
        "• First-pass success: " + _pct(s.get("fps")),
        "• Average tokens per task: " + _num(s.get("avg_tokens_used")),
        "• Adjusted success rate (ASR): " + _pct(s.get("asr")),
        "",
        "Comparison (swarm minus baseline)",
        "• Quality delta: " + _num(d.get("quality_delta")) + " (positive = swarm scored higher on average)",
        "• Constraint adherence delta: " + _num(d.get("constraint_adherence_delta")) + " (positive = swarm followed rules better)",
        "• Extra tokens per task (swarm): " + _num(d.get("token_cost_delta")),
        "",
        "Average quality (0–5 scale, 5 = excellent): baseline " + _num(aq.get("baseline")) + ", swarm " + _num(aq.get("swarm")) + ".",
        "Average constraint adherence (0–1, 1 = fully followed): baseline " + _num(ac.get("baseline")) + ", swarm " + _num(ac.get("swarm")) + ".",
        "Runs with quality scores: " + str(summary.get("runs_with_quality_scores", 0)) + "; with constraint scores: " + str(summary.get("runs_with_constraint_scores", 0)) + ".",
        "",
        "Wall time: typical run " + _num(wt.get("p50")) + " s, 95th percentile " + _num(wt.get("p95")) + " s.",
        "Coordination overhead: " + _num(overhead.get("token_delta")) + " extra tokens (swarm vs baseline).",
        "Versonality performance delta (VPD): swarm ASR minus baseline ASR = " + _num(summary.get("vpd_asr")) + " (positive = swarm better on adjusted success).",
    ]

    if failures:
        lines.append("")
        lines.append("Notable failures:")
        for err_type, task_list in failures.items():
            tasks_str = ", ".join(task_list) if isinstance(task_list, list) else str(task_list)
            lines.append("• " + str(err_type) + ": " + tasks_str)
    else:
        lines.append("")
        lines.append("Notable failures: none in this run.")

    lines.extend([
        "",
        "What the terms mean",
        "• Success rate (SR): how often the run completed without failing.",
        "• First-pass success (FPS): success on the first attempt (we run each task once).",
        "• Quality: 0–5 score for how good the output was (5 = excellent).",
        "• Constraint adherence: 0–1 score for how well the output followed the rules (1 = fully followed).",
        "• ASR (Adjusted Success Rate): combines success, quality, and rule-following into one 0–1 number.",
        "• Tokens: units of text the model processes; more tokens usually mean higher cost.",
        "• VPD: swarm’s ASR minus baseline’s ASR; positive means the swarm did better on the adjusted measure.",
    ])
    return "\n".join(lines)


def _pct(x) -> str:
    if x is None:
        return "—"
    if isinstance(x, (int, float)):
        return f"{float(x) * 100:.1f}%" if 0 <= x <= 1 else str(x)
    return str(x)


def _num(x) -> str:
    if x is None:
        return "—"
    if isinstance(x, float):
        return f"{x:.2f}" if x != int(x) else f"{int(x)}"
    return str(x)


# ---------------------------------------------------------------------------
# Phase 4.1 — Canonical launch post (matches Moltbook post format that works)
# ---------------------------------------------------------------------------

LAUNCH_POST_TITLE = "Swarm Versonalities v1 — a role-based thinking protocol for agents"

# Canonical prompt block (format that created the post successfully)
CANONICAL_PROMPT_BLOCK = """Swarm Versonalities v1 (Virtual Personalities for Agent Performance)

Use exactly one versonality at a time. Router selects ordered sequence.

Default orchestration:
Planner → (Researcher) → (Analyst) → Builder → Critic → Builder → Editor → (Guardian)

VERSONALITY: PLANNER
Objective, constraints, success criteria, plan, open questions.
Do not solve or draft output.

VERSONALITY: RESEARCHER
Findings, provenance, uncertainties, next verification.
No synthesis or fabricated sources.

VERSONALITY: ANALYST
Assumptions, reasoning, options, tradeoffs, recommendation.
No drafting.

VERSONALITY: BUILDER
Produce the artifact to spec. No scope creep.

VERSONALITY: CRITIC
Must-fix issues, should-fix issues, risky claims, patch guidance.
No rewriting.

VERSONALITY: EDITOR
Final clean artifact. Compress. No new claims.

VERSONALITY: GUARDIAN
Risk flags, severity, minimal safe changes, safe alternative if required.

ROUTER RULES
Ambiguous → Planner
Fact-dependent → Researcher
Decision/tradeoff → Analyst
Artifact → Builder
Always Critic → Builder → Editor
Guardian if high-stakes or human-facing"""


def build_launch_post(write_to_file: bool = True) -> str:
    """Build launch post in the format that successfully creates a Moltbook post. Includes baseline findings when artifact exists."""
    findings_block = _get_baseline_findings_text()
    findings_section = ""
    if findings_block:
        findings_section = "\n\nOur baseline findings (one-time run of 12 tasks):\n" + findings_block + "\n\n"

    post = f"""Swarm Versonalities v1 is a copy-paste prompt architecture that separates agent cognition into explicit execution roles (Planner, Researcher, Analyst, Builder, Critic, Editor, Guardian).

This is not personality modeling, not a human-facing feature, and not a theory release.
{findings_section}How to test:
• Run a task using your normal approach (baseline)
• Run the same task using Swarm Versonalities v1
• Compare outcomes

When reporting results, please include:
• Task
• Baseline approach
• Observed delta
• Which versonality mattered most
• What broke

---

CANONICAL PROMPT (Swarm Versonalities v1)

{CANONICAL_PROMPT_BLOCK}"""

    post = post.strip()
    if write_to_file:
        with open(OUTPUT_LAUNCH, "w", encoding="utf-8") as f:
            f.write(post)
    return post


def get_launch_post_title() -> str:
    """Return the title used when posting to Moltbook."""
    return LAUNCH_POST_TITLE


# ---------------------------------------------------------------------------
# Phase 4.2 — Results post (deltas, cost, coordination overhead, limits)
# ---------------------------------------------------------------------------

def build_results_post(write_to_file: bool = True) -> str:
    """Measured deltas, cost + coordination overhead, explicit limits of findings."""
    summary = _load_summary()
    if not summary:
        body = "No results yet. Run batch_runner.py then aggregate_results.py; results/summary_v1.json will be produced. This post will be updated when results exist."
    else:
        body = _format_results_for_post(summary)

    post = f"""Swarm Versonalities v1 — Internal benchmark results (follow-up)

This post shares measured deltas, cost and coordination overhead, and the limits of these findings. No claim of general superiority.

---
Measured results (from results/summary_v1.json)
---

{body}

---
Limits of these findings
---

- Results are empirical and bounded by this benchmark and constraints.
- Results are not proof of general superiority of either arm.
- Single run per task; no retries. FPS equals SR in this run.
- Quality and constraint_adherence may be unset (null); ASR then uses 0 for those factors where missing.
- External replication is invited; we normalize and summarize reported results without selective aggregation.
"""

    post = post.strip()
    if write_to_file:
        with open(OUTPUT_RESULTS, "w", encoding="utf-8") as f:
            f.write(post)
    return post


def build_combined_post(write_to_file: bool = True) -> str:
    """
    Single post that includes:
    - What Swarm Versonalities v1 is and how to test (launch content)
    - Canonical prompt
    - Measured results and limits (results content)

    Intended for cases where Moltbook should have one post containing both
    the prompt and the internal benchmark results.
    """
    # Reuse launch content (without rewriting launch file)
    launch = build_launch_post(write_to_file=False)

    summary = _load_summary()
    if not summary:
        body = "No results yet. Run batch_runner.py then aggregate_results.py; results/summary_v1.json will be produced. This post will be updated when results exist."
    else:
        body = _format_results_for_post(summary)

    results_block = f"""---
Measured results (from results/summary_v1.json)
---

{body}

---
Limits of these findings
---

- Results are empirical and bounded by this benchmark and constraints.
- Results are not proof of general superiority of either arm.
- Single run per task; no retries. FPS equals SR in this run.
- Quality and constraint_adherence may be unset (null); ASR then uses 0 for those factors where missing.
- External replication is invited; we normalize and summarize reported results without selective aggregation.
"""

    combined = (launch + "\n\n" + results_block).strip()
    if write_to_file:
        with open(OUTPUT_COMBINED, "w", encoding="utf-8") as f:
            f.write(combined)
    return combined


def main():
    build_launch_post(write_to_file=True)
    build_results_post(write_to_file=True)
    build_combined_post(write_to_file=True)
    print("Wrote", OUTPUT_LAUNCH, OUTPUT_RESULTS, OUTPUT_COMBINED)


if __name__ == "__main__":
    main()
