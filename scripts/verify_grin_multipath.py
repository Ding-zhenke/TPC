# -*- coding: utf-8 -*-
"""
P4/V6 事实核验：GRIN 透镜与多路径基板
=====================================

用途：在**装有 CST 的机器上**跑一次，核对 `docs/next_plan/README.md` 的 P4/V6：

L1  **GRIN 透镜构建序列**：`GrinLensSpec` / `build_grin_lens_holes` / `export_dxf` /
    `build_grin_lens` 全链路在真机上跑通，每一步**无 CST 消息**；
L2  **透镜的几何与布尔结果**：保存后读磁盘取证 —— 历史里出现预期命令
    （DXF 导入 / 镜像 / 椭圆拉伸 / 相减 / 旋转复制），且整体包围盒**有限、非退化、
    落在六边形量级内**；
M1  **多路径基板**：`build_substrate_multi` 把主干 + 分支各做一条带并**布尔并成一个实体**；
M2  **几何验收**：保存后读包围盒，与「按路径点 + 带宽算出的期望范围」逐轴比对。

⚠️ 为了不把机器占住太久，透镜用**小尺寸**（`ratio=2`、`nx=8`、`ny=6`），
孔数是参考配置的几十分之一；结论是「序列与几何正确」，**不是**参考配置的耗时结论。

只新建空白工程（从干净模板复制）；收尾关闭本次新建的 DE。

用法::

    python scripts/verify_grin_multipath.py
"""

import base64
import json
import math
import os
import re
import shutil
import struct
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cst_dialog_guard import describe_windows, describe_dialogs, save_prompts, guard   # noqa: E402

CLEAN_TEMPLATE = r'D:\TPC_out\tmp.cst'
A = 0.2425
E2 = A * math.sqrt(3) / 2

_results = []
_baseline = set()


def record(item, status, detail, **extra):
    entry = {'item': item, 'status': status, 'detail': detail}
    entry.update(extra)
    _results.append(entry)
    print(f'[{status:^7}] {item}: {detail}', flush=True)


def _messages(app):
    return [str(m) for m in (app.cst_file.get_messages() or [])]


def _read_bbox(project_path):
    """从保存后的 Model.abi 里解出 structureBB（xmin,ymin,zmin,xmax,ymax,zmax）。"""
    abi = os.path.join(os.path.splitext(project_path)[0], 'Model', '3D',
                       'Model.abi')
    if not os.path.isfile(abi):
        return None, f'没有 Model.abi：{abi}'
    text = open(abi, encoding='utf-8', errors='ignore').read()
    match = re.search(r'structureBB[^>]*>([A-Za-z0-9+/=\r\n]+)<', text)
    if not match:
        return None, 'Model.abi 里没有 structureBB'
    raw = base64.b64decode(match.group(1).replace('\r', '').replace('\n', ''))
    values = struct.unpack('<6d', raw)
    return values, None


def _history_commands(project_path):
    """保存后的历史里用了哪些 CST 命令（去重）。"""
    path = os.path.join(os.path.splitext(project_path)[0], 'Model', '3D',
                        'ModelHistory.json')
    if not os.path.isfile(path):
        return []
    data = json.load(open(path, encoding='utf-8-sig'))
    code = '\n'.join(line for entry in data.get('history', [])
                     for line in entry.get('code', []))
    # ⚠️ 词表必须含 `Solid.Add` —— 逐段四边形并集用的就是它；旧词表漏了它，
    #    于是 M 组的布尔并集被判成 UNKNOWN（2026-09-17 离线补证时发现）。
    keywords = ('Import', 'Mirror', 'Ellipse', 'ExtrudeCurve', 'Solid.Subtract',
                'Solid.Add', 'Transform', 'Polygon', 'Material', 'StoreParameter')
    return sorted({kw for kw in keywords if kw in code})


def _new_app(workdir, tag):
    """打开干净模板 + 建材料（模板 tmp.cst 不带材料，缺了第一条 extrude 就报
    `The specified material does not exist` —— 这是库的既定约定，模板都会先调
    build_materials）。"""
    from cst_solver import setup
    from topo_modeler.builders import build_materials
    template = os.path.join(workdir, f'tmp_{tag}.cst')
    if not os.path.exists(template):
        shutil.copy2(CLEAN_TEMPLATE, template)
    app = setup(template)
    build_materials(app)
    return app


# ============================================================
# L：GRIN 透镜
# ============================================================

def probe_lens(workdir):
    from topo_modeler.builders.lens import (
        build_grin_lens,
        build_grin_lens_holes,
        grin_lens_spec_from_cst_params,
    )

    # ---- L1-① 离线：算几何、导 DXF ----
    try:
        spec = grin_lens_spec_from_cst_params(
            a=A, ratio=1.0, nx=16, ny=13, r1_0=0.052, r2_0=0.066,
            n_small=8, lx1=6)
        holes = build_grin_lens_holes(spec)
        dxf = os.path.join(workdir, 'lens_small.dxf')
        holes.export_dxf(dxf)
        record('L1 生成孔阵列与 DXF', 'OK' if os.path.isfile(dxf) else 'FAIL',
               f'格距 a2={spec.a2:.5f}、椭圆 ec_a={spec.ec_a:.4f}、'
               f'R_big={spec.r_big:.4f}；DXF={os.path.basename(dxf)}'
               f'（{os.path.getsize(dxf) // 1024} KB）',
               n_holes=len(holes.centers) if hasattr(holes, 'centers') else None,
               dxf=dxf)
    except Exception as exc:                          # noqa: BLE001
        record('L1 生成孔阵列与 DXF', 'FAIL', f'{type(exc).__name__}: {exc}')
        return

    # ---- L1-② 真机：全序列 ----
    app = None
    step_tags = []
    try:
        app = _new_app(workdir, 'lens')
        app.para('a', A)
        app.para('h', 0.25)
        # ⚠️ 这两个参数**不属于** build_grin_lens（它们来自基板/大六边形工程），
        #    缺了它们 CST 会弹「请输入变量值」对话框把脚本挂住（P4/V6 实测）。
        app.para('Rbig', f'{spec.r_big / A:g}*a', expression='大六边形外接圆半径')
        app.para('Ls', '2.2*Rbig', expression='楔形裁剪体边长（约定 2.2*Rbig）')
        app.cst_file.get_messages()
        print('跑透镜前的 CST 窗口：\n' + describe_windows(), flush=True)
        print('跑透镜前的 CST 对话框：\n' + describe_dialogs(), flush=True)

        def log(tag=''):
            msgs = _messages(app)
            step_tags.append((tag, len(msgs)))
            if msgs:
                record(f'L1 步骤「{tag}」', 'FAIL',
                       f'有 CST 消息：{msgs[0][:150]}')
            else:
                record(f'L1 步骤「{tag}」', 'OK', '无消息')

        with guard('build_grin_lens', timeout=600):
            result = build_grin_lens(app, holes, spec, dxf_path=dxf, log=log)
        print('跑透镜后的 CST 窗口：\n' + describe_windows(), flush=True)
        output = os.path.join(workdir, 'lens_small.cst')
        app.cst_file.save(output, include_results=False, allow_overwrite=True)
        record('L1 透镜构建序列', 'OK',
               f'{len(step_tags)} 步全部无消息；实体：'
               f'{ {k: v for k, v in result.items() if isinstance(v, str)} }',
               steps=[tag for tag, _ in step_tags])
    except Exception as exc:                          # noqa: BLE001
        detail = ' | '.join(line.strip() for line in str(exc).splitlines()
                            if line.strip())[:300]
        record('L1 透镜构建序列', 'FAIL',
               f'在「{step_tags[-1][0] if step_tags else "第一步"}」之后失败：'
               f'{type(exc).__name__}: {detail}',
               finished_steps=[tag for tag, _ in step_tags])
        return
    finally:
        try:
            if app is not None:
                app.close()
        except Exception:                             # noqa: BLE001
            pass
        # 关闭 DE 时 CST 可能弹「是否保存更改？」—— 没人点它就挂住后续脚本（实测过）
        _check_close_dialogs()

    # ---- L2 落盘取证 ----
    commands = _history_commands(output)
    needed = {'Import', 'Mirror', 'Ellipse', 'ExtrudeCurve', 'Solid.Subtract',
              'Transform'}
    missing = sorted(needed - set(commands))
    record('L2 历史命令齐全', 'OK' if not missing else 'FAIL',
           f'出现：{commands}' if not missing
           else f'缺少 {missing}；实际出现 {commands}',
           commands=commands)

    bbox, error = _read_bbox(output)
    if bbox is None:
        record('L2 包围盒', 'FAIL', error)
        return
    xmin, ymin, zmin, xmax, ymax, zmax = bbox
    size = (xmax - xmin, ymax - ymin, zmax - zmin)
    finite = all(math.isfinite(v) for v in bbox)
    # 6 重对称的透镜阵列：整体尺度应当与 R_big 同量级（而不是 0 或无穷）
    scale = spec.r_big
    ok_range = (0.05 * scale < size[0] < 20 * scale and
                0.05 * scale < size[1] < 20 * scale)
    # z 方向应当就是片厚 h（拉伸 + 居中 ⇒ [-h/2, h/2]）
    z_ok = abs(size[2] - 0.25) < 1e-6
    record('L2 包围盒有限非退化', 'OK' if (finite and ok_range) else 'FAIL',
           f'x∈[{xmin:.4f},{xmax:.4f}] y∈[{ymin:.4f},{ymax:.4f}] '
           f'z∈[{zmin:.4f},{zmax:.4f}]；尺寸 {tuple(round(v, 4) for v in size)}；'
           f'R_big={scale:.4f}')
    record('L2 厚度方向正确（= h）', 'OK' if z_ok else 'FAIL',
           f'实测 z 厚度 {size[2]:.5f} vs 期望 {0.25}')


# ============================================================
# M：多路径基板
# ============================================================

def probe_multipath(workdir):
    from mesh_grid.tri_grid import TopoPath
    from topo_modeler.builders import build_substrate_multi

    main = (TopoPath.builder(A, name='p').start(0, 0).move(18, 'c').build())
    branch = (TopoPath.builder(A, name='q').start(0, 6).turn(120)
              .move(8, 'along').build())

    # 期望包围盒：**包含**所有路径点，且**不超过**「路径点范围 ± e2」的保守外扩
    # （直线段的带只在法向扩，故 x 方向不会被 e2 撑开 —— 早先按 ±e2 盲扩是错的）
    xs, ys = [], []
    for path in (main, branch):
        for x, y in ((float(a), float(b)) for a, b in path.xy):
            xs.append(x)
            ys.append(y)
    inner = (min(xs), min(ys), max(xs), max(ys))
    outer = (min(xs) - E2, min(ys) - E2, max(xs) + E2, max(ys) + E2)

    app = None
    try:
        app = _new_app(workdir, 'multi')
        app.para('a', A)
        app.para('h', 0.25)
        app.cst_file.get_messages()
        build_substrate_multi(app, {'main': main, 'branch': branch},
                              name='sub_multi', unite=True)
        messages = _messages(app)
        record('M1 多路径基板建模', 'OK' if not messages else 'FAIL',
               '无 CST 消息 ⇒ 两条带并成了一个实体' if not messages
               else f'有消息：{messages[0][:160]}',
               messages=[m[:150] for m in messages[:2]])
        output = os.path.join(workdir, 'multi.cst')
        app.cst_file.save(output, include_results=False, allow_overwrite=True)
        commands = _history_commands(output)
        record('M1 历史里出现布尔并', 'OK' if 'Solid.Add' in ' '.join(commands)
               or 'Add' in ' '.join(commands) else 'UNKNOWN',
               f'历史命令：{commands}')
    except Exception as exc:                          # noqa: BLE001
        record('M1 多路径基板建模', 'FAIL',
               f'{type(exc).__name__}: {str(exc).splitlines()[-1][:180]}')
        return
    finally:
        try:
            if app is not None:
                app.close()
        except Exception:                             # noqa: BLE001
            pass
        # 关闭 DE 时 CST 可能弹「是否保存更改？」—— 没人点它就挂住后续脚本（实测过）
        _check_close_dialogs()

    bbox, error = _read_bbox(output)
    if bbox is None:
        record('M2 包围盒', 'FAIL', error)
        return
    xmin, ymin, zmin, xmax, ymax, zmax = bbox
    tol = 1e-4
    covers = (xmin <= inner[0] + tol and ymin <= inner[1] + tol
              and xmax >= inner[2] - tol and ymax >= inner[3] - tol)
    not_oversized = (xmin >= outer[0] - tol and ymin >= outer[1] - tol
                     and xmax <= outer[2] + tol and ymax <= outer[3] + tol)
    record('M2 覆盖两条路径且未异常外扩', 'OK' if (covers and not_oversized)
           else 'FAIL',
           f'实测 x∈[{xmin:.4f},{xmax:.4f}] y∈[{ymin:.4f},{ymax:.4f}]；'
           f'应当包含路径点范围 x∈[{inner[0]:.4f},{inner[2]:.4f}] '
           f'y∈[{inner[1]:.4f},{inner[3]:.4f}]，且不超过保守外扩 '
           f'x∈[{outer[0]:.4f},{outer[2]:.4f}] y∈[{outer[1]:.4f},{outer[3]:.4f}]',
           bbox=list(bbox), inner=list(inner), outer=list(outer),
           covers=covers, not_oversized=not_oversized)
    record('M2 厚度方向正确（= h）', 'OK' if abs(zmax - zmin - 0.25) < 1e-6
           else 'FAIL', f'实测 z 厚度 {zmax - zmin:.5f} vs 期望 0.25')


def _check_close_dialogs():
    """
    关闭 DE 后检查有没有残留弹窗（「是否保存更改？」等）。

    背景：2026-09-17 用户实际遇到 CST 关项目/退出时的保存提示弹窗，
    没人点它就会把后续 CST 调用永久挂住 —— 所以收尾必须**主动检测**。
    """
    leftovers = save_prompts()
    if leftovers:
        record('关闭 DE 后的 CST 弹窗', 'FAIL',
               f'{len(leftovers)} 个未处理弹窗：'
               + '; '.join(repr(p['title']) for p in leftovers))
    else:
        record('关闭 DE 后的 CST 弹窗', 'OK',
               '无残留对话框（没有「是否保存」提示）')


def main() -> int:
    global _baseline
    _baseline = design_environment_baseline()
    print(f'基线 DE：{sorted(_baseline)}', flush=True)
    workdir = tempfile.mkdtemp(prefix='tpc_verify_v6_')
    print(f'产物目录：{workdir}', flush=True)
    try:
        probe_lens(workdir)
        probe_multipath(workdir)
    except Exception:                                 # noqa: BLE001
        record('核验过程异常', 'FAIL', traceback.format_exc(limit=3))
    finally:
        closed = close_extra_design_environments(_baseline, verbose=True)
        record('收尾', 'OK', f'关闭本次新建的 DE：{closed or "无"}')
        _check_close_dialogs()

    print('\n=== 汇总 ===')
    for entry in _results:
        print(f"{entry['status']:^7}  {entry['item']}")
    failed = [r for r in _results if r['status'] == 'FAIL']
    print(f'\nOK {len([r for r in _results if r["status"] == "OK"])} / '
          f'FAIL {len(failed)} / UNKNOWN '
          f'{len([r for r in _results if r["status"] == "UNKNOWN"])}')
    print(json.dumps(_results, ensure_ascii=False))
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
