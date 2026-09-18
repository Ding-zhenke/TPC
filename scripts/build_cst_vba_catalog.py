"""Build a small, machine-readable index of the installed CST VBA help.

The catalog is deliberately an index, not a guessed API binding: signatures are
kept as source file references and extracted headings.  This lets us compare
the installed CST release with our wrappers without importing ``cst`` or
starting CST.
"""
from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path


def _text(value: str) -> str:
    value = re.sub(r"<script.*?</script>|<style.*?</style>", " ", value,
                   flags=re.I | re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def _entry(path: Path, root: Path) -> dict[str, object]:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    title = ""
    match = re.search(r"<title[^>]*>(.*?)</title>", raw, re.I | re.S)
    if match:
        title = _text(match.group(1))
    headings = []
    for match in re.finditer(r"<h[1-4][^>]*>(.*?)</h[1-4]>", raw,
                             re.I | re.S):
        heading = _text(match.group(1))
        if heading and heading not in headings:
            headings.append(heading)
        if len(headings) >= 30:
            break
    return {
        "path": path.relative_to(root).as_posix(),
        "family": path.parent.name,
        "title": title,
        "headings": headings,
    }


def build(root: Path) -> dict[str, object]:
    vba = root / "mergedProjects" / "VBA_3D"
    files = sorted(vba.rglob("*.htm"))
    entries = [_entry(path, root) for path in files]
    families: dict[str, int] = {}
    for item in entries:
        family = str(item["family"])
        families[family] = families.get(family, 0) + 1
    return {
        "source": str(root),
        "scope": "mergedProjects/VBA_3D",
        "file_count": len(entries),
        "family_counts": dict(sorted(families.items())),
        "entries": entries,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--help-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if not args.help_root.is_dir():
        parser.error(f"CST help directory not found: {args.help_root}")
    catalog = build(args.help_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(catalog, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    print(f"indexed {catalog['file_count']} VBA help pages -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
