"""Phase 3 step 5 diagnosis: send the REAL planner prompt for up to 3 DEV questions to the live planner and save the RAW output.
Never touches TEST. Never prints the key. Usage: python tools/planner_probe.py --qids Q001,Q032,Q048 --out eval/results/planner_probe_dev.json
"""
import argparse, json, os, sys
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO); sys.path.insert(0, os.path.join(REPO, "tools"))
from google import genai
from google.genai import types
from tools_env import gemini_key
from scripts import planner_provider_gemini as ppg
from scripts.stage21_agent_planning import build_initial_context, build_planner_prompt, AgentDependencies

ap = argparse.ArgumentParser(); ap.add_argument("--qids", required=True); ap.add_argument("--out", required=True)
ap.add_argument("--model", default="gemini-3.5-flash-lite")
a = ap.parse_args()
qids = a.qids.split(",")
assert len(qids) <= 3, "time-boxed: at most 3 live calls"
split = json.load(open(os.path.join(REPO, "eval", "gold_split.json")))
dev = {k for k, v in split["split"].items() if v == "dev"}
items = {r["qid"]: r for r in (json.loads(x) for x in open(os.path.join(REPO, "eval", "gold_set.jsonl"), encoding="utf-8") if x.strip())}
client = genai.Client(api_key=gemini_key())
out = []
for q in qids:
    assert q in dev, f"{q} is not a DEV item"
    deps = AgentDependencies.__new__(AgentDependencies); deps.tool_registry = None
    ctx = build_initial_context({"query": items[q]["question"]}, deps)
    prompt = build_planner_prompt(ctx)
    cfg = types.GenerateContentConfig(system_instruction=ppg.SYSTEM_INSTRUCTION,
                                      temperature=0.0, response_mime_type="application/json", response_schema=ppg._PLANNER_DECISION_SCHEMA)
    r = client.models.generate_content(model=a.model, contents=prompt, config=cfg)
    out.append({"qid": q, "prompt": prompt, "raw_text": r.text, "finish_reason": str(r.candidates[0].finish_reason) if r.candidates else None})
json.dump(out, open(os.path.join(REPO, a.out), "w", encoding="utf-8", newline="\n"), indent=1)
print(json.dumps([{k: x[k] for k in ("qid", "raw_text")} for x in out], indent=1))
