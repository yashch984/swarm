# Dashboard Guide — What You're Looking At (Plain Language)

This document explains everything you see on the **Swarm Versonalities v1 Dashboard** in simple terms, so you can understand and explain the results to stakeholders without technical jargon.

---

## What This Project Measures

We compare two ways of using the same AI model to do tasks:

1. **Single agent (Monolith)** — One AI call per task; straightforward, fast, low cost.
2. **Swarm (Multiple roles)** — The same task is handled by a fixed sequence of roles (Planner → Analyst → Builder → Critic → Builder → Editor). More steps, more tokens, potentially better quality or worse depending on the task.

The dashboard shows how many tasks we ran, how each approach performed, where the swarm helped or hurt, and what we published publicly.

---

## Section 1: Benchmark Tasks and Run Coverage

### What you see

A table listing every task in the benchmark, with:

- **task_id** — Short ID for the task (e.g. t01, t02).
- **task_bucket** — Category of the task (e.g. single-step, multi-step, high-ambiguity).
- **has_run_file** — Whether we have run results for this task (True/False).
- **run_success** — Whether that run completed without errors (True/False).
- **prompt** — The exact instruction given to the AI for this task.

### What it means in plain language

- **“Benchmark”** = the fixed set of tasks we use so we can compare runs over time.
- **“Run coverage”** = how many of those tasks have been executed and saved. If all show **has_run_file: True**, the full benchmark has been run.
- **run_success** tells you if that task run finished successfully (no crash, no timeout). It does **not** mean the answer was correct; that is reflected later in quality and success-rate metrics.

### What to tell the client

> “This table is our task list. Each row is one task we ran. We check that every task has been run and whether that run completed. This is our baseline for comparing the single-agent vs swarm approach.”

---

## Section 2: Aggregate Metrics

This section has two parts: **Internal summary** (from the main benchmark) and **Run summary metrics** (from detailed run logs). Both compare the two approaches side by side.

### Internal summary (left side)

This is the main benchmark summary. It compares **Monolith** (single agent) vs **Swarm** (multi-role) across all tasks.

#### Numbers you’ll see (and what they mean)

- **benchmark_version** — Which version of the task set we used (e.g. sv-v1). Lets us keep results comparable over time.
- **task_count** — How many tasks were included (e.g. 12).

**Baseline (Monolith) and Swarm metrics:**

- **success_rate** — Percentage of tasks where that approach produced an output without failing. 1.0 = 100% (every task completed).
- **fps (First-Pass Success)** — Same as success rate here (we run each task once, no retries).
- **avg_tokens_used** — On average, how many tokens (pieces of text) the AI used per run. Higher = more “work” and usually more cost.
- **asr (Adjusted Success Rate)** — A single number that combines:
  - Did the run succeed?
  - How good was the output (quality 0–5)?
  - Did the output follow the rules (constraint adherence 0–1)?  
  So ASR answers: “How often did we get a good, rule-following result?” (0 = never, 1 = always).

**Deltas (Swarm minus Monolith):**

- **quality_delta** — How much better (or worse) the swarm’s average quality score was compared to the single agent. Positive = swarm scored higher on average.
- **constraint_adherence_delta** — How much more (or less) the swarm followed the rules on average. Positive = swarm followed constraints better.
- **token_cost_delta** — How many more tokens the swarm used on average per task. Positive = swarm uses more tokens (and usually more cost).

**Averages for interpretation:**

- **avg_quality (baseline, swarm)** — Average quality score (0–5) for each approach. Lets you see if one side is consistently higher.
- **avg_constraint_adherence (baseline, swarm)** — Average “followed the rules” score (0–1) for each approach.
- **runs_with_quality_scores** / **runs_with_constraint_scores** — How many runs had quality and constraint scores. If these are lower than task count, some runs weren’t scored (e.g. evaluation step skipped).

**Time and cost:**

- **wall_time_seconds (p50, p95)** — How long the full run took in real time: p50 = typical run, p95 = one of the slower runs. Helps understand responsiveness.
- **coordination_overhead** — Extra tokens (and often cost) from using the swarm instead of a single call (e.g. token_delta).
- **vpd_asr** — “Versonality Performance Delta”: swarm’s ASR minus baseline’s ASR. Positive = swarm did better on the adjusted success measure; negative = single agent did better.
- **notable_failures** — If any tasks failed with a known reason (e.g. timeout, API error), they’re grouped here by error type and task.

### Run summary metrics (right side)

This table is built from the same runs but from the detailed run log. It shows one row per **approach** (monolith, swarm) with:

- **arm** — Which approach (monolith or swarm).
- **SR** — Success rate (same idea as above).
- **FPS** — First-pass success (same as SR in our setup).
- **Avg Quality** — Average quality score (0–5) when we have scores.
- **Tokens/Success** — Average tokens used on runs that succeeded.
- **Cost/Success** — Average cost per successful run (when we have cost data).
- **Tool Correctness** — When tools are used, how often they were used correctly (0–100%). If no tools, this stays 0%.
- **Policy Violation Rate** — How often an output broke policy rules (0–100%).
- **Critical Hallucination Rate** — How often we flagged a serious hallucination (0–100%).

### What to tell the client

> “This section is the main comparison. We see how often each approach succeeded, how good the outputs were, and how well they followed the rules. We also see how much extra time and tokens the swarm used. The ‘deltas’ tell us whether the swarm was better or worse than the single agent on average, and the ‘notable failures’ show any systematic problems.”

---

## Section 3: Evaluation Artifact — Where Versonalities Helped or Hurt

### What you see

- **Structured artifact** — The full internal evaluation as a JSON blob (for reference or export).
- **Where versonalities helped / hurt** — Two tables:
  - **Helped** — Tasks where the swarm did better (e.g. swarm succeeded when baseline failed, or swarm used fewer tokens with same success).
  - **Hurt** — Tasks where the swarm did worse (e.g. baseline succeeded but swarm failed, or swarm used many more tokens).

Each row has **task_id**, **task_bucket**, and **reason** (short explanation like “swarm_more_tokens” or “baseline_success_swarm_failed”).

### What it means in plain language

- This is a **task-by-task** view: not just averages, but “on which tasks did the swarm help, and on which did it hurt?”
- **Helped** = swarm was the better choice for that task (by success and/or efficiency).
- **Hurt** = single agent was the better choice for that task.
- **Neutral** (if shown) = no clear winner (e.g. same success, similar tokens).

### What to tell the client

> “Here we break down results by task. We list exactly which tasks benefited from the multi-role approach and which ones were better with the single agent. That tells us where the swarm is worth the extra cost and where it isn’t.”

---

## Section 4: Moltbook Posts (Prompt + Results)

### What you see

- **Combined post** — The full text of the single post we publish: it includes the canonical prompt (how to run Swarm Versonalities), how to run the benchmark, our results summary, and an invitation for others to run the same and report back.
- An expandable area with **Launch post** and **Results post** as separate texts (same content split into two files, for reference).

### What it means in plain language

- **Moltbook** is the platform where we publish this one post.
- The **combined post** is what the public sees: the method, the numbers we got, and the ask (run the same 12 tasks and share results).
- No claims of superiority — we state what we measured and invite replication.

### What to tell the client

> “This is the exact text we publish. It explains the method, shows our benchmark results in plain form, and invites others to run the same test. Everything we claim in public is visible here.”

---

## Section 5: Bintly Orchestrator State and Errors

### What you see

- **State** — A small JSON that tracks how many posts we’ve published this run and how many replies we’ve sent (so we don’t exceed limits).
- **Recent errors** — The last lines from the error log (e.g. API failures, timeouts) when posting or replying.

### What it means in plain language

- **Bintly** is the process that publishes the post and (optionally) replies to comments under rules (e.g. one post per run, limited replies).
- **State** = “where we are” in those limits.
- **Recent errors** = what went wrong lately (e.g. “couldn’t publish because of X”). Useful for support or debugging.

### What to tell the client

> “This section is for operations: it shows that we’re respecting the posting and reply limits, and surfaces any recent errors when publishing or replying, so we can fix them.”

---

## Section 6: External Reports

### What you see

- If we have **external_reports.json**, the dashboard shows how many reports we have and a table (or JSON) of those reports.
- If the file is missing or empty, it says so.

### What it means in plain language

- When other people (or agents) run the same benchmark and report results, we can normalize and store them here.
- **External reports** = “other people’s results” that we aggregate without cherry-picking.

### What to tell the client

> “When others run the same 12 tasks and send us their results, we store them here. This is where we’d see community or partner replications of our benchmark.”

---

## One-Page Summary for the Client

| Dashboard section | In one sentence |
|-------------------|------------------|
| **1. Benchmark tasks and run coverage** | Shows the list of tasks we run and whether each has been executed and completed. |
| **2. Aggregate metrics** | Compares single-agent vs swarm on success, quality, rule-following, tokens, and cost; includes deltas and any notable failures. |
| **3. Evaluation artifact** | Lists which tasks the swarm helped on and which it hurt on, so we know where it’s worth the extra cost. |
| **4. Moltbook posts** | Shows the exact public post (prompt + results + invite) we publish. |
| **5. Bintly orchestrator state** | Shows posting/reply limits and recent errors for publishing and comments. |
| **6. External reports** | Shows how many external replications we have and their normalized data. |

---

## Glossary (for client conversations)

- **Benchmark** — The fixed set of tasks we use to compare approaches.
- **Monolith / Baseline** — Single AI call per task.
- **Swarm** — Multi-role sequence (Planner → … → Editor) for the same task.
- **Success rate** — % of tasks that completed without failure.
- **Quality (0–5)** — Score for how good the output was (5 = excellent).
- **Constraint adherence (0–1)** — Score for how well the output followed the rules (1 = fully followed).
- **ASR (Adjusted Success Rate)** — Single number combining success, quality, and rule-following (0–1).
- **Tokens** — Units of text the model processes; more tokens usually means more cost.
- **Delta** — Difference (Swarm minus Monolith); positive often means “swarm did more / better” for that metric.
- **VPD (ASR delta)** — How much better (or worse) the swarm’s ASR was compared to the single agent.
- **Moltbook** — The platform where we publish the one canonical post.
- **Bintly** — The automated process that publishes that post and optionally replies within limits.
