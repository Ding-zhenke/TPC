# -*- coding: utf-8 -*-
"""统计各包的公开 API 数量（AST 静态分析，不导入 cst）。用法: python scripts/_api_stats.py"""
import ast
import os
import sys
from collections import OrderedDict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TARGETS = OrderedDict([
    ("cst_solver", "cst_solver"),
    ("mesh_grid", "mesh_grid"),
    ("topo_modeler", "topo_modeler"),
    ("templates", "templates"),
    ("tpc_toolkit", "tpc_toolkit"),
])


def scan(path):
    funcs, classes, methods = [], [], {}
    for dirpath, dirnames, filenames in os.walk(path):
        dirnames[:] = [d for d in dirnames if d not in ("__pycache__", "tests")]
        for fn in sorted(filenames):
            if not fn.endswith(".py"):
                continue
            fp = os.path.join(dirpath, fn)
            with open(fp, encoding="utf-8") as f:
                try:
                    tree = ast.parse(f.read(), fp)
                except SyntaxError as e:
                    print(f"  !! SyntaxError in {fp}: {e}")
                    continue
            for node in tree.body:
                if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
                    funcs.append(f"{fn}::{node.name}")
                elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
                    pub = [m.name for m in node.body
                           if isinstance(m, ast.FunctionDef) and not m.name.startswith("_")]
                    classes.append(node.name)
                    methods[node.name] = pub
    return funcs, classes, methods


for label, rel in TARGETS.items():
    path = os.path.join(ROOT, rel)
    if not os.path.isdir(path):
        print(f"### {label}: MISSING")
        continue
    funcs, classes, methods = scan(path)
    total_m = sum(len(v) for v in methods.values())
    print(f"### {label}: {len(classes)} classes, {len(funcs)} module-level functions, "
          f"{total_m} public methods on classes")
    for c in classes:
        print(f"    {c}: {len(methods[c])}")
