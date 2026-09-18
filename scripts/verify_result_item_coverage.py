# -*- coding: utf-8 -*-
r"""
结果项覆盖扫描：这个工程的哪些结果**读得出来**（离线，只读）
==============================================================

用途：在真机验收（V2/V7/V9）之前先知道「这个工程的结果能不能读」，
免得跑到一半才发现某个条目读不出来。

做法：对工程结果树里的**每一项**尝试打开并读数据，逐项报告状态与失败原因；
失败原因走库里的诊断（`cst_solver._result_core.describe_result_item_failure`），
因此输出是**可执行**的话，而不是裸 `UnicodeDecodeError`。

已知情形（2026-09-17 实测，CST 2026）：`ANT_LEAKY_EPC_GRID.cst` 的 63 项里
45 项可读、18 项 ``1D Results\farfield (f=…)`` 在 `get_result_item()` 阶段就抛
`UnicodeDecodeError`（同工程其它带括号的条目正常 ⇒ 与路径写法无关）。
本脚本就是把这个事实变成**可复现的检查**。

全程只读；参考工程目录前后快照必须一致。

用法::

    python scripts/verify_result_item_coverage.py <工程.cst> [--json]
    python scripts/verify_result_item_coverage.py                 # 用默认的 Leaky 参考工程
"""

import argparse
import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

DEFAULT_PROJECT = (r'D:\成电博士生涯\拓扑光子晶体模型\硅基\Leaky'
                   r'\ANT_LEAKY_EPC_GRID.cst')
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


def sweep(project, quiet=False):
    """逐项尝试读取，返回 (可读, 失败列表)。"""
    from cst_solver import Result

    result = Result(project)
    items = [str(i) for i in result.get_tree_items()]
    record('结果树条目', 'OK' if items else 'FAIL', f'{len(items)} 条')

    readable, unreadable = [], []
    for item in items:
        try:
            node = result.result_module.get_result_item(item, 0)
            xs = node.get_xdata()
            readable.append((item, len(xs)))
        except Exception as exc:                       # noqa: BLE001
            from cst_solver._result_core import describe_result_item_failure
            unreadable.append((item, type(exc).__name__,
                               describe_result_item_failure(item, exc, [item])))

    record('可读项', 'OK' if readable else 'FAIL', f'{len(readable)}/{len(items)}')
    record('不可读项', 'OK', f'{len(unreadable)}/{len(items)}')

    # 不变式（2026-09-17 修掉误报后加）：list_s_parameters() 列出的每个名字都必须可读，
    # 且**只能**是真 S 参数 —— `…\Convergence\S-Parameters\Reflection S-Parameters [1]`
    # 这种同名收敛曲线不算。
    declared = result.list_s_parameters()
    record('list_s_parameters()', 'OK' if declared else 'UNKNOWN', f'{declared}')
    broken = []
    for name in declared:
        try:
            if len(result.read_s_parameter(name, 0)) == 0:
                broken.append((name, '0 点'))
        except Exception as exc:                       # noqa: BLE001
            broken.append((name, type(exc).__name__))
    record('不变式：列出的 S 参数都可读', 'OK' if declared and not broken else
           ('UNKNOWN' if not declared else 'FAIL'), f'{broken or "全部可读"}')
    if not quiet:
        for item, kind, message in unreadable:
            print(f'    · [{kind}] {item}')
            print(f'      {message[:200]}')
    # 按「名字模式」归类，便于判断是普遍问题还是个别条目
    patterns = {}
    for item, kind, _message in unreadable:
        key = 'farfield (f=…)' if 'farfield (' in item else item.rsplit('\\', 1)[0]
        patterns.setdefault(key, []).append(kind)
    for key, kinds in sorted(patterns.items()):
        record(f'不可读模式：{key}', 'OK', f'{len(kinds)} 项，{sorted(set(kinds))}')
    return readable, unreadable


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project', nargs='?', default=DEFAULT_PROJECT)
    parser.add_argument('--cst-root', default=os.environ.get('CST_INSTALL_PATH',
                                                             DEFAULT_CST_ROOT))
    parser.add_argument('--json', action='store_true', help='只输出 JSON')
    parser.add_argument('--quiet', action='store_true', help='不逐项打印失败详情')
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    lib = os.path.join(args.cst_root, 'AMD64', 'python_cst_libraries')
    if os.path.isdir(lib) and lib not in sys.path:
        sys.path.insert(0, lib)
    if not os.path.isfile(args.project):
        record('工程', 'UNKNOWN', f'不存在：{args.project}')
        print('\nUNKNOWN 1（没有参考工程，跳过）')
        return 0

    root = os.path.dirname(args.project)
    before = snapshot(root)
    try:
        sweep(args.project, quiet=args.quiet)
        # 完整路径与相对路径必须给出同样的数据（2026-09-17 修掉的路径陷阱）
        from cst_solver import Result
        result = Result(args.project)
        # ⚠️ 取样点名要用 `list_s_parameters()` 的返回值（保证是真 S 参数）——
        #    直接按名字里有没有 'S-Parameters' 去筛，会取到收敛监控曲线。
        declared = result.list_s_parameters()
        sample = ['1D Results\\S-Parameters\\' + declared[0]] if declared else []
        if sample:
            full = result.read_1D(sample[0])
            relative = result.read_1D(sample[0].split('\\', 1)[1])
            same = full.shape == relative.shape and (full == relative).all()
            record('完整路径 vs 相对路径结果一致', 'OK' if same else 'FAIL',
                   f'{sample[0]} → {full.shape}')
    except Exception as exc:                           # noqa: BLE001
        import traceback
        record('扫描过程异常', 'FAIL', traceback.format_exc(limit=3)[:300])
    after = snapshot(root)
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    record('工程目录未被改动', 'OK' if not changed else 'FAIL',
           f'{len(before)} 个文件，变化 {len(changed)} 个')

    failed = [r for r in _results if r['status'] == 'FAIL']
    if not args.json:
        print('\n=== 汇总 ===')
        for entry in _results:
            print(f"{entry['status']:^7}  {entry['item']}")
        print(f'\nOK {len([r for r in _results if r["status"] == "OK"])} / '
              f'FAIL {len(failed)} / UNKNOWN '
              f'{len([r for r in _results if r["status"] == "UNKNOWN"])}')
    print(json.dumps(_results, ensure_ascii=False))
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
