#!/bin/bash
# NeuroForge OS — Batch Pipeline Runner
# Runs all remaining topics in sequence

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/.."

run_topic() {
    local topic="$1"
    local faculty="$2"
    echo ""
    echo "========================================"
    echo "  STARTING: $topic ($faculty)"
    echo "  $(date)"
    echo "========================================"
    python scripts/neuroforge_pipeline.py \
        --topic "$topic" \
        --faculty "$faculty" \
        --mode full
    echo ""
    echo "  FINISHED: $topic — $(date)"
    echo "========================================"
}

# Remaining 8 topics from the roadmap (Dopamine Detox running separately)
run_topic "Stop Procrastinating" "Kai Ren"
run_topic "The Confidence Code" "Luna Hart"
run_topic "Beat Phone Addiction" "Kai Ren"
run_topic "Stop Negative Thoughts" "Dr. Nova Vale"
run_topic "How to Read People" "Luna Hart"
run_topic "The Discipline Blueprint" "Marcus Voss"
run_topic "The Charisma Blueprint" "Luna Hart"
run_topic "Beat Anxiety Fast" "Dr. Nova Vale"

# Easter special topic
run_topic "The Rebirth Blueprint" "Dr. Nova Vale"

echo ""
echo "========================================"
echo "  ALL TOPICS COMPLETE — $(date)"
echo "========================================"
echo ""
cat ../neuroforge_db.json | python3 -c "
import json, sys
db = json.load(sys.stdin)
topics = {}
for r in db:
    t = r['topic']
    if t not in topics:
        topics[t] = []
    if r['qa_score']:
        topics[t].append(r['qa_score'])
print('TOPIC SUMMARY:')
print('-' * 50)
for t, scores in topics.items():
    avg = sum(scores) // len(scores) if scores else 0
    print(f'  {t:<30} avg: {avg}/50 ({len(scores)} agents)')
print('-' * 50)
"
