# -*- coding: utf-8 -*-
"""
P4/V1 事实核验：UnitAntenna 的阵列范围与路径参数映射
====================================================

用途：在**装有 CST 的机器上**跑一次，核对 `UnitAntenna` 的阵列范围（xup/yup/ydn）
与路径参数是否与旧 notebook（`Ant1_D_{AB,BA}_120D_*`）的约定一致。
本脚本只做事实核验与取证，不改库代码；结论回填
`docs/validation/p4_real_machine_evidence.md` 的 V1 节。

旧 notebook 的权威取值（从参考工程 `普通单元天线\Ant1_D_{AB,BA}_120_Feed_antenna-DF`
的 Parameters.json 与对应 ipynb 读出）
--------------------------------------------------------------------
=========================  ==========================  =========================
                           AB（臂朝 +y）                BA（臂朝 −y）
=========================  ==========================  =========================
路径点（格点 r,c）         (0,-1)→(0,18)→(14,18)       (0,-1)→(0,18)→(−14,32)
臂端物理坐标 (x,y)         (6.0625, **+2.9402**)       (6.0625, **−2.9402**)
`xup`                      `x1+int(y1/2)` = **25**      `x1+int(y1/2)+1` = **26**
`yup` / `ydn`              `y1` = **14** / **14**       `y1` = **14** / **14**
`xmax`                     `a*x1+y1*e1+e1` = 6.18375   `a*x1+e1` = 4.48625
=========================  ==========================  =========================

（x1=18 直段周期数、y1=14 臂长；阵列步长 `e2*2`，重复次数 `int(yup/2)`。）

⚠️ **`bend_angle` 是张角**（两侧臂夹角）= 2 × 单臂偏角，与 notebook 文件名一致：
`--bend 120` ⇒ 单臂 ±60°（= 参考 120D）、`--bend 240` ⇒ 单臂 ±120°（= 参考 240D）。
臂端与参考工程的 px3/py3 由本脚本**逐位比对**（2026-09-17 语义修正后的回归）。

**一次会话关掉两个待办**：本脚本默认还会在同一次 CST 会话里顺带跑「求解控制 API 探针」
（P2 待办的 `probe_solver_control_api.py --live` 那一步），因此

```text
python scripts/verify_antenna_mapping.py            # AB + BA 建模核验 + 求解控制 API 探针
```

一条命令即可同时收掉 V1 的新臂方向复验与「CST 取消/停止接口核实」的真机那一步。
不需要探针时加 `--no-solver-api-probe`。

用法
----
    python scripts/verify_antenna_mapping.py [--topology AB] [--bend 120]

注意
----
只新建**空白工程**（从干净模板复制到临时目录），不打开、不修改既有工程；
收尾关闭 DE（只关本次自己开出来的）。
"""

import argparse
import json
import os
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from topo_modeler.batch import (                    # noqa: E402
    close_extra_design_environments,
    design_environment_baseline,
)

CLEAN_TEMPLATE = r'D:\TPC_out\tmp.cst'              # 模板（⚠️ **并不干净**：自带旧工程
#   的 77 项参数，含 `x1=8 / y1=8 / xup=37 / ymax_*` 与一个求值为空的死参数
#   `N=(y0+4)*2`。2026-09-17 之前这里写的是「只含单位/边界/网格设置」，与实测不符；
#   参数闭合性由 scripts/verify_model_parameter_usage.py 审计，见 P4 证据 §8.7）
PARAM_TEMPLATE = r'D:\TPC_out\tmp'                  # 同一模板的**文件夹形式**（离线可读参数表）
STRAIGHT, ARM, BEND = 18, 14, 120
# 参考工程 Parameters.json 的**臂端实测值**（bend_angle=120 ⇒ 单臂偏角 60°）
#   AB: px3=6.0625, py3=+2.94015624584816   BA: px3=6.0625, py3=-2.94015624584816
REF_ARM_END = {'AB': (6.0625, +2.94015624584816),
               'BA': (6.0625, -2.94015624584816)}
# 参考工程历史里阵列复制的写法（`ModelHistory.json` 原文），必须逐字出现：
# 我们此前是 `int(25)` / `int(14/2)`，参数表里的 xup/yup/ydn 一次都没被引用。
REF_ARRAY_EXPRESSIONS = ('int(xup)', 'int(yup/2)', 'int(ydn/2)')
_results = []
_baseline = set()
_solver_probe_done = False
_probe_solver_api = True
_param_usage = True


def record(item, status, detail, **extra):
    entry = {'item': item, 'status': status, 'detail': detail}
    entry.update(extra)
    _results.append(entry)
    print(f'[{status:^7}] {item}: {detail}', flush=True)


def expected(topology):
    """旧 notebook 的期望值。"""
    xup = STRAIGHT + int(ARM / 2) + (1 if topology == 'BA' else 0)
    return {'xup': xup, 'yup': ARM, 'ydn': ARM}


def check_parameter_usage(output, topology):
    """核对建成工程的「参数表 ↔ 建模历史」闭合性（2026-09-17 修复后的回归）。

    两件事：

    1. **阵列次数必须是参数引用**：历史里要出现参考工程那三条原文
       `int(xup)` / `int(yup/2)` / `int(ydn/2)`。修复前是 `int(25)` / `int(14/2)`，
       整份历史里 `xup|yup|ydn` 出现 **0 次**（真机取证见 P4 证据 §8.7）。
    2. **完整闭合性审计**：复用 `verify_model_parameter_usage.py` ——
       未定义引用、死写入（本次写过却没人用的参数）都算 FAIL。
    """
    import verify_model_parameter_usage as usage

    # ⚠️ 必须走 resolve_project：CST 保存出来的是**文件夹形式**工程
    #    （`ant_AB_120.cst\Model\...`），拿 `output` 直接拼 `Model\3D` 会找不到文件，
    #    于是历史读成空、检查全报「缺 int(xup)」——2026-09-17 真机踩过一次假 FAIL。
    project = usage.resolve_project(output)
    history_path = os.path.join(project, 'Model', '3D', 'ModelHistory.json')
    texts = []
    if os.path.isfile(history_path):
        with open(history_path, encoding='utf-8-sig') as handle:
            def walk(node):
                if isinstance(node, str):
                    texts.append(node)
                elif isinstance(node, dict):
                    for value in node.values():
                        walk(value)
                elif isinstance(node, (list, tuple)):
                    for value in node:
                        walk(value)
            walk(json.load(handle))
    blob = '\n'.join(texts)
    missing = [expr for expr in REF_ARRAY_EXPRESSIONS if expr not in blob]
    record(f'{topology} 阵列次数是参数引用', 'OK' if not missing else 'FAIL',
           f'历史 {len(texts)} 条字符串里三条参考写法齐全（{", ".join(REF_ARRAY_EXPRESSIONS)}）'
           if not missing else
           f'历史 {len(texts)} 条字符串里缺 {missing}（阵列被烘成数字，改参数不动几何）',
           history=history_path)

    template_table, template_path = usage.load_parameters(PARAM_TEMPLATE)
    if template_table is None:
        record(f'{topology} 参数闭合性审计', 'UNKNOWN',
               f'模板参数表读不到，跳过对比：{template_path}')
        return
    before = len(usage.RESULTS)
    result = usage.audit_project(project, template_table,
                                 label=f'{topology} 参数闭合')
    for entry in usage.RESULTS[before:]:                   # 并入本脚本的汇总并打印
        _results.append(entry)
        print(f'[{entry["status"]:^7}] {entry["item"]}: {entry["detail"]}',
              flush=True)
    if result is not None:
        record(f'{topology} 死写入', 'FAIL' if result['dead_writes'] else 'OK',
               f'库写过却没人引用的参数：{result["dead_writes"] or "无"}'
               f'（已引用 {result["used"]} / 共 {result["defined"]}）')


def probe(topology, outdir):
    """构建一次 UnitAntenna 并取证。"""
    from topo_templates import UnitAntenna
    from cst_dialog_guard import (check_dialogs, describe_dialogs,
                                  describe_windows, guard, save_prompts)

    template = os.path.join(outdir, 'tmp.cst')
    if not os.path.exists(template):
        shutil.copy2(CLEAN_TEMPLATE, template)
    output = os.path.join(outdir, f'ant_{topology}_{BEND}.cst')

    messages = []
    error = None
    ant = None
    try:
        # 开工前先看有没有残留弹窗（模态弹窗会让下一次 CST 调用永久阻塞）
        check_dialogs(f'{topology} 开工前')
        print(f'{topology} 建模前 CST 对话框：\n{describe_dialogs()}', flush=True)
        # 构造 + 建模 + 保存都是重步骤：卡住要能报出「哪一步 + 当时的窗口快照」，
        # 而不是无声挂死（2026-09-17 用户被「是否保存更改？」弹窗拦住的教训）
        with guard(f'{topology} 构造+建模+保存', timeout=900):
            ant = UnitAntenna(bend_angle=BEND, straight_length=STRAIGHT,
                              arm_length=ARM, topology=topology,
                              template_cst=template, output_path=output)
            path = ant.path
            lattice = list(path.path_lattice)
            # ⚠️ 模板真正下发给 CST 的是 ant.xup/yup/ydn；path.get_array_range()
            #    是修复前用的推导方式，这里一并记录以便对照
            arr = (ant.xup, ant.yup, ant.ydn)
            record(f'{topology} 路径（库算）', 'OK',
                   f'lattice={lattice}',
                   template_array_range=list(arr),
                   get_array_range=list(path.get_array_range()),
                   expected=expected(topology))
            # `bend_angle` 是张角：单臂偏角 = bend/2，符号按拓扑取 ——
            # 臂端必须与参考工程的 px3/py3 逐位一致（离线可比，见证据 §4.5）
            end_x, end_y = path.xy[-1]
            ref_x, ref_y = REF_ARM_END[topology]
            arm_ok = (abs(end_x - ref_x) < 1e-6 and abs(end_y - ref_y) < 1e-6)
            record(f'{topology} 臂端（张角语义）', 'OK' if arm_ok else 'FAIL',
                   f'库 ({end_x:.4f}, {end_y:.4f}) vs 参考工程 ({ref_x:.4f}, {ref_y:.4f})'
                   f'（bend={BEND} ⇒ 单臂偏角 {BEND // 2}°）')

            # 同一次会话顺带做「求解控制接口」探针（P2 待办的 `--live` 那一步）——
            # 这样两个待办一次 CST 会话就能都关掉，不必再单独起一次 CST。
            if _probe_solver_api and ant.app is not None:
                global _solver_probe_done
                if not _solver_probe_done:
                    try:
                        from probe_solver_control_api import probe_live_app
                        found = probe_live_app(ant.app)
                        present = [item['name'] for item in found if item['present']]
                        record('求解控制 API 探针（同一会话内）',
                               'OK' if present else 'UNKNOWN',
                               f'存在 {present or "无"}；共探 {len(found)} 个候选名字',
                               present=present,
                               absent=[i['name'] for i in found if not i['present']])
                        _solver_probe_done = True
                    except Exception as exc:                  # noqa: BLE001
                        record('求解控制 API 探针（同一会话内）', 'FAIL',
                               f'{type(exc).__name__}: {exc}')
            record(f'{topology} 阵列范围（库算 vs 旧 notebook）',
                   'OK' if tuple(arr) == tuple(expected(topology).values()) else 'FAIL',
                   f'库 {tuple(arr)} vs 期望 '
                   f'{(expected(topology)["xup"], expected(topology)["yup"], expected(topology)["ydn"])}')
            ant.build_all()
            messages = [str(m) for m in (ant.app.cst_file.get_messages() or [])]
            ant.save(output)
    except Exception as exc:                          # noqa: BLE001
        error = f'{type(exc).__name__}: {exc}'
        try:
            if ant is not None and ant.app is not None:
                messages = [str(m) for m in (ant.app.cst_file.get_messages() or [])]
        except Exception:                             # noqa: BLE001
            pass
    finally:
        try:
            if ant is not None:
                ant.close()
        except Exception:                             # noqa: BLE001
            pass
        # 关会话时 CST 可能弹「是否保存更改？」—— 不点会挂住后续脚本
        leftovers = save_prompts()
        if leftovers:
            record(f'{topology} 关会话后弹窗', 'FAIL',
                   f'{len(leftovers)} 个未处理弹窗：'
                   + '; '.join(repr(p['title']) for p in leftovers))
        print(f'{topology} 建模后 CST 窗口：\n{describe_windows()}', flush=True)

    record(f'{topology} 建模', 'OK' if error is None else 'FAIL',
           error or '未抛异常',
           n_messages=len(messages),
           messages=[m[:200] for m in messages[:2]])

    # 读磁盘上的参数表（不连 CST）
    params_path = os.path.join(os.path.splitext(output)[0], 'Model',
                               'Parameters.json')
    if os.path.isfile(params_path):
        data = json.load(open(params_path, encoding='utf-8-sig'))
        prm = {x['name']: x.get('value') for x in data['parameters']}
        got = {k: prm.get(k) for k in ('xup', 'yup', 'ydn', 'xmax')}
        record(f'{topology} 落盘参数', 'OK', json.dumps(got, ensure_ascii=False))
        for key, want in expected(topology).items():
            value = prm.get(key)
            ok = value is not None and float(value) == float(want)
            record(f'{topology} 参数 {key}', 'OK' if ok else 'FAIL',
                   f'实测 {value} vs 期望 {want}')
    else:
        record(f'{topology} 落盘参数', 'FAIL',
               f'没有产出参数表（工程没保存成功）：{params_path}')

    # 参数引用 vs 烘数值 + 闭合性审计（2026-09-17 修复后的回归；分钟级、纯离线读盘）
    if _param_usage:
        try:
            check_parameter_usage(output, topology)
        except Exception as exc:                          # noqa: BLE001
            record(f'{topology} 参数闭合性审计', 'FAIL',
                   f'{type(exc).__name__}: {exc}')
    return output


def main() -> int:
    global _baseline, BEND, _probe_solver_api, _param_usage
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--topology', default='both', choices=('AB', 'BA', 'both'))
    parser.add_argument('--bend', type=int, default=BEND)
    parser.add_argument('--no-solver-api-probe', action='store_true',
                        help='跳过「求解控制 API 探针」（默认在同一次会话里顺带做）')
    parser.add_argument('--no-param-usage', action='store_true',
                        help='跳过「参数引用/闭合性审计」（默认做，纯离线读盘）')
    args = parser.parse_args()
    BEND = args.bend
    _probe_solver_api = not args.no_solver_api_probe
    _param_usage = not args.no_param_usage

    _baseline = design_environment_baseline()
    print(f'基线 DE：{sorted(_baseline)}', flush=True)
    outdir = tempfile.mkdtemp(prefix='tpc_verify_ant_')
    print(f'产物目录：{outdir}', flush=True)
    topologies = ('AB', 'BA') if args.topology == 'both' else (args.topology,)
    try:
        for topology in topologies:
            probe(topology, outdir)
    except Exception:                                 # noqa: BLE001
        record('核验过程异常', 'FAIL', traceback.format_exc(limit=3))
    finally:
        closed = close_extra_design_environments(_baseline, verbose=True)
        record('收尾', 'OK', f'关闭本次新建的 DE：{closed or "无"}')

    print('\n=== 汇总 ===')
    for entry in _results:
        print(f"{entry['status']:^7}  {entry['item']}")
    failed = [r for r in _results if r['status'] == 'FAIL']
    print(f'\nOK {len([r for r in _results if r["status"] == "OK"])} / FAIL {len(failed)}')
    print(json.dumps(_results, ensure_ascii=False))
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
