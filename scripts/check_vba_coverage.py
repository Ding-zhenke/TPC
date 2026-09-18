"""Report CST VBA help families against the current Python wrapper surface.

This is an offline inventory check.  It intentionally reports families as
``partial`` unless a dedicated wrapper module exists; it never claims that a
VBA call is CST-compatible or runs a solver.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


FAMILY_MAP = {
    "modeling": ["common_vbabasicsolids", "common_vbacurves", "common_vbaextrude", "common_vbaloft"],
    "postprocessing": ["common_vbapostproc", "special_vbapostproc"],
    "ports": ["special_vbaports"],
    "monitors": ["special_vbamonitors"],
    "solvers": ["special_vbasolver", "special_vbaparametersweep", "special_vbatransientsolvers", "special_vbastaticsolver", "special_vbathermalsolver"],
    "import_export": ["common_vbaimpexp"],
    "coordinates": ["common_vbaunitso", "common_vbawcso", "common_vbapicko"],
}

WRAPPER_MARKERS = {
    "modeling": ["cst_solver/modeling"],
    "postprocessing": ["cst_solver/postprocessing", "cst_solver/_result_core.py"],
    "ports": ["cst_solver/simulation/ports.py"],
    "monitors": ["cst_solver/simulation/monitors.py"],
    "solvers": ["cst_solver/simulation/solver.py"],
    "import_export": ["cst_solver/import_export"],
    "coordinates": ["cst_solver/modeling/wcs.py", "cst_solver/modeling/picks.py", "cst_solver/units.py"],
}


def build_report(catalog: dict, repo_root: Path) -> dict:
    families = catalog.get("family_counts", {})
    rows = []
    for capability, help_families in FAMILY_MAP.items():
        pages = sum(int(families.get(name, 0)) for name in help_families)
        present = [str(repo_root / marker) for marker in WRAPPER_MARKERS[capability]
                   if (repo_root / marker).exists()]
        status = "partial" if present else "missing"
        rows.append({"capability": capability, "help_pages": pages,
                     "help_families": help_families, "wrapper_files": present,
                     "status": status})
    return {"source": catalog.get("source"), "offline_only": True, "rows": rows}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    report = build_report(catalog, args.repo_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    for row in report["rows"]:
        print(f"{row['capability']}: {row['status']} ({row['help_pages']} help pages)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
