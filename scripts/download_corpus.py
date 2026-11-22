"""Corpus fetch/verify helper (STUB - no download source is configured yet).

The source PDFs are NOT stored in this repository: their redistribution licence has not been
confirmed. Obtain them from their original publisher, place them as listed below, then run

    python scripts/download_corpus.py --check

which verifies every expected file by SHA-256 (the pipeline's doc_id is "doc_" + this hash, so a
matching file reproduces the same doc_id and chunk ids).

    python scripts/download_corpus.py --print-manifest   # machine-readable list

TODO: when a legitimate source URL per document is known, fill in the URL column and implement
download. Do not guess URLs.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

RAW_DIR = Path("data/proposals/raw")

# (category folder, filename, sha256, source_url)
CORPUS = [
    ("biodiversity", "cameroon_biodiversity_iplc_conservation.pdf", "2bfb8f4c19d6f3c9d77f18e545b3a7e55745a2a96c91dbe5f73822fc6bd2ad6c", None),
    ("biodiversity", "ecuador_jaguar_landscape_connectivity.pdf", "6f1ac2315be2a47c98cd10289b475811e5fff8eb79b3be6219ebe718f3ee953a", None),
    ("biodiversity", "ecuador_marine_biodiversity.pdf", "d01bd4278178e388128443134b04a77fdd79fed307e5bf799d3ebebfec8cb2a4", None),
    ("biodiversity", "ecuador_biodiversity.pdf", "e72e747170fa21c7f40d0c27e77cbf7ec23ea66b9448a13cd3548a69ad802eec", None),
    ("climate", "cuba_clean_energy.pdf", "e75ba796c7d58cc1c27571b733bbe09cfc2afbfbce2271dd66ffbe2ca179500f", None),
    ("education", "india_karnataka_public_schools_2026.pdf", "6cbb8ab79a146d77455357f0895abcf8769f235ea5c899ea712c08ca2c0b6969", None),
    ("health", "armenia_healthcare_quality_improvement_2024.pdf", "49578294e00a7ff5f4d9f945ffe15a4f23b603ed1733b3db088a9edbb38eb4bc", None),
    ("health", "sri_lanka_universal_health_coverage_2025.pdf", "559ccd15c023e037e1bb47af88729606b3be08ea695d7f818bcb213ed7746297", None),
    ("poverty", "bangladesh_displaced_myanmar_livelihoods_2025.pdf", "5e4674e8f6c7829e829c8894b6f98eef96e3dd9da2f329ed7a77c1e154861e3b", None),
    ("poverty", "bhutan_rural_finance_development_2020.pdf", "14346ab83b31206cda560ba53daa18a5791245f62391e412e15f3e6ec46096cc", None),
    ("poverty", "sri_lanka_post_cyclone_livelihood_recovery_2026.pdf", "dc746aa33f34cfe672faec1d2c3b471d002d451a1ad3e35be227a6026cf05b27", None),
    ("responsible_consumption", "mozambique_planetgold.pdf", "e2fd661744c7c3b66a02391da610a266a80068a43997a5e0d2568b4a9f404354", None),
    ("water", "nepal_kathmandu_water_supply_2024.pdf", "8e9df83dc7002dc54065994745b70c5c532203690723fe37a9a2581e20639d59", None),
]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def check(raw_dir: Path = RAW_DIR) -> int:
    """Returns the number of missing or mismatching files."""
    problems = 0
    for category, name, digest, _url in CORPUS:
        path = raw_dir / category / name
        if not path.exists():
            print(f"MISSING   {path}")
            problems += 1
        elif _sha256(path) != digest:
            print(f"MISMATCH  {path} (sha256 differs from the expected file)")
            problems += 1
        else:
            print(f"OK        {path}")
    return problems


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="verify files already placed under data/proposals/raw/")
    parser.add_argument("--print-manifest", action="store_true", help="print the expected corpus as JSON")
    args = parser.parse_args(argv)
    if args.print_manifest:
        print(json.dumps([dict(category=c, filename=n, sha256=s, source_url=u) for c, n, s, u in CORPUS], indent=2))
        return 0
    if args.check:
        return 1 if check() else 0
    parser.print_help()
    print("\nNo download source is configured; see the module docstring.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
