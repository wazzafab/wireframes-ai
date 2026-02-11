"""
LOCKED PIPELINE ORDER (do not reorder without updating validators):
1) main.py                 -> sitemap.json, facts.json, wireframes.json
2) semantics.py            -> semantic.json (anchored to wireframes sections)
3) enrich_wireframes.py    -> wireframes.enriched.json
4) verify.py               -> structural gate
5) verify_semantics.py     -> semantic coverage gate
6) render_wireframes.py    -> SVG output
"""

import subprocess
import sys


PIPELINE = [
    ("Phase 1/2: main.py (sitemap/facts/wireframes)", ["python", "main.py"]),
    ("Phase 2.5: semantics.py (semantic.json)", ["python", "semantics.py"]),
    ("Enrich: enrich_wireframes.py (wireframes.enriched.json)", ["python", "enrich_wireframes.py"]),
    ("Verify: verify.py (structure)", ["python", "verify.py"]),
    ("Verify: verify_semantics.py (meaning coverage)", ["python", "verify_semantics.py"]),
    ("Render: render_wireframes.py (SVGs)", ["python", "render_wireframes.py"]),
]


def run_step(label, cmd):
    print(f"\n=== {label} ===")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f"\nERROR: Pipeline stopped: {label}")
        sys.exit(result.returncode)
    print(f"OK: {label}")


def main():
    for label, cmd in PIPELINE:
        run_step(label, cmd)

    print("\nPIPELINE COMPLETE (all steps passed).")


if __name__ == "__main__":
    main()
