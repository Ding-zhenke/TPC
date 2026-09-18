# -*- coding: utf-8 -*-
r"""
MCP 分析与报告路径吃**真实曲线**（离线；不是假后端合成曲线）
============================================================

P3 的离线证据此前全部基于**假后端**产出的**合成**曲线（`test_tools.py` 里写明
「不能代替真机」）。但分析/报告这一段**根本不需要 CST 跑求解** —— 只要有
**真实的 S 参数曲线**（从已求解工程离线读出来）就能验。本脚本把这一段补上：

1. 从真实工程导出 CSV（1 端口 / 2 端口 / **3 端口 6 条**）；
2. 走 MCP 工具 `analyze_s_parameters`（阈值/判据/谐振/最小 prominence）；
3. **交叉核对**：同一曲线用库层规则（`tpc_toolkit.curves.find_resonances`）
   算出来的谐振必须与 MCP 给的**条数一致、频率差 < 1e-3 GHz**
   （差异只来自 CSV 往返的浮点末位舍入，实测 ~1e-8 GHz）；
4. 走 MCP 工具 `export_report` → HTML/CSV 产物落在服务工作目录内、路径唯一、
   HTML 自包含（零 CDN）；
5. 负例：`out_dir` 写到工作目录外必须被 `workdir_escape` 拒绝；
6. 全程只读：参考工程目录前后快照一致。

用法::

    python scripts/verify_mcp_real_curves.py
"""

import argparse
import glob
import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
_MCP_SRC = os.path.join(PROJECT_ROOT, 'integrations', 'cst-mcp', 'src')
if _MCP_SRC not in sys.path:
    sys.path.insert(0, _MCP_SRC)

BASE_DEFAULT = r'D:\成电博士生涯\拓扑光子晶体模型\硅基'
DEFAULT_CST_ROOT = r'C:\SOFTWARE\CST Studio Suite 2026'

#: 想要覆盖的形态：1 端口 / 2 端口（含收敛监控陷阱）/ 3 端口 6 条
WANTED = (
    (r'普通单元天线\Ant1_D_BA_120_Feed_antenna-DF.cst', 'S1,1', 1),
    (r'Leaky\ANT_LEAKY_EPC_GRID.cst', 'S2,1', 2),
    (r'MPMBA\Ant3_epc.cst', 'S1,1', 6),
)

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
    parser.add_argument('--base', default=BASE_DEFAULT)
    parser.add_argument('--cst-root', default=os.environ.get('CST_INSTALL_PATH',
                                                             DEFAULT_CST_ROOT))
    parser.add_argument('--threshold', type=float, default=-10.0)
    parser.add_argument('--prominence', type=float, default=0.5)
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    lib = os.path.join(args.cst_root, 'AMD64', 'python_cst_libraries')
    if os.path.isdir(lib) and lib not in sys.path:
        sys.path.insert(0, lib)

    cases = []
    for relative, metric, expected_params in WANTED:
        path = os.path.join(args.base, relative)
        if os.path.isfile(path):
            cases.append((path, metric, expected_params))
    if not cases:
        record('参考工程', 'UNKNOWN', f'{args.base} 下没有可用的已求解工程')
        print('\nUNKNOWN 1（没有参考工程，跳过）')
        return 0

    import numpy as np
    from cst_solver import Result
    from cst_solver._result_core import _to_db
    from cst_mcp import runtime, tools as mcp_tools
    from tpc_toolkit.curves import find_resonances

    workdir = runtime.default_workdir()
    runtime.reset()
    runtime.configure(workdir=workdir)
    service = runtime.get_service()
    out_dir = os.path.join(service.workdir, 'reports_real')
    record('服务工作目录', 'OK', service.workdir)

    roots = sorted({os.path.dirname(path) for path, _m, _n in cases})
    before = {root: snapshot(root) for root in roots}
    report_paths = []

    for path, metric, expected_params in cases:
        label = os.path.basename(path)
        result = Result(path)
        names = result.list_s_parameters()
        record(f'{label} 声明的 S 参数', 'OK' if len(names) == expected_params
               else 'FAIL', f'{names}（期望 {expected_params} 条）')

        csv_path = os.path.join(service.workdir, f'{label}.csv')
        result.export_s_parameters_csv(csv_path, run_id=0, names=names)

        analyzed = mcp_tools.dispatch('analyze_s_parameters', {
            'csv_path': csv_path, 'threshold_db': args.threshold,
            'criterion': 'below', 'metric': metric,
            'resonance_kind': 'min', 'min_prominence_db': args.prominence})
        if not analyzed.get('ok'):
            record(f'{label} analyze_s_parameters', 'FAIL',
                   json.dumps(analyzed.get('error'), ensure_ascii=False)[:160])
            continue
        detail = analyzed['analysis']
        record(f'{label} analyze_s_parameters', 'OK',
               f"n_points={detail.get('n_points')} n_bands={detail.get('n_bands')} "
               f"n_resonances={detail.get('n_resonances')} metric={detail.get('metric')}")

        # 交叉核对：库层规则 vs MCP（差异只应来自 CSV 往返舍入）
        xs, ys = result.read_1D('S-Parameters\\' + metric).T
        library_peaks = find_resonances(np.asarray(xs).astype(float),
                                       _to_db(np.asarray(ys)), kind='min',
                                       min_prominence_db=args.prominence)
        lib_freqs = [float(p['freq_ghz']) for p in library_peaks]
        mcp_freqs = [float(p['freq_ghz']) for p in detail.get('resonances', [])]
        delta = max((abs(a - b) for a, b in zip(lib_freqs, mcp_freqs)), default=0.0)
        same_count = len(lib_freqs) == len(mcp_freqs)
        record(f'{label} 跨层谐振一致', 'OK' if same_count and delta < 1e-3 else 'FAIL',
               f'库 {len(lib_freqs)} 条 vs MCP {len(mcp_freqs)} 条，'
               f'最大频率差 {delta:.2e} GHz（阈值 1e-3）')

        reported = mcp_tools.dispatch('export_report', {
            'csv_path': csv_path, 'threshold_db': args.threshold, 'metric': metric,
            'title': f'{label} 真实曲线报告', 'formats': ['html', 'csv'],
            'out_dir': out_dir})
        if not reported.get('ok'):
            record(f'{label} export_report', 'FAIL',
                   json.dumps(reported.get('error'), ensure_ascii=False)[:160])
            continue
        kinds = sorted(a['kind'] for a in reported['artifacts'])
        files_ok = all(os.path.isfile(a['path']) for a in reported['artifacts'])
        report_paths += [a['path'] for a in reported['artifacts']]
        html = [a['path'] for a in reported['artifacts'] if a['kind'] == 'html']
        self_contained = False
        if html:
            text = open(html[0], encoding='utf-8', errors='replace').read()
            self_contained = ('http://' not in text and 'https://' not in text
                              and metric in text)
        record(f'{label} export_report', 'OK' if files_ok and kinds == ['csv', 'html']
               and self_contained else 'FAIL',
               f'产物 {kinds}，均存在={files_ok}，HTML 自包含且含指标名={self_contained}')

    # 负例：产物目录写到工作目录外必须被拒
    outside = os.path.join(os.path.dirname(service.workdir), 'tpc_outside_probe')
    rejected = mcp_tools.dispatch('export_report', {
        'csv_path': os.path.join(service.workdir, f'{os.path.basename(cases[0][0])}.csv'),
        'threshold_db': args.threshold, 'formats': ['html'], 'out_dir': outside})
    record('负例：产物目录逃出工作目录被拒', 'OK' if rejected.get('ok') is False
           and rejected['error']['code'] == 'workdir_escape' else 'FAIL',
           json.dumps(rejected.get('error', {}), ensure_ascii=False)[:120])

    duplicated = len(report_paths) - len(set(report_paths))
    record('多次报告产物路径互不重复', 'OK' if duplicated == 0 else 'FAIL',
           f'{len(report_paths)} 个产物，重复 {duplicated} 个')

    changed_total = 0
    for root, before_snapshot in before.items():
        after = snapshot(root)
        changed = sorted(k for k in set(before_snapshot) | set(after)
                         if before_snapshot.get(k) != after.get(k))
        changed_total += len(changed)
        record(f'{os.path.basename(root)} 目录未被改动',
               'OK' if not changed else 'FAIL',
               f'{len(before_snapshot)} 个文件，变化 {len(changed)} 个')

    failed = [r for r in _results if r['status'] == 'FAIL']
    print('\n=== 汇总 ===')
    for entry in _results:
        print(f"{entry['status']:^7}  {entry['item']}")
    print(f'\nOK {len([r for r in _results if r["status"] == "OK"])} / '
          f'FAIL {len(failed)} / UNKNOWN '
          f'{len([r for r in _results if r["status"] == "UNKNOWN"])}')
    print(json.dumps([r for r in _results if r['status'] != 'OK'],
                     ensure_ascii=False))
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
