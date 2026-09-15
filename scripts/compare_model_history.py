# -*- coding: utf-8 -*-
"""
离线对比两个 CST 工程的实体几何
================================

用途：**阶段 4 T1「实体级几何对比」的可复现工具**。

原理
----
CST 工程的 ``<工程名>/Model/3D/ModelHistory.json`` 保存着**全部建模 VBA**，
每条实体创建命令都带**精确坐标与表达式**。因此不打开 CST、不调 API，
就能逐实体对比两个工程的几何定义 —— 比读 bounding box 更精确。

为什么不用 bounding box
-----------------------
CST 的 ``Solid`` 对象**没有**包围盒查询（官方 VBA 参考 §7 只有布尔/实体管理/
网格属性/高级建模）；参考实现里的 `show-bounding-box` 也只是**切换显示**
（``Plot.DrawBox "True"``），不是查询。

用法
----
    python scripts/compare_model_history.py <工程A目录> <工程B目录>

两个参数都传**工程目录**（含 ``Model/3D/ModelHistory.json`` 的那一层），
或直接传 ``.cst`` 文件路径（会自动推导同名的工程目录）。

输出
----
1. 实体名集合对比（共有 / 仅 A 有 / 仅 B 有）
2. 对**共有实体**逐个做「规范化 VBA」比对：一致 / 不一致
3. 不一致的实体打印双方的几何定义片段，便于人工判定

退出码: 0=全部共有实体一致; 1=存在差异或参数错误
"""

import json
import re
import sys
from pathlib import Path

# 规范化时忽略的差异：纯缩进/空白
_WS = re.compile(r"[ \t]+")


def _norm(text):
    """去掉每行首尾空白与多余空格，便于忽略排版差异。"""
    return "\n".join(_WS.sub(" ", ln).strip() for ln in text.splitlines() if ln.strip())


def _code_of(entry):
    """history 条目的 code 可能是 str 或 list[str]。"""
    code = entry.get("code", "")
    return "\n".join(code) if isinstance(code, list) else str(code)


def load_entities(project):
    """
    读取工程历史，返回 ``{实体名: 创建该实体的 VBA 片段}``。

    一个实体名可能出现在多条历史里（先创建、后变换），本函数保留
    **首次出现**的那条，即其创建命令。
    """
    project = Path(project)
    if project.suffix.lower() == ".cst":
        project = project.parent / project.stem
    history_file = project / "Model" / "3D" / "ModelHistory.json"
    if not history_file.exists():
        raise FileNotFoundError(f"找不到建模历史：{history_file}")

    history = json.loads(history_file.read_text(encoding="utf-8")).get("history", [])
    entities = {}
    for entry in history:
        code = _code_of(entry)
        for name in re.findall(r'\.Name\s+"([^"]+)"', code):
            entities.setdefault(name.strip(), code)
    return entities


def compare(dir_a, dir_b):
    """对比两个工程目录，返回 (共有实体数, 不一致实体名列表)。"""
    ent_a = load_entities(dir_a)
    ent_b = load_entities(dir_b)
    shared = sorted(set(ent_a) & set(ent_b))

    print(f"A = {dir_a}\nB = {dir_b}")
    print(f"\n实体数：A={len(ent_a)}  B={len(ent_b)}  共有={len(shared)}")
    print(f"仅 A 有（{len(set(ent_a) - set(ent_b))}）：{sorted(set(ent_a) - set(ent_b))}")
    print(f"仅 B 有（{len(set(ent_b) - set(ent_a))}）：{sorted(set(ent_b) - set(ent_a))}")

    print(f"\n{'=' * 72}\n共有实体逐项比对（忽略缩进与空白）\n{'=' * 72}")
    differing = []
    for name in shared:
        if _norm(ent_a[name]) == _norm(ent_b[name]):
            print(f"  ✅ 一致   {name}")
        else:
            differing.append(name)
            print(f"  ❌ 不一致 {name}")

    for name in differing:
        print(f"\n{'-' * 72}\n### 不一致实体：{name}\n{'-' * 72}")
        print(f"--- A ---\n{ent_a[name].strip()}")
        print(f"\n--- B ---\n{ent_b[name].strip()}")

    print(f"\n{'=' * 72}")
    print(f"结论：共有 {len(shared)} 个实体，其中 {len(shared) - len(differing)} 个几何一致，"
          f"{len(differing)} 个不一致 -> {differing}")
    print("\n注意：共有实体一致 **不等于** 两个模型等价 —— 还需比对")
    print("  1) 仅一方存在的实体（上面的「仅 A 有 / 仅 B 有」）")
    print("  2) 布尔运算序列（add / subtract / intersect / insert 的条数与对象）")
    return len(shared), differing


def main(argv):
    if len(argv) != 3:
        print(__doc__)
        return 1
    try:
        _, differing = compare(argv[1], argv[2])
    except Exception as exc:
        print(f"对比失败：{exc!r}")
        return 1
    return 0 if not differing else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
