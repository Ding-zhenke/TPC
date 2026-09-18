# -*- coding: utf-8 -*-
r"""
V3 判据（「谐振峰偏差 < 1 GHz」）在**真实曲线**上的可执行验证
==============================================================

计划 P4/V3 原文：*「旧四个频点 dB 比较不等于『谐振峰偏差 < 1 GHz』；
需使用可比曲线、明确峰/谷提取规则并实际计算频率差」*。
这条判据此前只是文档里的一句话，没有 API、也没在真数据上算过。

本脚本（**离线**：只读已求解工程的结果，不启动 CST、不求解）用参考工程群里
**真实的 S1,1 曲线**把这条判据跑通：

1. 用**唯一**的提取规则（`tpc_toolkit.curves.find_resonances`，prominence 过滤）
   逐工程提取谐振；
2. 交叉核对：同一曲线经 `cst_mcp.analysis.find_resonances` 与
   `ResultReader.resonances()` 得到的**必须完全一致**（防两套规则漂移）；
3. 两两配对（就近配对 + 容差），算 Δf 并与 1 GHz 比较 —— 两个分支都要出现：
   至少一对 `ok=True`、至少一对 `ok=False` 或 `no_matched_resonance`；
4. 全程只读：参考工程目录前后快照必须一致。

⚠️ 这里验证的是**判据与提取规则**（V3 的方法学那一半）。「本库自己跑一次求解再与参考对比」
仍属真机（需 ≥2 次求解）。

用法::

    python scripts/verify_resonance_criterion.py
    python scripts/verify_resonance_criterion.py --prominence 0.5 --limit 1.0
"""

import argparse
import itertools
import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

REFERENCE_DIR = r'D:\成电博士生涯\拓扑光子晶体模型\硅基\普通单元天线'
REFERENCE_PROJECTS = (
    'Ant1_D_AB_120_Feed_antenna-DF.cst',
    'Ant1_D_BA_120_Feed_antenna-DF.cst',
    'Ant1_D_AB_180_Feed_antenna-DF.cst',
    'Ant1_D_AB_120_cylinder-DF.cst',
    'Ant1_D_BA_120_cylinder-DF.cst',
)
DEFAULT_CST_ROOT = r'C:\SOFTWARE\CST Studio Suite 2026'

_results = []


def record(item, status, detail, **extra):
    entry = {'item': item, 'status': status, 'detail': detail}
    entry.update(extra)
    _results.append(entry)
    print(f'[{status:^7}] {item}: {detail}', flush=True)


def snapshot(root):
    out = {}
    for dirpath, _dirnames, filenames in os.walk(root):
        for filename in filenames:
            path = os.path.join(dirpath, filename)
            try:
                stat = os.stat(path)
            except OSError:
                continue
            out[os.path.relpath(path, root)] = (stat.st_size, int(stat.st_mtime))
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dir', default=REFERENCE_DIR)
    parser.add_argument('--prominence', type=float, default=0.5,
                        help='prominence 下限（dB），用于滤掉数值毛刺')
    parser.add_argument('--limit', type=float, default=1.0,
                        help='V3 判据限值（GHz）')
    parser.add_argument('--tolerance', type=float, default=3.0,
                        help='配对容差（GHz）')
    parser.add_argument('--cst-root', default=os.environ.get('CST_INSTALL_PATH',
                                                             DEFAULT_CST_ROOT))
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    lib = os.path.join(args.cst_root, 'AMD64', 'python_cst_libraries')
    if os.path.isdir(lib) and lib not in sys.path:
        sys.path.insert(0, lib)
    if not os.path.isdir(args.dir):
        record('参考工程目录', 'UNKNOWN', f'不存在：{args.dir}（本脚本需要已求解的参考工程）')
        print('\n=== 汇总 ===\nUNKNOWN 1（没有参考工程，跳过）')
        return 0

    from topo_modeler.result_reader import ResultReader
    from tpc_toolkit.curves import find_resonances

    projects = [os.path.join(args.dir, name) for name in REFERENCE_PROJECTS]
    projects = [p for p in projects if os.path.isfile(p)]
    if not projects:
        record('参考工程', 'UNKNOWN', '目录里没有预期的已求解工程')
        print('\n=== 汇总 ===\nUNKNOWN 1（没有参考工程，跳过）')
        return 0

    before = snapshot(args.dir)
    readers, resonances = {}, {}
    for path in projects:
        label = os.path.basename(path).replace('Ant1_D_', '').replace('.cst', '')
        try:
            reader = ResultReader(path, names=['S1,1'], run_id=0)
            found = reader.resonances('S1,1', min_prominence_db=args.prominence)
        except Exception as exc:                      # noqa: BLE001
            record(f'{label} 提取谐振', 'FAIL', f'{type(exc).__name__}: {exc}')
            continue
        readers[label], resonances[label] = reader, found
        record(f'{label} 提取谐振', 'OK' if found else 'UNKNOWN',
               f'{len(found)} 个：' + ', '.join(f"{m['freq_ghz']:.2f}" for m in found))

        # 交叉核对：同一曲线经 MCP 层规则必须得到**完全一样**的结果
        try:
            from cst_mcp.analysis import find_resonances as mcp_find
            xs, ys = reader.read_s_parameters_db(names=['S1,1'])['S1,1']
            mcp_found = mcp_find(xs, ys, kind='min',
                                 min_prominence_db=args.prominence, band=None)
            same = mcp_found == found
            record(f'{label} 跨层规则一致性', 'OK' if same else 'FAIL',
                   'MCP 层与库层结果一致' if same
                   else f'不一致：库 {len(found)} 条 vs MCP {len(mcp_found)} 条')
        except Exception as exc:                      # noqa: BLE001
            record(f'{label} 跨层规则一致性', 'FAIL',
                   f'{type(exc).__name__}: {exc}')

    # 两两配对：两个分支都要出现
    verdicts = []
    for a, b in itertools.combinations(sorted(readers), 2):
        verdict = readers[a].resonance_shift(readers[b], 'S1,1',
                                             min_prominence_db=args.prominence,
                                             limit_ghz=args.limit,
                                             tolerance_ghz=args.tolerance)
        verdicts.append({'a': a, 'b': b, **verdict})
        worst = verdict['max_delta_ghz']
        record(f'{a} vs {b}', 'OK',
               f"配对 {verdict['n_matched']}，最大 Δf "
               f"{('%.3f GHz' % worst) if worst is not None else '—'}，"
               f"判据 {'通过' if verdict['ok'] else '未通过'}"
               f"（{verdict['reason']}）")

    passed = [v for v in verdicts if v['ok']]
    not_passed = [v for v in verdicts if not v['ok']]
    record('判据「通过」分支已被真实数据覆盖', 'OK' if passed else 'UNKNOWN',
           f'{len(passed)} 对通过，最小 Δf '
           f"{min((v['max_delta_ghz'] for v in passed), default=float('nan')):.3f} GHz"
           if passed else '没有任何一对 < 限值（无法证明通过分支可用）')
    record('判据「未通过」分支已被真实数据覆盖', 'OK' if not_passed else 'UNKNOWN',
           f"{len(not_passed)} 对未通过，最大 Δf "
           f"{max((v['max_delta_ghz'] or 0.0) for v in not_passed):.3f} GHz"
           if not_passed else '全部通过')
    unmatched = [v for v in verdicts if v['reason'] == 'no_matched_resonance']
    record('「配不上任何峰」不当成通过', 'OK' if unmatched else 'UNKNOWN',
           f'{len(unmatched)} 对没有任何配对（ok=False，如实报告）'
           if unmatched else '所有对都至少配上一对峰')

    after = snapshot(args.dir)
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    record('参考工程目录未被改动', 'OK' if not changed else 'FAIL',
           f'{len(before)} 个文件，变化 {len(changed)} 个')

    failed = [r for r in _results if r['status'] == 'FAIL']
    print('\n=== 汇总 ===')
    for entry in _results:
        print(f"{entry['status']:^7}  {entry['item']}")
    print(f'\nOK {len([r for r in _results if r["status"] == "OK"])} / '
          f'FAIL {len(failed)} / UNKNOWN '
          f'{len([r for r in _results if r["status"] == "UNKNOWN"])}')
    print(json.dumps(verdicts, ensure_ascii=False))
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
