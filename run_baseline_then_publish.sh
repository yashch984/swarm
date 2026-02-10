#!/usr/bin/env bash
# One-time baseline run, then build the canonical post (ready to publish).
# Does NOT publish to Moltbook (run bintly_orchestrator.py after this with MOLTBOOK_API_KEY).
# Requires: GROQ_API_KEY set.
set -e
cd "$(dirname "$0")"
echo "1/5 Running 12 tasks (monolith + swarm)..."
python batch_runner.py
echo "2/5 Evaluating quality and constraint adherence (for ASR)..."
python evaluate_quality.py
echo "3/5 Aggregating results..."
python aggregate_results.py
echo "4/5 Generating evaluation artifact..."
python generate_evaluation_artifact.py
echo "5/5 Building Moltbook launch post (with findings)..."
python build_moltbook_post.py
echo "Done. Results: results/summary_v1.json, results/internal_evaluation.json"
echo "Launch post: moltbook_launch_post.txt"
echo "To publish: export MOLTBOOK_API_KEY=... && python bintly_orchestrator.py"
