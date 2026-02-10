#!/usr/bin/env bash
# One-time baseline run, then build the canonical post (ready to publish).
# Does NOT publish to Moltbook (run bintly_orchestrator.py after this with MOLTBOOK_API_KEY).
# Requires: GROQ_API_KEY set.
set -e
cd "$(dirname "$0")"
echo "1/4 Running 12 tasks (monolith + swarm)..."
python batch_runner.py
echo "2/4 Aggregating results..."
python aggregate_results.py
echo "3/4 Generating evaluation artifact..."
python generate_evaluation_artifact.py
echo "4/4 Building Moltbook launch post (with findings)..."
python build_moltbook_post.py
echo "Done. Results: results/summary_v1.json, results/internal_evaluation.json"
echo "Launch post: moltbook_launch_post.txt"
echo "To publish: export MOLTBOOK_API_KEY=... && python bintly_orchestrator.py"
