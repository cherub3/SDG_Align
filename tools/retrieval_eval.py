"""Run the 15 fixed questions through the REAL stage-10 retrieve() and compute the Phase 1 metrics.

Usage:  python tools/retrieval_eval.py --root <dir containing data/proposals> --label before --out FILE
Needs sentence-transformers (not in requirements.txt: heavy; local, no API call).
Questions and metric rules: reports/evidence/metrics_definitions.md (frozen).
"""
import argparse
import glob
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
import chunk_metrics as cm  # noqa: E402

MODEL = "BAAI/bge-small-en-v1.5"
QUESTIONS = [
    ("What are the main components of the planetGOLD project in Mozambique?", "mozambique_planetgold"),
    ("How will the project reduce mercury use in artisanal gold mining?", "mozambique_planetgold"),
    ("Which indigenous peoples and local communities are involved in the Cameroon project?", "cameroon_biodiversity_iplc_conservation"),
    ("What protected areas or landscapes does the Cameroon project target?", "cameroon_biodiversity_iplc_conservation"),
    ("What renewable energy technologies will be deployed in Cuba?", "cuba_clean_energy"),
    ("How does the Cuba project contribute to the country's NDC?", "cuba_clean_energy"),
    ("What marine protected areas are covered in Ecuador?", "ecuador_marine_biodiversity"),
    ("What threats do Ecuador's coastal and marine ecosystems face?", "ecuador_marine_biodiversity"),
    ("What is the total GEF financing requested?", "any"),
    ("How will gender equality be mainstreamed in the project?", "any"),
    ("What are the key risks and mitigation measures?", "any"),
    ("How many hectares of landscape will be under improved management?", "any"),
    ("Which SDGs does the Ecuador biodiversity project contribute to?", "ecuador_biodiversity"),
    ("What water supply improvements are planned in Kathmandu?", "NOT INDEXED"),
    ("How will the project improve public schools in Karnataka?", "NOT INDEXED"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out_path = os.path.abspath(a.out)
    os.chdir(a.root)
    from sentence_transformers import SentenceTransformer
    from scripts.stage0_register import load_manifest
    from scripts.stage9_vector_indexing import FAISSAdapter
    from scripts.stage10_retrieval import retrieve

    st = SentenceTransformer(MODEL, device="cpu")

    class LocalBGE:
        provider_name, model_name, model_version = "huggingface", MODEL, "v1.5"
        def embed_batch(self, texts):
            return st.encode(list(texts), normalize_embeddings=False).tolist()
        def is_transient_error(self, e):
            return False

    ad = LocalBGE()
    manifest = load_manifest()
    chunks = {c["chunk_id"]: c for c in cm.load_chunks("data/proposals/chunks")}
    doc_name = {r.doc_id: os.path.basename(r.source_path or "").replace(".pdf", "") for r in manifest.values()}
    fps = []
    for mp in sorted(glob.glob("data/proposals/vector_index/*/index_metadata.json")):
        meta = json.load(open(mp, encoding="utf-8"))
        if (meta.get("provider"), meta.get("model_name"), meta.get("model_version")) == ("huggingface", MODEL, "v1.5"):
            fps.append(meta["index_fingerprint"])
    if len(fps) != 1:
        raise SystemExit(f"expected exactly one matching index, found {fps}")

    results, seen_dup, frag_top5, boiler_top5 = [], 0, 0, 0
    rank1_ok, rank1_n = 0, 0
    for i, (q, exp) in enumerate(QUESTIONS, 1):
        r = retrieve({"query": q, "index_fingerprints": fps, "top_k": 5}, manifest,
                     lambda p, m, v: ad, lambda metric: FAISSAdapter(metric))
        top, seen = [], set()
        for x in r["results"]:
            text = x.get("text") or chunks[x["chunk_id"]]["text"]
            key = cm.norm(text)
            dup = key in seen
            seen.add(key)
            seen_dup += dup
            frag_top5 += cm.is_fragment(text)
            boiler_top5 += cm.is_boilerplate_chunk(text)
            top.append({"rank": x["rank"], "chunk_id": x["chunk_id"], "doc": doc_name.get(x["doc_id"], x["doc_id"][:12]),
                        "score": round(x["score"], 4), "text": text, "len": len(text),
                        "boilerplate": cm.is_boilerplate_chunk(text), "fragment": cm.is_fragment(text), "duplicate_of_higher_rank": dup})
        if exp not in ("any", "NOT INDEXED"):
            rank1_n += 1
            rank1_ok += bool(top) and top[0]["doc"] == exp
        results.append({"n": i, "question": q, "expected_doc": exp, "status": r["status"], "top5": top})

    total = sum(len(x["top5"]) for x in results)
    answerable = [x for x in results if x["expected_doc"] != "NOT INDEXED"]
    total_ans = sum(len(x["top5"]) for x in answerable)
    boiler_ans = sum(t["boilerplate"] for x in answerable for t in x["top5"])
    out = {
        "label": a.label, "model": MODEL, "index_fingerprint": fps[0],
        "chunk_metrics": cm.chunk_metrics([c["text"] for c in chunks.values()]),
        "docs_indexed": sorted({doc_name.get(c["doc_id"], c["doc_id"][:12]) for c in chunks.values()}),
        "retrieval_metrics": {
            "results_total": total,
            "boilerplate_in_top5": boiler_top5, "boilerplate_share_top5_all15": round(boiler_top5 / total, 4),
            "boilerplate_share_top5_answerable13": round(boiler_ans / total_ans, 4),
            "fragments_in_top5": frag_top5, "duplicates_in_top5": seen_dup,
            "expected_doc_rank1": f"{rank1_ok}/{rank1_n}",
            "top1_scores": {x["n"]: x["top5"][0]["score"] for x in results if x["top5"]},
        },
        "results": results,
    }
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, ensure_ascii=False)
    print(json.dumps({k: out[k] for k in ("label", "chunk_metrics", "docs_indexed", "retrieval_metrics")}, indent=1))


if __name__ == "__main__":
    main()
