# -*- coding: utf-8 -*-
"""
P4/V8 事实核验：环境与会话生命周期
==================================

用途：在**装有 CST 的机器上**跑一次，核对「本轮环境与会话改动」是否真的成立。
本脚本只做事实核验，不改库代码；结论回填 `docs/validation/p4_real_machine_evidence.md`。

要核验的四件事（对应计划 P4/V8）
--------------------------------
D1  打开**不存在**的工程：必须在创建 DE 之前失败 —— 不留空窗口
D2  打开**存在但不是有效工程**的文件：创建了 DE 之后失败 → 必须把 DE 关掉
D3  只创建 DE 再关掉：DE 数量回到基线
D4  先关工程、再关 DE：两步语义分别成立（关工程后 DE 仍在，关 DE 后回到基线）
D5  ``python -m cst_solver doctor --probe``：只说明**接口可导入**，
    不代表许可/仿真可用（这里如实记录状态，不夸大）

判定方式
--------
以 ``cst.interface.running_design_environments()`` 的**进程号集合**为准，
每个探针跑完都要求集合回到基线（允许短暂延迟，最多等 30 s）。

用法
----
    python scripts/verify_environment_lifecycle.py

注意
----
* 只新建空白工程与一个临时坏文件，**不打开、不修改任何既有工程**；
* 收尾用基线差集关闭**本次自己开出来的** DE，绝不碰用户已开着的会话；
* 需要 CST；无 CST 时会明确报错退出（非 0）。
"""

import json
import os
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from topo_modeler.batch import (                    # noqa: E402
    close_extra_design_environments,
    design_environment_baseline,
    running_design_environments,
)

_results = []
_app = None
_baseline = set()
_template = None
_tmpdir = None


def record(item, status, detail, **extra):
    """记录一条核验结果（OK / FAIL / UNKNOWN）。"""
    entry = {'item': item, 'status': status, 'detail': detail}
    entry.update(extra)
    _results.append(entry)
    print(f'[{status:^7}] {item}: {detail}', flush=True)


def de_count() -> int:
    """当前活着的 DE 数量。"""
    return len(running_design_environments())


def wait_for_baseline(timeout=30.0) -> bool:
    """等 DE 数量回到基线（关闭进程需要一点时间）。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if set(running_design_environments()) <= _baseline:
            return True
        time.sleep(0.5)
    return set(running_design_environments()) <= _baseline


def expect_baseline(label, timeout=30.0):
    """要求 DE 回到基线，否则记 FAIL。"""
    ok = wait_for_baseline(timeout)
    record(label, 'OK' if ok else 'FAIL',
           f'DE 集合{"回到" if ok else "未回到"}基线（当前 {sorted(running_design_environments())}，'
           f'基线 {sorted(_baseline)}）')
    return ok


# ============================================================
# D1 / D2：打开失败清理
# ============================================================

def check_missing_project():
    """D1：不存在的工程 → 必须在建 DE 之前失败。"""
    from cst_solver import setup
    before = de_count()
    missing = str(Path(_tmpdir) / 'does_not_exist.cst')
    try:
        setup(missing)
        record('D1 打开不存在的工程', 'FAIL', '居然没有抛异常')
        return
    except FileNotFoundError as exc:
        record('D1 打开不存在的工程', 'OK',
               f'抛 FileNotFoundError（{exc}）', de_before=before,
               de_after=de_count())
    except Exception as exc:                          # noqa: BLE001
        record('D1 打开不存在的工程', 'FAIL',
               f'抛了非预期异常 {type(exc).__name__}: {exc}')
        return
    expect_baseline('D1 失败后 DE 未增加')


def check_invalid_project():
    """D2：存在但不是有效工程 → 建了 DE 之后失败，必须关掉 DE。"""
    from cst_solver import setup
    bad = Path(_tmpdir) / 'not_a_project.cst'
    bad.write_text('this is not a CST project', encoding='utf-8')
    before = de_count()
    try:
        setup(str(bad))
        record('D2 打开无效工程文件', 'FAIL', '居然没有抛异常')
    except Exception as exc:                          # noqa: BLE001
        record('D2 打开无效工程文件', 'OK',
               f'抛 {type(exc).__name__}（打开失败）', de_before=before,
               de_after=de_count())
    expect_baseline('D2 失败后 DE 未残留')


# ============================================================
# D3 / D4：DE 与工程的关闭语义
# ============================================================

def check_de_only_lifecycle():
    """D3：只创建 DE 再关掉。"""
    from cst_solver.environment import _load_cst_module
    environment = _load_cst_module('cst.interface').DesignEnvironment()
    record('D3 只创建 DE', 'OK', f'创建后 DE 数量 {de_count()}')
    environment.close()
    expect_baseline('D3 关闭 DE 后回到基线')


def check_project_then_environment():
    """D4：先关工程、再关 DE，两步语义分别成立。"""
    from cst_solver import setup
    global _app
    _app = setup(_template)
    after_open = de_count()
    record('D4 打开工程', 'OK' if after_open > len(_baseline) else 'FAIL',
           f'打开后 DE 数量 {after_open}（基线 {len(_baseline)}）')
    if after_open <= len(_baseline):
        return

    _app.project_close()                              # 只关工程
    time.sleep(1.0)
    still_alive = de_count()
    record('D4 只关工程', 'OK' if still_alive > len(_baseline) else 'FAIL',
           f'关工程后 DE 数量 {still_alive}（应当仍存活）')

    _app.project.close()                              # 再关 DE
    expect_baseline('D4 再关 DE 后回到基线')
    _app = None


# ============================================================
# D5：doctor
# ============================================================

def check_doctor():
    """D5：doctor --probe 只说明接口可导入。"""
    proc = subprocess.run([sys.executable, '-m', 'cst_solver', 'doctor', '--probe'],
                          capture_output=True, text=True, cwd=str(PROJECT_ROOT))
    try:
        payload = json.loads(proc.stdout)
    except Exception as exc:                          # noqa: BLE001
        record('D5 doctor --probe', 'FAIL',
               f'输出不是 JSON（{exc!r}）：{proc.stdout[:200]!r}')
        return
    status = payload.get('status')
    record('D5 doctor --probe', 'OK' if status in ('importable', 'unavailable')
           else 'FAIL',
           f'status={status}（importable 只说明接口能加载，'
           f'不代表许可/仿真可用）')
    record('D5 doctor 不建 DE', 'OK' if set(running_design_environments()) <= _baseline
           else 'FAIL',
           f'doctor 结束后 DE 集合 {sorted(running_design_environments())}')


# ============================================================
# 主流程
# ============================================================

def main() -> int:
    global _baseline, _template, _tmpdir
    _baseline = design_environment_baseline()
    print(f'基线 DE：{sorted(_baseline)}（收尾只会关掉不在这个集合里的）', flush=True)
    _tmpdir = tempfile.mkdtemp(prefix='tpc_verify_env_')

    # 干净模板：用仓库外已有的干净模板副本（只读打开，不改它）
    source = r'D:\TPC_out\tmp.cst'
    if not os.path.isfile(source):
        record('准备模板', 'FAIL', f'找不到干净模板 {source}（需要先准备一份干净 tmp.cst）')
        return 2
    _template = os.path.join(_tmpdir, 'tmp.cst')
    import shutil
    shutil.copy2(source, _template)
    record('准备模板', 'OK', f'已复制干净模板 → {_template}')

    try:
        check_missing_project()
        check_invalid_project()
        check_de_only_lifecycle()
        check_project_then_environment()
        check_doctor()
    except Exception:                                 # noqa: BLE001
        record('核验过程异常', 'FAIL', traceback.format_exc(limit=3))
    finally:
        if _app is not None:
            try:
                _app.close()
            except Exception:                         # noqa: BLE001
                pass
        closed = close_extra_design_environments(_baseline, verbose=True)
        record('收尾', 'OK',
               f'关闭本次新建的 DE：{closed or "无"}（用户已有会话未触碰）')

    failed = [r for r in _results if r['status'] == 'FAIL']
    print('\n=== 汇总 ===')
    for entry in _results:
        print(f"{entry['status']:^7}  {entry['item']}")
    print(f'\nOK {len([r for r in _results if r["status"] == "OK"])} / '
          f'FAIL {len(failed)} / UNKNOWN {len([r for r in _results if r["status"] == "UNKNOWN"])}')
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
