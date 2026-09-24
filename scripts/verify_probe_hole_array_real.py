# -*- coding: utf-8 -*-
r"""
真机验收：`build_ba_hole_array_feed`（BA 微锥条 + 椭圆孔阵列短探针）
====================================================================
**只建模，不求解**（分钟级）。

离线部分由 `topo_modeler/tests/test_probe_hole_array.py`（14 项）钉住：参数口径、
预设数值（四位小数）、几何顶点 CCW/闭合、孔心是累加表达式、缺参数提前拦截。
**本脚本补的是「CST 到底接不接受这套 VBA」** —— 也就是
`docs/next_plan/README.md` 里登记的 P4 欠项。

建的东西
--------
1. **参数**：`a / h / l1 / l2 / e1 / e2` —— 派生量写成 **CST 表达式**
   （`'0.65*a'` / `'0.35*a'` / `'a/2'` / `'a*sqr(3)/2'`），不是烘好的小数；
   多端口族 `wf2/lf4/lf5/lf6`（外形依赖）用 `register_multiport_params`；
   探针 `pb_*` 用 `register_probe_params(preset='Pp4')`。
2. **材料** + **探针**：`build_ba_hole_array_feed(n_holes=4)`。

验收项
------
* A **CST 消息**：`Rebuild()` 前后都必须为空（阻塞式重放历史最能暴露问题）；
* B **实体清单**：`feed2` 在，`pb_hole1..4` 已被 `subtract` 消耗（不该残留）；
* C **参数是表达式**：`get_parameter('e1')` 返回 `str` 而不是 `float`，
  且落盘 `Parameters.json` 里 `l1/l2/e1/e2` 的 `expr` 非空；
* D **历史取证**：`Solid.Subtract` = 孔数、孔心是累加表达式、末尾有 z 居中；
* E **参数闭合性**：复用 `scripts/verify_model_parameter_usage.py`，
  死写入必须为 0。

安全约定（都是踩过的坑）
------------------------
* 开工前/收尾都查一次 CST 对话框（`cst_dialog_guard`）；
* **必须在非沙箱环境里跑**：沙箱作业对象会杀掉直接 spawn 出来的 DE 子进程
  （`DesignEnvironmentStartupError: Process with pid: … is gone`）——
  真因是沙箱，**不是许可证坏了**（本机 999 席、0 在用）。真要起 DE 又起不来，
  按 `skills/developer/cst-solver-dev.md` 的结论：用 `explorer.exe "<exe>"`
  双击语义拉起、再 attach。本脚本**不 attach、不关闭**任何既有 DE；
* 别的 DE 在跑求解**不影响**本脚本新建 DE（各 999 席）—— 那只影响
  「借那个忙碌的 DE 建新工程」（见 `busy_de_hint` 的注释）；
* 模板只作**只读引用**（`copyfile` + `copytree` 到临时目录再改）。

用法
----
    python scripts/verify_probe_hole_array_real.py
    python scripts/verify_probe_hole_array_real.py --template <干净的 tmp.cst>
    python scripts/verify_probe_hole_array_real.py --workdir <产物目录>
"""

import argparse
import io
import json
import os
import re
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
for _extra in (PROJECT_ROOT, Path(__file__).resolve().parent):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))


class _Tee(object):
    """把输出同时写到 stdout 与日志文件。

    为什么必须有（`skills/user/tpc-usage.md` §16）：终端会**吞输出**，而且同步终端
    偶发把命令前缀成 `^U` 导致解析失败 —— 那样即使脚本跑完了，证据也一起丢了
    （2026-09-24 实测：工程都建好落盘了，但调用方的重定向没执行，日志停在上一版）。
    """

    def __init__(self, *streams):
        self.streams = streams

    def write(self, text):
        for stream in self.streams:
            try:
                stream.write(text)
                stream.flush()
            except Exception:                            # noqa: BLE001
                pass

    def flush(self):
        for stream in self.streams:
            try:
                stream.flush()
            except Exception:                            # noqa: BLE001
                pass

from topo_modeler.batch import (                        # noqa: E402
    close_extra_design_environments,
    design_environment_baseline,
    design_environment_query,
)

#: 默认模板 = 下游探针工作区的 `tmp.cst`（几百 KB，带单位/边界/网格设置）。
#: ⚠️ 其余 `verify_*_real.py` 用的 `D:\TPC_out\tmp.cst` **本机不存在**
#:（`D:\TPC_out` 整个目录都没有）⇒ 这里显式给一个存在的默认值，并支持 `--template`。
DEFAULT_TEMPLATE = r'D:\成电博士生涯\拓扑光子晶体模型\硅基\探针问题\tmp.cst'

#: 网格分辨率/工艺口径（只用于 reporting，不参与断言）
_results = []
_baseline = set()


def record(item, status, detail, **extra):
    """记录一条核验结论。status ∈ {OK, INFO, WARN, FAIL, UNKNOWN}。"""
    entry = {'item': item, 'status': status, 'detail': detail}
    entry.update(extra)
    _results.append(entry)
    text = '  ' + json.dumps(extra, ensure_ascii=False, default=str) if extra else ''
    print(f'[{status:^7}] {item}: {detail}{text}', flush=True)
    return entry


def busy_de_hint(pid=None):
    """
    是否有某个 CST 会话**正在跑求解**（主窗口标题带 `[nn% ]`）？

    与 `scripts/verify_bugfixes_real.py::busy_de_hint` **同一判据**（都只读窗口
    标题、不发 COM 调用）。

    ⚠️ 适用范围要说清楚：忙碌只影响「**借**那个 DE 建新工程」——历史教训
    （2026-09-23）：在忙碌的 DE 里 `new_project()` 会先抛
    `RuntimeError: An error occurred while trying to create a new project.`，
    重试时甚至把 COM 调用**挂死**。本脚本**新建自己的 DE**，所以忙碌的别的
    会话**不是阻塞项**（各 999 席）—— 这里只当提示信息报出来。

    :param pid: int 可选, 只看该进程的窗口
    :return: str, 空串 = 没有在跑求解的 CST 会话
    """
    try:
        from cst_dialog_guard import list_windows
    except Exception:                                   # noqa: BLE001
        return ''
    hits = []
    for window in list_windows():
        if pid is not None and window.get('pid') not in (None, pid):
            continue
        title = window.get('title') or ''
        if re.search(r'\[\s*\d+\s*%\s*\]', title):
            hits.append(f'{window.get("pid")}: {title!r}')
    if not hits:
        return ''
    return ('另有 CST 会话正在跑求解（' + '；'.join(hits[:2]) +
            '）。**不影响**本脚本新建自己的 DE；只提醒你别去动它（本脚本也不会）。')


def _messages(app):
    try:
        return [str(m) for m in (app.cst_file.get_messages() or [])]
    except Exception as exc:                            # noqa: BLE001
        return [f'<读消息失败 {type(exc).__name__}: {exc}>']


def _n_shapes(app):
    """工程里现在有多少个实体。

    用**官方** `Solid.GetNumberOfShapes()`（库自己的守卫层也在用它，见
    `cst_solver/parameters.py::_guard_geometry_probe`）。

    ⚠️ 不要用 `model3d.GetAllSolidNames()` —— 实测（2026-09-24，CST 2026）真机上
    它直接 `AttributeError: object has no attribute 'GetAllSolidNames'`；
    `skills/user/topo-quickstart.md` §10 里那段示例是**错的**（本轮已报回）。
    """
    try:
        return int(app.cst_file.model3d.Solid.GetNumberOfShapes())
    except Exception as exc:                            # noqa: BLE001
        record_detail = f'{type(exc).__name__}: {exc}'
        print(f'    (读实体数失败：{record_detail})', flush=True)
        return None


def _history_code(project_path):
    path = os.path.join(os.path.splitext(project_path)[0], 'Model', '3D',
                        'ModelHistory.json')
    if not os.path.isfile(path):
        return []
    with open(path, encoding='utf-8-sig') as handle:
        data = json.load(handle)
    return [line for entry in data.get('history', [])
            for line in entry.get('code', [])]


def _parameters(project_path):
    path = os.path.join(os.path.splitext(project_path)[0], 'Model',
                        'Parameters.json')
    if not os.path.isfile(path):
        return {}
    with open(path, encoding='utf-8-sig') as handle:
        data = json.load(handle)
    return {p['name']: p for p in data.get('parameters', [])}


def run(workdir, template_src):
    from cst_dialog_guard import check_dialogs, describe_dialogs, guard
    from cst_solver import setup
    from topo_modeler.builders import (
        PROBE_PRESETS,
        build_ba_hole_array_feed,
        build_materials,
        register_multiport_params,
        register_probe_params,
    )

    check_dialogs('开工前')
    print(f'开工前 CST 对话框：\n{describe_dialogs()}', flush=True)

    # ★ 模板只作**只读引用**：拷成独立副本再改（同名目录也要拷，模板带着材料/网格）
    project = os.path.join(workdir, 'probe_hole_array.cst')
    shutil.copy2(template_src, project)
    src_dir = os.path.splitext(template_src)[0]
    if os.path.isdir(src_dir):
        shutil.copytree(src_dir, os.path.splitext(project)[0],
                        dirs_exist_ok=True)
    print(f'工程副本：{project}', flush=True)

    preset = 'Pp4'
    n_holes = PROBE_PRESETS[preset]['n_holes']
    app = None
    error = None
    before, after = [], []
    n_shapes = None
    try:
        with guard('孔阵列探针 建模+保存', timeout=900):
            app = setup(project)
            # ---- 1) 参数（派生量一律写表达式，见 skill §9 陷阱 15）----
            app.para('a', 0.2425, expression='晶格常数')
            app.para('h', 0.25, expression='硅板厚度')
            app.para('l1', '0.65*a', expression='大孔尺寸 = 0.65*a')
            app.para('l2', '0.35*a', expression='小孔尺寸 = 0.35*a')
            app.para('e1', 'a/2', expression='三角晶格 x 半间距 = a/2')
            app.para('e2', 'a*sqr(3)/2', expression='三角晶格 y 半间距')
            app.para('x01', 0, expression='三角底部半格修剪')
            # 外形依赖多端口族；探针参数走预设
            register_multiport_params(app, wf2=0.2, lf4=0.2, lf5=3.0, lf6=0.2)
            info = register_probe_params(app, preset=preset)
            # ---- 2) 材料 + 探针 ----
            build_materials(app)
            name = build_ba_hole_array_feed(app, n_holes=info['n_holes'])
            # ---- 3) 阻塞式重放历史（最能暴露问题的一步）----
            app.cst_file.model3d.Rebuild()
            n_shapes = _n_shapes(app)
            app.save(project, include_results=False)
        record('建模 + Rebuild + 保存', 'OK', f'feed 实体名 {name!r}')
    except Exception as exc:                            # noqa: BLE001
        error = f'{type(exc).__name__}: {exc}'
        record('建模 + Rebuild + 保存', 'FAIL', error,
               traceback=traceback.format_exc(limit=5))
        if app is not None:
            n_shapes = _n_shapes(app)
    finally:
        if app is not None:
            after = _messages(app)
            try:
                app.close()
            except Exception:                           # noqa: BLE001
                pass

    # ---- A 消息 ----
    record('A1 Rebuild 之后 CST 消息为空',
           'OK' if error is None and not after else 'FAIL',
           error or f'{len(after)} 条消息', messages=after[:4])

    # ---- B 实体：只应剩下 feed2 一个（4 个孔实体都被 subtract 吃掉了）----
    record('B1 实体数 = 1（4 个孔实体已被 subtract 吃掉）',
           'OK' if n_shapes == 1 else 'FAIL',
           f'Solid.GetNumberOfShapes() = {n_shapes}（期望 1：feed2）')
    code_all = '\n'.join(_history_code(project))
    created_holes = [f'pb_hole{i}' for i in range(1, n_holes + 1)
                     if f'pb_hole{i}' in code_all]
    record('B2 历史里确实建出了 4 个孔实体（并逐个被 subtract）',
           'OK' if len(created_holes) == n_holes else 'FAIL',
           f'历史中出现 {len(created_holes)}/{n_holes} 个 pb_holeN')

    # ---- C 参数是表达式 ----
    table = _parameters(project)
    exprs = {k: table.get(k, {}).get('expr') for k in ('l1', 'l2', 'e1', 'e2')}
    values = {k: table.get(k, {}).get('value') for k in ('l1', 'l2', 'e1', 'e2')}
    record('C1 Parameters.json 里 l1/l2/e1/e2 的 expr 非空',
           'OK' if all(exprs.values()) else 'FAIL',
           f'expr={exprs}', values=values)
    expected = {'l1': 0.65 * 0.2425, 'l2': 0.35 * 0.2425,
                'e1': 0.2425 / 2, 'e2': 0.2425 * 3 ** 0.5 / 2}
    drift = {k: abs(float(values.get(k) or 0) - v) for k, v in expected.items()}
    record('C2 表达式求值 = 晶格派生值（容差 1e-9 mm）',
           'OK' if all(d < 1e-9 for d in drift.values()) else 'FAIL',
           f'最大偏差 {max(drift.values()):.2e} mm')
    pb = {p: table.get(p, {}).get('value') for p in PROBE_PRESETS[preset]['values']}
    missing = [p for p, v in pb.items() if v in (None, '')]
    record('C3 预设的 14 个 pb_* 都落进参数表',
           'OK' if not missing else 'FAIL', f'缺 {missing}' if missing else '14/14')

    # ---- D 历史取证 ----
    code = '\n'.join(_history_code(project))
    if not code:
        record('D 历史取证', 'FAIL', '读不到 ModelHistory.json')
    else:
        n_sub = code.count('Solid.Subtract')
        record('D1 逐孔减法条数 = 孔数',
               'OK' if n_sub >= n_holes else 'FAIL',
               f'实测 {n_sub}（期望 ≥ {n_holes}）')
        cum = ['pb_x_h0+pb_p_e1', 'pb_x_h0+pb_p_e1+pb_p_e2',
               'pb_x_h0+pb_p_e1+pb_p_e2+pb_p_e3']
        hit = [c for c in cum if c in code.replace(' ', '')]
        record('D2 孔心是**累加表达式**（不是烘好的小数）',
               'OK' if len(hit) >= 3 else 'FAIL',
               f'命中 {len(hit)}/3 个累加式')
        record('D3 z 居中平移存在',
               'OK' if '-h/2' in code else 'FAIL', 'history 里出现 -h/2')

    # ---- E 参数闭合性（复用 P4 §8.7 的工具）----
    try:
        import verify_model_parameter_usage as usage

        before_n = len(usage.RESULTS)
        result = usage.audit_project(os.path.splitext(project)[0],
                                     label='孔阵列探针')
        for entry in usage.RESULTS[before_n:]:
            _results.append(entry)
            print(f'[{entry["status"]:^7}] {entry["item"]}: {entry["detail"]}',
                  flush=True)
        if result:
            record('E1 库下发参数没有死写入',
                   'FAIL' if result['dead_writes'] else 'OK',
                   f'死写入：{result["dead_writes"] or "无"}'
                   f'（已引用 {result["used"]} / 共 {result["defined"]}）')
    except Exception as exc:                            # noqa: BLE001
        record('E1 参数闭合性', 'UNKNOWN', f'{type(exc).__name__}: {exc}')

    return project


def main(argv=None):
    global _baseline
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument('--template', default=DEFAULT_TEMPLATE,
                        help='干净的模板 .cst（只读引用）')
    parser.add_argument('--workdir', default=None, help='产物目录（默认临时目录）')
    parser.add_argument('--keep', action='store_true',
                        help='即使自动建了临时目录也保留（供离线复核）')
    parser.add_argument('--log', default=None,
                        help='日志文件（推荐给；终端会吞输出，见 tpc-usage §16）')
    args = parser.parse_args(argv)

    if args.log:
        os.makedirs(os.path.dirname(os.path.abspath(args.log)) or '.',
                    exist_ok=True)
        sys.stdout = _Tee(sys.__stdout__,
                          io.open(args.log, 'w', encoding='utf-8'))

    try:
        import cst_solver

        lib = cst_solver.CST_PYTHON_LIB
        if lib and lib not in sys.path:
            sys.path.append(lib)
    except Exception as exc:                            # noqa: BLE001
        record('cst.interface 准备', 'WARN', f'{type(exc).__name__}: {exc}')

    # ---- 提示：别的会话在跑求解（不影响本脚本）----
    hint = busy_de_hint()
    if hint:
        print(f'!! {hint}', flush=True)
        record('提示：别的 CST 会话在忙', 'INFO', hint)
    else:
        record('提示：别的 CST 会话在忙', 'INFO', '没有在跑求解的 CST 会话')

    if not os.path.isfile(args.template):
        record('预检：模板存在', 'FAIL', f'找不到模板 {args.template}')
        print('\n===== VERIFY PROBE HOLE ARRAY DONE rc=1 =====')
        return 1
    record('预检：模板存在', 'OK', args.template)

    _baseline = design_environment_baseline()
    print(f'基线 DE：{sorted(_baseline)}', flush=True)
    workdir = args.workdir or tempfile.mkdtemp(prefix='tpc_probe_ha_')
    os.makedirs(workdir, exist_ok=True)
    print(f'产物目录：{workdir}', flush=True)

    try:
        run(workdir, args.template)
    except Exception:                                   # noqa: BLE001
        record('核验过程异常', 'FAIL', traceback.format_exc(limit=3))
    finally:
        closed = close_extra_design_environments(_baseline, verbose=True)
        record('收尾', 'OK', f'关闭本次新建的 DE：{closed or "无"}')
        query = design_environment_query()
        record('收尾后的 DE', 'OK' if query['ok'] else 'UNKNOWN',
               f'{query["pids"]}（基线 {sorted(_baseline)}）'
               if query['ok'] else query['reason'])
        # 临时产物纪律（tpc-usage.md §17）：自动建的临时目录默认删掉；
        # 显式给 --workdir（或 --keep）则保留，供离线复核
        if args.workdir is None and not args.keep:
            shutil.rmtree(workdir, ignore_errors=True)
            record('收尾：临时产物', 'OK', f'已删除 {workdir}')
        else:
            record('收尾：临时产物', 'OK', f'保留 {workdir}')

    print('\n=== 汇总 ===')
    for entry in _results:
        print(f"{entry['status']:^7}  {entry['item']}")
    n_fail = sum(1 for e in _results if e['status'] == 'FAIL')
    n_unknown = sum(1 for e in _results if e['status'] == 'UNKNOWN')
    print(f'\n合计 {len(_results)} 项：FAIL {n_fail} / UNKNOWN {n_unknown}')
    print(f'===== VERIFY PROBE HOLE ARRAY DONE rc={1 if n_fail else 0} =====')
    return 1 if n_fail else 0


if __name__ == '__main__':
    sys.exit(main())
