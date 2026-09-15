# -*- coding: utf-8 -*-
"""检查仓库内 Markdown 的相对链接是否都能解析（忽略 http/anchor）。\n\n用法: python scripts/check_md_links.py\n按 skills/developer/WORKFLOW.md §9，移动/重命名文件后应跑一次。\n"""
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP_DIRS = {'.git', '__pycache__', 'node_modules', '.pytest_cache', 'archive'}
LINK = re.compile(r'\[[^\]]*\]\(([^)\s]+)\)')

bad = []
checked = 0
for dirpath, dirnames, filenames in os.walk(ROOT):
    dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
    for fn in filenames:
        if not fn.endswith('.md'):
            continue
        fp = os.path.join(dirpath, fn)
        text = io.open(fp, encoding='utf-8', errors='replace').read()
        for target in LINK.findall(text):
            if target.startswith(('http://', 'https://', 'mailto:', '#')):
                continue
            path_part = target.split('#', 1)[0]
            if not path_part:
                continue
            resolved = os.path.normpath(os.path.join(dirpath, path_part))
            checked += 1
            if not os.path.exists(resolved):
                bad.append((os.path.relpath(fp, ROOT), target))

print(f"检查了 {checked} 条相对链接")
if bad:
    print(f"[FAIL] {len(bad)} 条无法解析：")
    for f, t in bad:
        print(f"   {f}  ->  {t}")
    sys.exit(1)
print("[OK] 全部相对链接均可解析")
