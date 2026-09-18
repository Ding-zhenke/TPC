# -*- coding: utf-8 -*-
"""
P4/V4 事实核验：守卫层与导出流程
================================

用途：在**装有 CST 的机器上**跑一次，核对计划 P4/V4 的三件事：

G1  两个模板（`StraightWaveguide` / `UnitAntenna`）在 **warn 模式**下建模，
    守卫层**不得误报**（把正常运行当成 T13/T2/T15 问题）；
G2  同上，但把守卫层产生的 finding 逐条打印出来，便于定位噪声来源；
G3  **T3 场景**：在**已求解工程的副本**上「导出结果 → 再 save(include_results=True)」
    —— 守住层应当给出那条「建议 include_results=False」的警告（这是**期望行为**，
    不是误报）；
G4  **端口增强**参数（`number_of_modes` / `adjust_polarization` /
    `polarization_angle` / `reference_plane_distance`）真实调用：应当被 CST 接受。

只读/只写副本：G3 用**复制到临时目录的副本**，绝不改动用户原工程；
收尾关闭本次新建的 DE（只关自己开的）。

用法::

    python scripts/verify_guard_export_flow.py
"""

import json
import os
import shutil
import sys
import tempfile
import traceback
import warnings
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from topo_modeler.batch import (                    # noqa: E402
    close_extra_design_environments,
    design_environment_baseline,
)

CLEAN_TEMPLATE = r'D:\TPC_out\tmp.cst'
SOLVED_PROJECT = (r'D:\成电博士生涯\拓扑光子晶体模型\硅基\普通单元天线'
                  r'\Ant1_D_BA_120_Feed_antenna-DF.cst')

_results = []
_baseline = set()


def record(item, status, detail, **extra):
    entry = {'item': item, 'status': status, 'detail': detail}
    entry.update(extra)
    _results.append(entry)
    print(f'[{status:^7}] {item}: {detail}', flush=True)


def _findings(app):
    """守卫层登记的 finding（结构化）。"""
    from cst_solver._guards import get_guard_state
    try:
        return [f.as_dict() for f in get_guard_state(app).get_findings()]
    except Exception as exc:                          # noqa: BLE001
        return [{'error': repr(exc)}]


def _capture_warnings(func, *args, **kwargs):
    """执行 func，返回 (结果, 捕获到的 warning 列表)。"""
    caught = []
    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter('always')
        result = func(*args, **kwargs)
    for entry in recorded:
        caught.append({'category': entry.category.__name__,
                       'message': str(entry.message)[:160]})
    return result, caught


def _summary(warnings_list):
    """按类别聚合警告（同一类只留一条样例）。"""
    buckets = {}
    for entry in warnings_list:
        key = entry['message'].split('：')[0][:60]
        buckets.setdefault(key, {'count': 0, 'sample': entry['message']})
        buckets[key]['count'] += 1
    return buckets


# ============================================================
# G1 / G2：模板在 warn 模式下不得误报
# ============================================================

def probe_template(kind, workdir, topology='AB'):
    """建一个模板（warn 模式），统计守卫 finding 与 Python 警告。"""
    from cst_solver._guards import set_guard_mode
    from topo_templates import StraightWaveguide, UnitAntenna

    set_guard_mode('warn')
    template = os.path.join(workdir, f'tmp_{kind}.cst')
    if not os.path.exists(template):
        shutil.copy2(CLEAN_TEMPLATE, template)
    output = os.path.join(workdir, f'{kind}_{topology}.cst')

    if kind == 'straight':
        antenna = StraightWaveguide(topology=topology, length=18,
                                    template_cst=template, output_path=output)
    else:
        antenna = UnitAntenna(bend_angle=120, straight_length=18, arm_length=14,
                              topology=topology, template_cst=template,
                              output_path=output)
    try:
        _, caught = _capture_warnings(antenna.build_all)
        antenna.save(output)
        findings = _findings(antenna.app)
        messages = [str(m) for m in (antenna.app.cst_file.get_messages() or [])]
        guard_summary = None
        try:
            from cst_solver._guards import get_guard_state
            guard_summary = get_guard_state(antenna.app).summary()
        except Exception:                             # noqa: BLE001
            pass
    except Exception as exc:                          # noqa: BLE001
        record(f'G1/G2 {kind}({topology}) 建模', 'FAIL',
               f'{type(exc).__name__}: {str(exc).splitlines()[-1][:160]}')
        return
    finally:
        try:
            antenna.close()
        except Exception:                             # noqa: BLE001
            pass

    traps = [f for f in findings if str(f.get('plan_id', '')) in
             ('T2', 'T3', 'T13', 'T7\'', 'T15')]
    noise = _summary(caught)
    guard_noise = {k: v for k, v in noise.items() if 'LOG_FLAG_NO_REBUILD' in k
                   or 'GUARD' in k.upper()}
    record(f'G1/G2 {kind}({topology}) 建模', 'OK',
           f'建模成功；CST 消息 {len(messages)} 条；守卫 finding {len(findings)} 条',
           guard_summary=guard_summary,
           trap_findings=[{k: f.get(k) for k in ('code', 'plan_id', 'severity')}
                          for f in traps],
           python_warning_kinds=len(noise),
           guard_related_warnings=guard_noise,
           messages=[m[:150] for m in messages[:2]])
    # 期望：CST 无消息、且没有守卫层的 trap finding / 相关噪声警告
    clean = (not messages) and (not traps) and (not guard_noise)
    record(f'G1/G2 {kind}({topology}) 无误报', 'OK' if clean else 'FAIL',
           '干净：无 CST 消息、无守卫 trap、无噪声警告' if clean
           else f'存在误报：CST 消息 {len(messages)}；trap {len(traps)}；'
                f'噪声警告 {guard_noise}')


# ============================================================
# G3：T3 场景（导出后保存）
# ============================================================

def probe_t3(workdir):
    """在**已求解工程的副本**上：导出 1D 结果 → save(include_results=True)。"""
    from cst_solver import setup
    from cst_solver._guards import get_guard_state, set_guard_mode

    if not os.path.isfile(SOLVED_PROJECT):
        record('G3 T3 场景', 'FAIL', f'找不到已求解工程：{SOLVED_PROJECT}')
        return
    copy_dir = os.path.join(workdir, 'solved_copy')
    os.makedirs(copy_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(SOLVED_PROJECT))[0]
    target = os.path.join(copy_dir, f'{stem}.cst')
    if not os.path.exists(target):
        shutil.copy2(SOLVED_PROJECT, target)
        source_folder = os.path.splitext(SOLVED_PROJECT)[0]
        if os.path.isdir(source_folder):
            shutil.copytree(source_folder, os.path.splitext(target)[0])
    record('G3 准备副本', 'OK', f'已复制已求解工程副本 → {target}')

    set_guard_mode('warn')
    app = None
    try:
        app = setup(target)
        export_path = os.path.join(copy_dir, 'exported_1d.txt')
        _, caught_export = _capture_warnings(
            app.export_result_1d, 'S-Parameters\\S1,1', export_path)
        exported = os.path.isfile(export_path)
        record('G3 导出 1D 结果', 'OK' if exported else 'FAIL',
               f'导出文件{"已生成" if exported else "没有生成"}：{export_path}',
               warnings=caught_export)

        _, caught_save = _capture_warnings(app.save, target)
        findings = _findings(app)
        t3 = [f for f in findings if str(f.get('plan_id', '')) == 'T3'
              or 'T3' in str(f.get('code', ''))]
        t3_warned = any('include_results' in w['message'] for w in caught_save) or bool(t3)
        record('G3 导出后保存', 'OK' if t3_warned else 'FAIL',
               ('守卫给了 T3 警告（期望行为）' if t3_warned
                else '没有给出 T3 警告 —— 这条守卫需要复查'),
               warnings=[w['message'][:140] for w in caught_save],
               findings=[{k: f.get(k) for k in ('code', 'plan_id', 'severity')}
                         for f in findings])

        # 推荐做法：导出后用 include_results=False 保存 —— 不应再告警
        get_guard_state(app).clear_findings()
        _, caught_again = _capture_warnings(app.save, target,
                                            include_results=False)
        again = [w for w in caught_again if 'include_results' in w['message']]
        record('G3 导出后 save(include_results=False) 不告警',
               'OK' if not again else 'FAIL',
               '不再告警（与守卫建议一致）' if not again
               else f'仍告警：{again[0]["message"][:140]}')
    except Exception as exc:                          # noqa: BLE001
        record('G3 T3 场景', 'FAIL', f'{type(exc).__name__}: {exc}')
    finally:
        try:
            if app is not None:
                app.close()
        except Exception:                             # noqa: BLE001
            pass


# ============================================================
# G4：端口增强
# ============================================================

def probe_port(workdir):
    """端口增强参数的真实调用。"""
    from cst_solver import setup
    from cst_solver._guards import set_guard_mode

    set_guard_mode('warn')
    template = os.path.join(workdir, 'tmp_port.cst')
    if not os.path.exists(template):
        shutil.copy2(CLEAN_TEMPLATE, template)
    app = None
    try:
        app = setup(template)
        app.new_project()
        app.square('0', '1', '0', '1', '0', '1', 'pbox', 'component1',
                   'Vacuum')
        picked = app.pick_face_auto('pbox', points=[(0.5, 0.5, 1.0)],
                                    candidates=('10', '1', '2', '3'))
        app.add_port(1, orientation='positive', number_of_modes=2,
                     adjust_polarization='True', polarization_angle='30',
                     reference_plane_distance='0.5')
        messages = [str(m) for m in (app.cst_file.get_messages() or [])]
        record('G4 端口增强真实调用', 'OK' if not messages else 'FAIL',
               '无 CST 消息 ⇒ 被接受' if not messages
               else f'有消息：{messages[0][:160]}',
               picked=str(picked), messages=[m[:150] for m in messages[:2]])
    except Exception as exc:                          # noqa: BLE001
        record('G4 端口增强真实调用', 'FAIL',
               f'{type(exc).__name__}: {str(exc).splitlines()[-1][:160]}')
    finally:
        try:
            if app is not None:
                app.close()
        except Exception:                             # noqa: BLE001
            pass


def main() -> int:
    global _baseline
    _baseline = design_environment_baseline()
    print(f'基线 DE：{sorted(_baseline)}', flush=True)
    workdir = tempfile.mkdtemp(prefix='tpc_verify_v4_')
    print(f'产物目录：{workdir}', flush=True)
    try:
        probe_template('straight', workdir, 'AB')
        probe_template('antenna', workdir, 'AB')
        probe_port(workdir)
        probe_t3(workdir)
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
