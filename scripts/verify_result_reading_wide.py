# -*- coding: utf-8 -*-
r"""
广域结果读取核验：把本库的读取 API 跑在**一大批真实工程**上（离线、只读）
==========================================================================

为什么需要：单工程验证只能证明「那条路径能走通」，而结果树的形态差异很大
（1 端口 / 3 端口 / 只有材料色散曲线 / 带收敛监控 / 带远场 1D 项…）。
本脚本按家族抽样，对每个工程跑**同一套动作**，逐项判定：

============================  ====================================================
``Result(path)``              能否打开（`cst.results` 离线读，不启动 CST）
``list_s_parameters()``       不变式：返回的**每个**名字都必须能 `read_s_parameter()` 读出
``read_all_s_parameters()``   条目数与声明一致，长度非零
``export_s_parameters_csv()`` 行数 = 点数 + 1；表头含全部 S 参数名
``ResultReader``              用**自动发现的名字**取峰位置（`names[0]` 不再炸）
``cst_result_probe / 指纹``   `run_contract` 能在真实输出上算出结果
============================  ====================================================

已知且**刻意容忍**的两种情况（会记为 OK/UNKNOWN 而不是 FAIL）：

* 工程里**本来就没有** S 参数结果（例如 `Ant1_epc_mf_AB.cst` 只有材料色散曲线）
  —— `list_s_parameters() == []` 是正确结果，不是失败；
* `1D Results\farfield (f=…)` 这类条目在部分工程上打不开
  （见 [P4 记录 §8.3](../docs/validation/p4_real_machine_evidence.md)）——
  它不在本脚本的动作集里，只在报告里提示。

全程**只读**：每个家族目录前后快照必须一致。

用法::

    python scripts/verify_result_reading_wide.py                 # 默认抽样
    python scripts/verify_result_reading_wide.py --max 30        # 多抽几个
    python scripts/verify_result_reading_wide.py --family Leaky  # 只跑一个家族
"""

import argparse
import glob
import json
import os
import sys
import tempfile

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

BASE_DEFAULT = r'D:\成电博士生涯\拓扑光子晶体模型\硅基'
FAMILIES_DEFAULT = ('普通单元天线', 'Leaky', 'MPMBA', '多端口', '开关尝试')
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


def check_project(path, tmpdir):
    """
    对一个工程跑完整动作集。

    :param path: str, .cst 路径
    :param tmpdir: str, CSV 临时目录
    :return: list[dict], 该工程的问题（空列表 = 全过）
    """
    from cst_solver import Result
    from cst_solver.run_contract import cst_result_probe, result_fingerprint
    from topo_modeler.result_reader import ResultReader

    name = os.path.basename(path)
    problems = []
    result = Result(path)

    declared = result.list_s_parameters()
    for s_name in declared:
        try:
            if len(result.read_s_parameter(s_name, 0)) == 0:
                problems.append(f'{s_name} 读到 0 点')
        except Exception as exc:                       # noqa: BLE001
            problems.append(f'{s_name} 读失败 {type(exc).__name__}')

    if not declared:
        # 没有 S 参数结果不是失败（工程可能只算了材料/收敛类曲线）
        return problems, {'s_params': [], 'points': 0, 'note': '该工程没有 S 参数结果'}

    data = result.read_all_s_parameters(run_id=0)
    if sorted(data) != sorted(declared):
        problems.append(f'read_all 返回 {sorted(data)}，声明 {declared}')
    lengths = sorted({len(v) for v in data.values()})
    if not lengths or lengths[0] == 0:
        problems.append(f'读到的点数为空：{lengths}')

    out = os.path.join(tmpdir, f'{name}.csv')
    result.export_s_parameters_csv(out, run_id=0, names=declared)
    with open(out, encoding='utf-8-sig', errors='replace') as handle:
        rows = handle.read().splitlines()
    if len(rows) != lengths[0] + 1:
        problems.append(f'CSV 行数 {len(rows)} ≠ 点数 {lengths[0]} + 1')
    header = rows[0] if rows else ''
    for s_name in declared:
        if s_name not in header:
            problems.append(f'CSV 表头缺 {s_name}：{header!r}')

    reader = ResultReader(path, names=declared, run_id=0)
    try:
        reader.peak_position(declared[0], kind='min')     # 曾经会被收敛曲线带偏
    except Exception as exc:                           # noqa: BLE001
        problems.append(f'peak_position({declared[0]}) 失败：{type(exc).__name__}')

    probe = cst_result_probe(path)
    if 'error' in probe:
        problems.append(f'cst_result_probe 报错：{probe["error"][:60]}')
    if not result_fingerprint(path):
        problems.append('result_fingerprint 为空')

    return problems, {'s_params': declared, 'points': lengths[0],
                      'run_ids': probe.get('run_ids')}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', default=BASE_DEFAULT)
    parser.add_argument('--family', action='append', default=None,
                        help='只跑指定家族（可重复）')
    parser.add_argument('--max', type=int, default=25, help='最多抽查多少个工程')
    parser.add_argument('--cst-root', default=os.environ.get('CST_INSTALL_PATH',
                                                             DEFAULT_CST_ROOT))
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    lib = os.path.join(args.cst_root, 'AMD64', 'python_cst_libraries')
    if os.path.isdir(lib) and lib not in sys.path:
        sys.path.insert(0, lib)
    if not os.path.isdir(args.base):
        record('参考工程根目录', 'UNKNOWN', f'不存在：{args.base}')
        print('\nUNKNOWN 1（没有参考工程，跳过）')
        return 0

    families = tuple(args.family) if args.family else FAMILIES_DEFAULT
    # ① 递归找（`多端口` / `开关尝试` 的工程在子目录里，顶层 `*.cst` 是 0 个）
    # ② 家族间**轮流取**，这样某个家族项目少时，别的家族能补上——否则固定切片
    #    会把多端口工程（Ant3_*）全部挡在门外，抽查里就永远看不到 >2 端口的例子
    per_family = []
    for family in families:
        folder = os.path.join(args.base, family)
        found = [p for p in sorted(glob.glob(os.path.join(folder, '**', '*.cst'),
                                             recursive=True))
                 if not os.path.basename(p).startswith('tmp')]
        record(f'家族 {family}', 'OK' if found else 'UNKNOWN', f'{len(found)} 个工程')
        per_family.append((family, found))

    projects = []
    index = 0
    while len(projects) < max(1, args.max):
        added = False
        for _family, found in per_family:
            if index < len(found) and len(projects) < max(1, args.max):
                projects.append(found[index])
                added = True
        if not added:
            break
        index += 1
    if not projects:
        record('可抽查工程', 'UNKNOWN', '一个都没有')
        print('\nUNKNOWN 1（没有可抽查的工程）')
        return 0

    before = {family: snapshot(os.path.join(args.base, family))
              for family in families if os.path.isdir(os.path.join(args.base, family))}
    tmpdir = tempfile.mkdtemp(prefix='tpc_wide_csv_')
    total_problems = 0
    multi_port = []
    no_s_params = []
    try:
        for path in projects:
            name = os.path.basename(path)
            try:
                problems, info = check_project(path, tmpdir)
            except Exception as exc:                   # noqa: BLE001
                problems, info = [f'{type(exc).__name__}: {str(exc)[:80]}'], {}
            total_problems += len(problems)
            if len(info.get('s_params', [])) > 2:
                multi_port.append(f'{name}({len(info["s_params"])} 个)')
            if not info.get('s_params'):
                no_s_params.append(name)
            detail = (f"{len(info.get('s_params', []))} 个 S 参数，"
                      f"{info.get('points', 0)} 点" if info.get('s_params')
                      else info.get('note', '无数据'))
            record(f'工程 {name}', 'FAIL' if problems else 'OK',
                   detail + (f" | 问题：{'; '.join(problems)}" if problems else ''))
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)

    record('多端口工程（>2 个 S 参数）', 'OK' if multi_port else 'UNKNOWN',
           f'{multi_port or "抽查里没有多端口工程"}')
    record('没有 S 参数的工程（应如实为空）', 'OK',
           f'{no_s_params or "抽查里没有"}')

    changed_total = 0
    for family, before_snapshot in before.items():
        after = snapshot(os.path.join(args.base, family))
        changed = sorted(k for k in set(before_snapshot) | set(after)
                         if before_snapshot.get(k) != after.get(k))
        changed_total += len(changed)
        record(f'家族 {family} 目录未被改动', 'OK' if not changed else 'FAIL',
               f'{len(before_snapshot)} 个文件，变化 {len(changed)} 个')

    failed = [r for r in _results if r['status'] == 'FAIL']
    print('\n=== 汇总 ===')
    print(f'抽查工程 {len(projects)} 个，问题 {total_problems} 条；'
          f'FAIL 项 {len(failed)}')
    print(f'\nOK {len([r for r in _results if r["status"] == "OK"])} / '
          f'FAIL {len(failed)} / UNKNOWN '
          f'{len([r for r in _results if r["status"] == "UNKNOWN"])}')
    print(json.dumps([r for r in _results if r['status'] != 'OK'],
                     ensure_ascii=False))
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
