"""Fingerprint a finished build (stages 4-9) so two builds can be compared byte for byte.

Usage: python tools/hash_build.py --out FILE        (run from the repo root)
Hashes: chunk text (all chunks, in order), embedding vectors (float32 bytes, in chunk order), index.bin,
and for information the whole-file hashes (which include timestamps, so they are expected to differ).
"""
import argparse
import glob
import hashlib
import json
import os

import pyarrow.parquet as pq


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = {"per_doc": {}, "index": {}}
    for f in sorted(glob.glob("data/proposals/chunks/*/chunks.json")):
        doc = os.path.basename(os.path.dirname(f))
        chunks = json.load(open(f, encoding="utf-8"))["chunks"]
        text_h = sha(json.dumps([(c["chunk_id"], c["text"]) for c in chunks], ensure_ascii=False).encode("utf-8"))
        ef = f"data/proposals/embeddings/{doc}/embeddings.parquet"
        t = pq.read_table(ef).to_pylist()
        t.sort(key=lambda r: r["chunk_id"])
        vec_h = sha(b"".join(
            __import__("numpy").asarray(r["embedding_vector"], dtype="float32").tobytes() for r in t))
        out["per_doc"][doc] = {"chunks": len(chunks), "chunk_text_sha256": text_h, "vectors_sha256": vec_h,
                               "chunks_json_file_sha256": sha(open(f, "rb").read()),
                               "embeddings_parquet_file_sha256": sha(open(ef, "rb").read())}
    for d in sorted(glob.glob("data/proposals/vector_index/*")):
        out["index"][os.path.basename(d)] = {
            "index_bin_sha256": sha(open(d + "/index.bin", "rb").read()),
            "id_map_parquet_file_sha256": sha(open(d + "/id_map.parquet", "rb").read())}
    json.dump(out, open(a.out, "w"), indent=2)
    print(json.dumps(out["index"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
