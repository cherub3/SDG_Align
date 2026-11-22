#!/usr/bin/env bash
# Rebuild stages 4-9 from raw extraction and evaluate. Usage: tools/rebuild_and_eval.sh <label> <split> [ENV=VAL ...]
# Needs requirements-local.txt. Refuses (via eval_retrieval) if the clean text hashes changed.
set -e
LABEL=$1; SPLIT=$2; shift 2
export HF_HUB_OFFLINE=1 EMBEDDING_PROVIDER=local "$@"
PY=${PY:-python}
$PY tools/reset_for_rerun.py > /dev/null
for s in stage4_cleaning stage5_structure stage6_validation stage7_chunking stage8_embedding_generation stage9_vector_indexing; do
  $PY -m scripts.$s 2>&1 | grep -E "^\[stage[0-9]+\] attempted" || true
done
$PY tools/eval_retrieval.py --split "$SPLIT" --label "$LABEL" --out "eval/results/${LABEL}.json" 2>&1 | grep -v "faiss\|Loading\|Module"
