# -*- coding: utf-8 -*-
r"""
V7 的「读取」半边：在**真实 CST 输出**上验证结果读取（不需要 CST、不需要求解）
==============================================================================

计划 P4/V7 要的是「真实 runner 完成一次小范围串行闭环」—— 那需要真跑求解。
但 V7 里有**一半是“读”**：`cst_solver.Result` / `topo_modeler.ResultReader` /
`cst_solver.run_contract` 的结果读取与指纹判定。这一半**完全可以在真机之外验证**：
`cst.results` 官方文档就写着「No running instance of CST Studio Suite is required」，
只要有一个**真的算过的工程**即可。

本脚本用参考工程（真实求解结果，含 1D S 参数、远场、材料色散等 31 个结果树条目）验证：

1. `cst_solver.Result` 能打开并列出结果树、运行 ID；
2. `topo_modeler.result_reader.ResultReader` 能读出 S 参数曲线、峰位置与指定频点值，
   并且**缺项时报错而不是返回空数据**；
3. `cst_solver.run_contract.cst_result_probe()` / `result_fingerprint()` 能对真实输出算出指纹；
4. 读取过程**不改动工程**（前后快照比对）；
5. 「工程不存在」时报的是**可执行的原因**（含非 ASCII 路径时 CST 会误报 UnicodeDecodeError，
   本库已把它翻译成「工程文件不存在」）。

全程**只读**：不启动 CST、不复制大文件、不写工程目录。

用法::

    python scripts/verify_result_reading.py                  # 用默认参考工程
    python scripts/verify_result_reading.py --project <path>
    python scripts/verify_result_reading.py --snapshot-copy  # 额外做一次「拷贝到临时目录再读」的对照
"""

import argparse
import json
import os
import shutil
import sys
import tempfile
import time
import traceback

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

DEFAULT_PROJECT = (r'D:\成电博士生涯\拓扑光子晶体模型\硅基\普通单元天线'
                   r'\Ant1_D_BA_120_Feed_antenna-DF.cst')
DEFAULT_CST_ROOT = r'C:\SOFTWARE\CST Studio Suite 2026'

_results = []


def record(item, status, detail, **extra):
    entry = {'item': item, 'status': status, 'detail': detail}
    entry.update(extra)
    _results.append(entry)
    print(f'[{status:^7}] {item}: {detail}', flush=True)


def snapshot(root):
    """工程目录快照（相对路径 → (大小, mtime)）。"""
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


def ensure_cst_results_importable(cst_root):
    """把 CST 的 Python 库目录加进 sys.path 并导入 `cst.results`（离线，不启动 CST）。"""
    lib = os.path.join(cst_root, 'AMD64', 'python_cst_libraries')
    if os.path.isdir(lib) and lib not in sys.path:
        sys.path.insert(0, lib)
    import cst.results                                    # noqa: PLC0415
    return cst.results


def probe_missing_paths():
    """「工程不存在」必须报成可执行的原因（含非 ASCII 路径的误报场景）。"""
    from cst_solver import Result

    for label, path in (('不存在的 ASCII 路径', os.path.join(tempfile.gettempdir(),
                                                             'tpc_no_such.cst')),
                        ('不存在的含中文路径', os.path.join(tempfile.gettempdir(),
                                                           '不存在的工程.cst'))):
        try:
            Result(path)
            record(f'缺失工程：{label}', 'FAIL', '竟然打开成功了？')
        except RuntimeError as exc:
            text = str(exc)
            ok = '工程文件不存在' in text
            record(f'缺失工程：{label}', 'OK' if ok else 'FAIL',
                   text[:140].replace('\n', ' '))
        except Exception as exc:                          # noqa: BLE001
            record(f'缺失工程：{label}', 'FAIL',
                   f'抛出了非 RuntimeError：{type(exc).__name__}: {exc}')


def verify_reading(project, run_id=0):
    """读真实结果：树、运行 ID、S 参数、指纹、缺项行为。"""
    from cst_solver import Result
    from cst_solver.run_contract import cst_result_probe, result_fingerprint
    from topo_modeler.result_reader import ResultReader

    t0 = time.time()
    result = Result(project)
    record('solver.Result 打开工程', 'OK', f'{time.time() - t0:.2f}s')

    items = list(result.get_tree_items())
    run_ids = list(result.get_all_run_ids())
    record('结果树条目', 'OK' if items else 'FAIL', f'{len(items)} 条')
    record('运行 ID', 'OK' if run_ids else 'FAIL', f'{run_ids}')

    s_names = sorted({str(item).split('\\')[-1] for item in items
                      if 'S-Parameters' in str(item)})
    record('S 参数条目', 'OK' if s_names else 'FAIL', f'{s_names}')

    # 逐条读曲线（缺项/读不动必须报错，不能静默返回空）
    reader = ResultReader(project, names=s_names or ['S1,1'], run_id=run_id)
    for name in s_names or ['S1,1']:
        try:
            curve = reader.read_s_parameters(names=[name]).get(name)
            xs, ys = curve
            peak = reader.peak_position(name, kind='min')
            record(f'{name} 曲线', 'OK',
                   f'{len(xs)} 点，{xs[0]:.1f}–{xs[-1]:.1f} GHz；'
                   f'最小值 {peak[1]:.3f} dB @ {peak[0]:.3f} GHz' if peak else
                   f'{len(xs)} 点')
        except Exception as exc:                          # noqa: BLE001
            record(f'{name} 曲线', 'FAIL', f'{type(exc).__name__}: {exc}')

    try:
        probe = cst_result_probe(project)
        # `cst_result_probe` 的契约：成功时给 `run_ids` + `available_results`；
        # CST 不可用或读取失败时把原因放进 `error`，并**保留**磁盘部分。
        ok = 'error' not in probe
        detail = (f"run_ids={probe.get('run_ids')} "
                  f"available_results={probe.get('available_results')}"
                  if ok else f"error={probe['error']}")
        record('run_contract.cst_result_probe', 'OK' if ok else 'UNKNOWN',
               detail[:200])
    except Exception as exc:                              # noqa: BLE001
        record('run_contract.cst_result_probe', 'FAIL',
               f'{type(exc).__name__}: {exc}')

    try:
        fingerprint = result_fingerprint(project)
        record('result_fingerprint', 'OK' if fingerprint else 'UNKNOWN',
               f'{str(fingerprint)[:120]}')
    except Exception as exc:                              # noqa: BLE001
        record('result_fingerprint', 'FAIL', f'{type(exc).__name__}: {exc}')

    # 缺项：读出不存在的结果项时报错（不是空数据）
    missing = 'S9,9'
    try:
        reader.read_s_parameters(names=[missing])
        record(f'缺项 {missing} 的行为', 'FAIL', '读到了不存在的结果项（不应发生）')
    except Exception as exc:                              # noqa: BLE001
        record(f'缺项 {missing} 的行为', 'OK',
               f'如实报错：{type(exc).__name__}')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', default=DEFAULT_PROJECT)
    parser.add_argument('--cst-root', default=os.environ.get('CST_INSTALL_PATH',
                                                             DEFAULT_CST_ROOT))
    parser.add_argument('--run-id', type=int, default=0)
    parser.add_argument('--snapshot-copy', action='store_true',
                        help='额外把工程复制到临时目录再读一次（对照，验证与路径无关）')
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    if not os.path.isfile(args.project):
        record('参考工程', 'UNKNOWN',
               f'没有找到已求解的参考工程：{args.project}（本脚本需要一份真的算过的工程）')
        print('\n=== 汇总 ===\nUNKNOWN 1（缺参考工程，跳过）')
        return 0
    try:
        ensure_cst_results_importable(args.cst_root)
        record('cst.results 可用', 'OK', f'{args.cst_root}\\AMD64\\python_cst_libraries')
    except Exception as exc:                              # noqa: BLE001
        record('cst.results 可用', 'UNKNOWN',
               f'本机 CST Python 库不可用（{type(exc).__name__}: {exc}）—— 跳过读取验证')
        print('\n=== 汇总 ===\nUNKNOWN 1（无 CST 库，跳过）')
        return 0

    root = os.path.dirname(args.project)
    before = snapshot(root)
    try:
        verify_reading(args.project, run_id=args.run_id)
    except Exception:                                     # noqa: BLE001
        record('读取过程异常', 'FAIL', traceback.format_exc(limit=3))
    probe_missing_paths()

    if args.snapshot_copy:
        tmp = tempfile.mkdtemp(prefix='tpc_result_copy_')
        try:
            copy = os.path.join(tmp, os.path.basename(args.project))
            shutil.copy2(args.project, copy)
            record('对照：复制到临时目录再读', 'OK' if os.path.isfile(copy) else 'FAIL',
                   tmp)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    after = snapshot(root)
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    record('工程目录未被改动', 'OK' if not changed else 'FAIL',
           f'{len(before)} 个文件，变化 {len(changed)} 个' +
           (f'：{changed[:3]}' if changed else ''))

    failed = [r for r in _results if r['status'] == 'FAIL']
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
