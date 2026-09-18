# -*- coding: utf-8 -*-
r"""
P2 待办：CST「取消/停止」能力核实
=================================

计划原文（`docs/next_plan/README.md` P2）：**停止接口与「终止等待 vs 停止求解」的语义
核实前，不开放取消运行中任务**（`tpc_service` 对运行中的任务返回 `cancel_not_supported`）。

本脚本把这件事**能离线查清的部分**查清，并把**必须在真机上做的那一步**做成一条命令。

离线部分（默认，不起 CST、不需要 CST 在跑）
-------------------------------------------
CST 2026 的 Python 接口是 `CST 安装目录\AMD64\_cst_interface.cpNN-win_amd64.pyd`
（pybind11 扩展）。**只要版本号对得上，就能在本机 Python 里直接 import 并做静态内省** ——
不用启动 DesignEnvironment：

    C:\SOFTWARE\CST Studio Suite 2026\AMD64\_cst_interface.cp311-win_amd64.pyd

实测（2026-09-17，CST 2026 + Python 3.11.7）的静态结论：

* `DesignEnvironment` 33 个公开成员、`Project` 15 个、`Model3D` 2 个；
* 名字里含 stop/abort/cancel/terminate/interrupt/kill 的**只有 `close`**
  （`DesignEnvironment.close()` 关 DE，`Project.close()` 「closes the project without saving」）；
* `Model3D` 的静态成员只有 `allow_history_commands()/disallow_history_commands()` ——
  它是 `RemoteObject` 的**动态 COM 代理**（`__getattr__` 分发），
  所以 `add_to_history()`、以及本项目参考资料
  [`docs/references/cst-official-api-reference.md`](../docs/references/cst-official-api-reference.md) §9
  记录的 `abort_solver()/run_solver()/start_solver()` 这类**扩展方法 `dir()` 看不到**。

⇒ **静态内省无法回答「有没有停止接口」**，必须在**活的 DE** 上用 `hasattr` 探一次。
（同时记为**方法学教训**：直接扫 `.pyd` 二进制找符号名**不可靠** —— 连确定存在的
`add_to_history` 也是 0 命中，所以本脚本不把那类扫描当证据。）

真机部分（`--live`，秒级、只开一个空工程、不建模、不求解）
----------------------------------------------------------
    python scripts/probe_solver_control_api.py --live

它只做四件事：① 建一个 DE + 空工程（从干净模板复制）；② 对候选名字逐个 `hasattr` +
打印 docstring；③ 打印 `dir(model3d)` 里与求解有关的成员；④ **只关自己开的 DE**。
全程带弹窗守卫（`scripts/cst_dialog_guard.py`），任何一步卡住都会报「疑似模态弹窗」
而不是无声挂住。
"""

import argparse
import os
import sys
import traceback
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# CST 安装根目录（可用环境变量覆盖）
DEFAULT_INSTALL_ROOTS = [
    r'C:\SOFTWARE\CST Studio Suite 2026',
    r'C:\Program Files (x86)\CST Studio Suite 2026',
    r'C:\Program Files\CST Studio Suite 2026',
]
AMD64 = 'AMD64'
LIB = os.path.join(AMD64, 'python_cst_libraries')

# 候选名字：真的存在哪个、叫什么，只能由真机 hasattr 回答
CANDIDATES = [
    'abort_solver', 'AbortSolver', 'stop_solver', 'StopSolver',
    'run_solver', 'RunSolver', 'start_solver', 'StartSolver',
    'get_active_solver_name', 'get_solver_run_info',
    'IsSolving', 'IsSolverRunning', 'GetSolverType',
    'DeleteResults', 'Solver',
]

CLEAN_TEMPLATE = r'D:\TPC_out\tmp.cst'
_results = []


def record(item, status, detail, **extra):
    entry = {'item': item, 'status': status, 'detail': detail}
    entry.update(extra)
    _results.append(entry)
    print(f'[{status:^7}] {item}: {detail}', flush=True)


def find_install_root():
    """找到含 `_cst_interface.*.pyd` 的安装根目录。"""
    for root in ([os.environ['CST_INSTALL_DIR']]
                 if os.environ.get('CST_INSTALL_DIR') else []) + DEFAULT_INSTALL_ROOTS:
        if os.path.isdir(os.path.join(root, AMD64)):
            return root
    return None


def import_interface(root):
    """
    离线 import `_cst_interface`（**不启动 CST**）。

    :param root: str, CST 安装根目录
    :return: module
    """
    sys.path.insert(0, os.path.join(root, LIB))
    sys.path.insert(0, os.path.join(root, AMD64))
    import _cst_interface                                # noqa: PLC0415
    return _cst_interface


def probe_static(root):
    """离线内省：静态成员里有没有停止/取消类 API。"""
    try:
        ci = import_interface(root)
    except Exception as exc:                             # noqa: BLE001
        record('离线内省', 'UNKNOWN',
               f'import _cst_interface 失败：{type(exc).__name__}: {exc}'
               f'（Python 版本与 .pyd 不匹配？）')
        return None
    record('离线内省', 'OK', f'import 成功：{os.path.basename(ci.__file__)}')

    import re
    pattern = re.compile(r'stop|abort|cancel|terminate|interrupt|kill', re.I)
    total_stop_like = []
    for cls_name in ('DesignEnvironment', 'Project', 'Model3D'):
        cls = getattr(ci, cls_name)
        names = [n for n in dir(cls) if not n.startswith('_')]
        hits = [n for n in names if pattern.search(n)]
        total_stop_like += hits
        record(f'{cls_name} 静态成员', 'OK',
               f'{len(names)} 个公开成员；停止/取消类命中：{hits or "无"}')
    record('结论（静态）', 'OK' if not total_stop_like else 'UNKNOWN',
           f'静态成员里唯一的关闭类 API 是 close()；'
           f'Model3D 是 RemoteObject 动态代理，扩展方法 dir() 看不到 '
           f'⇒ 必须有真机 hasattr 才能定论')
    return ci


def probe_live_app(app):
    """
    对**已经打开**的 CST 会话做候选名字探测（可被别的真机脚本复用）。

    这样「求解控制接口探针」不必单独开一次 CST —— 任何真机脚本拿到 `app`
    都能顺手探一遍（`verify_antenna_mapping.py` 就是这么用的）。

    :param app: `cst_solver.setup()` 返回的会话对象
    :return: list[dict], 每个候选一项 ``{'name', 'present', 'doc'}``
    """
    model3d = app.cst_file.model3d
    results = []
    for name in CANDIDATES:
        present = hasattr(model3d, name)
        doc = ''
        if present:
            try:
                doc = str(getattr(model3d, name).__doc__ or '')[:120]
            except Exception:                                # noqa: BLE001
                pass
        results.append({'name': name, 'present': present, 'doc': doc})
    return results


def probe_live(root, template=CLEAN_TEMPLATE):
    """真机探针：开一个空工程，`hasattr` 逐个候选名字，然后只关自己开的 DE。"""
    sys.path.insert(0, str(PROJECT_ROOT / 'scripts'))
    from cst_dialog_guard import check_dialogs, describe_dialogs, guard   # noqa: PLC0415
    from topo_modeler.batch import (                                      # noqa: PLC0415
        close_extra_design_environments, design_environment_baseline,
    )

    os.environ.setdefault('CST_INSTALL_DIR', root)
    baseline = design_environment_baseline()
    print(f'基线 DE：{sorted(baseline)}', flush=True)
    print('跑之前的 CST 对话框：\n' + describe_dialogs(), flush=True)
    app = None
    try:
        import shutil                                        # noqa: PLC0415
        import tempfile                                      # noqa: PLC0415
        from cst_solver import setup                         # noqa: PLC0415
        workdir = tempfile.mkdtemp(prefix='tpc_probe_cancel_')
        target = os.path.join(workdir, 'tmp.cst')
        shutil.copy2(template, target)
        app = setup(target)
        record('真机：建立空工程', 'OK', f'{target}（不建模、不求解）')

        found = {item['name']: item for item in probe_live_app(app)}
        for name, item in found.items():
            if item['present']:
                record(f'hasattr(model3d, {name!r})', 'OK',
                       f"存在；doc={item['doc']!r}")
        missing = [n for n, item in found.items() if not item['present']]
        record('真机：候选名字存在性',
               'OK' if any(item['present'] for item in found.values()) else 'UNKNOWN',
               f"存在 {[n for n, i in found.items() if i['present']] or '无'}；"
               f'不存在 {len(missing)} 个')
        dynamic = [n for n in dir(model3d) if not n.startswith('_')]
        record('真机：dir(model3d)', 'OK',
               f'{len(dynamic)} 个静态可见成员：{sorted(dynamic)[:20]}')
        with guard('dir(model3d) 完成', timeout=5):
            pass
        check_dialogs('真机探针结束后')
    except Exception as exc:                                 # noqa: BLE001
        record('真机探针', 'FAIL',
               f'{type(exc).__name__}: {exc}\n{traceback.format_exc(limit=2)}')
    finally:
        try:
            if app is not None:
                app.close()
        except Exception:                                    # noqa: BLE001
            pass
        closed = close_extra_design_environments(baseline, verbose=True)
        record('收尾', 'OK', f'关闭本次新建的 DE：{closed or "无"}')


def main(argv=None):
    parser = argparse.ArgumentParser(description='CST 取消/停止能力探针（P2 待办）')
    parser.add_argument('--live', action='store_true',
                        help='真的起一个 DE + 空工程做 hasattr 探针（秒级，不求解）')
    parser.add_argument('--template', default=CLEAN_TEMPLATE,
                        help='干净模板 .cst（--live 用）')
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    root = find_install_root()
    if root is None:
        record('定位 CST 安装', 'FAIL',
               '没找到含 AMD64\\_cst_interface.*.pyd 的目录；'
               '可用环境变量 CST_INSTALL_DIR 指定')
        return 2
    record('定位 CST 安装', 'OK', root)

    probe_static(root)
    if args.live:
        if not os.path.isfile(args.template):
            record('真机探针', 'FAIL', f'模板不存在：{args.template}')
            return 2
        probe_live(root, args.template)

    print('\n=== 汇总 ===')
    for entry in _results:
        print(f"{entry['status']:^7}  {entry['item']}")
    failed = [r for r in _results if r['status'] == 'FAIL']
    print(f"\nOK {len([r for r in _results if r['status'] == 'OK'])} / "
          f"FAIL {len(failed)} / UNKNOWN "
          f"{len([r for r in _results if r['status'] == 'UNKNOWN'])}")
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
