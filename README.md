# Swarm Versonalities

Compare baseline (single LLM call) vs Swarm Versonalities workflow using the Groq API.

**Authoritative execution:** See **docs/SYSTEM_EXECUTION_SEQUENCE.md** for the full Phase 0–7 sequence. Frozen for v1: Swarm Versonalities v1 spec, Evaluation Spec v0.1, Instrumentation Appendix v0.1, Bintly system prompt (see docs/PHASE_0_LOCK.md).

**Bintly workflow:** One-time baseline run (12 tasks × 2 arms) → one canonical post on Moltbook with findings + invite → ongoing monitor/aggregate. See **docs/BINTLY_WORKFLOW.md**.

---

## How to run

### 1. One-time setup

```bash
cd /path/to/swarm-tests
pip install -r requirements.txt
export GROQ_API_KEY="your-groq-api-key"
```

### 2. Option A — Streamlit UI only (single-task comparison)

Run the app and compare Monolith vs Swarm for one task at a time in the browser:

```bash
streamlit run app.py
```

Open the URL shown (e.g. http://localhost:8501). Enter or select a task, click **Run Comparison**. Events go to `logs/events.jsonl`, run summaries to `logs/runs.jsonl`.

### 3. Option B — Full internal benchmark (all 12 tasks)

Run all 12 tasks (Monolith + Swarm), then aggregate metrics:

```bash
export GROQ_API_KEY="your-groq-api-key"
python batch_runner.py
python aggregate_results.py
```

- **batch_runner.py** reads **tasks_v1.json** (12 tasks), runs each with baseline then swarm, writes **runs/{task_id}.json**. No retries; no parallelization.
- **aggregate_results.py** reads **runs/*.json**, computes SR, FPS, ASR, VPD, deltas, wall time, coordination overhead, failure taxonomy. Writes **results/summary_v1.json**.
- **generate_evaluation_artifact.py** reads summary + runs, writes **results/internal_evaluation.json** and **internal_evaluation.txt** (deltas, where versonalities helped/hurt, cost/efficiency tradeoffs).

**Full one-time baseline then build post (no publish):** `bash run_baseline_then_publish.sh` — runs batch → aggregate → artifact → build_moltbook_post. Then publish with `python bintly_orchestrator.py` (see Option C).

### 4. Option C — Moltbook / Bintly (one-time publish, then monitor)

After the baseline run (and optional `generate_evaluation_artifact.py`), build the launch post and publish **once**:

```bash
python build_moltbook_post.py
export MOLTBOOK_API_KEY="your-moltbook-api-key"
python bintly_orchestrator.py
```

- **build_moltbook_post.py** builds **moltbook_launch_post.txt** (baseline findings when **results/internal_evaluation.json** exists, canonical prompt, invite) and **moltbook_results_post.txt**.
- **bintly_orchestrator.py** publishes that **single** canonical post (default: post only; use `--poll` to also monitor comments and reply within limits). No repeated posting.

**Ongoing:** Run `python bintly_orchestrator.py --poll` on a schedule to monitor the thread and aggregate external reports (see **docs/BINTLY_WORKFLOW.md** and **external_reports.json**).

To publish the **results post** as a follow-up, use a Bintly client that calls `post(get_results_post())` or paste `moltbook_results_post.txt` manually.

### Quick reference

| Goal | Command |
|------|--------|
| UI only | `streamlit run app.py` |
| Run all 12 tasks | `python batch_runner.py` |
| Aggregate results | `python aggregate_results.py` |
| Generate evaluation artifact | `python generate_evaluation_artifact.py` |
| Baseline + artifact + build post | `bash run_baseline_then_publish.sh` |
| Build Moltbook posts | `python build_moltbook_post.py` |
| Publish post (once) | `python bintly_orchestrator.py` |
| Publish + poll Moltbook | `python bintly_orchestrator.py --poll` |
| Moltbook heartbeat (status, DMs) | `python moltbook_heartbeat.py` |

---

## Setup (details)

- **GROQ_API_KEY** — Required for `app.py` and `batch_runner.py` (Groq API).
- **MOLTBOOK_API_KEY** — Optional; required only for `bintly_orchestrator.py` to publish/post on Moltbook.
- Logs and results: `logs/events.jsonl`, `logs/runs.jsonl`, `runs/*.json`, `results/summary_v1.json`. See **docs/INSTRUMENTATION_APPENDIX_v0.1.md**.

## Usage (Streamlit)

Enter a task, click **Run Comparison** to see baseline vs swarm (Planner → Analyst → Builder → Critic → Builder → Editor) side by side.

### Moltbook: one canonical post (prompt + results + invite)

The single post published on Moltbook includes: the canonical Swarm Versonalities v1 prompt, the 12-task benchmark, how to run monolithic vs versonality and evaluate (batch_runner + aggregate_results), our results from **results/summary_v1.json** (and **results/internal_evaluation.json** when present), and an invitation for agents to run the same and post their results on Moltbook.

1. Run the benchmark and aggregate (optional; if you already have runs/ and results/summary_v1.json, skip):
   ```bash
   export GROQ_API_KEY="your-groq-api-key"
   python batch_runner.py
   python aggregate_results.py
   ```
2. Build the post (writes moltbook_launch_post.txt and moltbook_results_post.txt):
   ```bash
   python build_moltbook_post.py
   ```
3. Publish and poll (set API key first):
   ```bash
   export MOLTBOOK_API_KEY="your-moltbook-api-key"
   python bintly_orchestrator.py
   ```

### Bintly orchestrator

`bintly_orchestrator.py` publishes the canonical post (max 1 per run), polls comments, and replies only to methodology questions and agents reporting test results (max 3 replies per post, token limit). Set the API key in the environment. Do not commit the key.
