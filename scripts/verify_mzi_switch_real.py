# -*- coding: utf-8 -*-
r"""
P5「MZISwitch 模板」真机验收（**只建模，不求解**）
================================================

离线部分（路径方向序列/阵列范围公式/mzi_type 语义/参数登记）由
`topo_templates/tests/test_mzi_switch.py`（15 项）钉住；
**本脚本补的是「CST 到底接不接受这套 VBA」**。

建的东西（设计记录 D1：本库口径 —— 中心线派生，不是 notebook 逐字节复刻）：

1. 材料（含自定义 `m1`：Epsilon 11.9 / Sigma=sigma1）
2. VPC 区域（上半区 + 下半区）→ 光子晶体阵列 → 裁剪
3. AB 型探针 `feed1` + **关于 x 中点镜像** ⇒ 两个端口臂
4. 耦合区矩形 `pump1`（`ax`/`ay`）+ 关于 y 镜像 + 与 vpca 求并
5. 开关圆柱 `pump2`（材料 `m1`）→ 与 vpca 求交后 **insert** 回去
6. **2 个端口**：直接建在 `feed1` 的两个端面上（面 `'14'`/`'4'`，`shield='electric'`）

⚠️ 为了分钟级完成：用**小尺寸**（`arm_x1=4 / mid_x2=4 / arm_gap_y1=2`）。
**不求解**：只 `build_all()` + `save()`。

用法
----
    python scripts/verify_mzi_switch_real.py
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
for _extra in (PROJECT_ROOT, Path(__file__).resolve().parent):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

from topo_modeler.batch import (                        # noqa: E402
    close_extra_design_environments,
    design_environment_baseline,
    design_environment_query,
)

CLEAN_TEMPLATE = r'D:\TPC_out\tmp.cst'
SMALL = dict(arm_x1=4, mid_x2=4, arm_gap_y1=2)

_results = []
_baseline = set()


def record(item, status, detail, **extra):
    entry = {'item': item, 'status': status, 'detail': detail}
    entry.update(extra)
    _results.append(entry)
    text = '  ' + json.dumps(extra, ensure_ascii=False, default=str) if extra else ''
    print(f'[{status:^7}] {item}: {detail}{text}', flush=True)
    return entry


def _messages(app):
    try:
        return [str(m) for m in (app.cst_file.get_messages() or [])]
    except Exception as exc:                            # noqa: BLE001
        return [f'<读消息失败 {type(exc).__name__}: {exc}>']


def _history_code(project_path):
    path = os.path.join(os.path.splitext(project_path)[0], 'Model', '3D',
                        'ModelHistory.json')
    if not os.path.isfile(path):
        return []
    with open(path, encoding='utf-8-sig') as handle:
        data = json.load(handle)
    return [line for entry in data.get('history', [])
            for line in entry.get('code', [])]


def run(workdir):
    from cst_dialog_guard import check_dialogs, describe_dialogs, guard
    from topo_templates import MZISwitch

    check_dialogs('开工前')
    print(f'开工前 CST 对话框：\n{describe_dialogs()}', flush=True)
    template = os.path.join(workdir, 'tmp_mzi.cst')
    shutil.copy2(CLEAN_TEMPLATE, template)
    output = os.path.join(workdir, 'mzi_switch.cst')

    mzi = None
    error = None
    try:
        with guard('MZI 构造+建模+保存', timeout=1800):
            mzi = MZISwitch(template_cst=template, output_path=output, **SMALL)
            mzi.build_all()
            mzi.save(output)
    except Exception as exc:                            # noqa: BLE001
        error = f'{type(exc).__name__}: {exc}'
        record('建模', 'FAIL', error, traceback=traceback.format_exc(limit=5))
    finally:
        if mzi is not None:
            messages = _messages(mzi.app)
            record('MZI 建模（探针镜像 + 耦合区 + 圆柱 + 2 端口）',
                   'OK' if error is None and not messages else 'FAIL',
                   error or f'未抛异常；CST 消息 {len(messages)} 条',
                   messages=messages[:3])
            parts = getattr(mzi, '_parts', {})
            record('部件清单', 'OK' if parts.get('ports') else 'FAIL',
                   f"端口 {len(parts.get('ports', []))} 个、feed={parts.get('feed')}、"
                   f"pump1={parts.get('pump1')}、pump2={parts.get('pump2')}、"
                   f"材料={parts.get('material')}",
                   clip=parts.get('clip'))
            try:
                mzi.close()
            except Exception:                       # noqa: BLE001
                pass

    code = '\n'.join(_history_code(output))
    if not code:
        record('历史取证', 'FAIL', '读不到 ModelHistory.json')
        return
    record('历史取证', 'OK', f'{len(code.splitlines())} 行 VBA')

    checks = [
        ('H1 布尔并（Solid.Add）', 'Solid.Add' in code),
        ('H2 圆柱（Cylinder）', 'Cylinder' in code or 'circle' in code.lower()),
        ('H3 求交（Solid.Intersect）', 'Solid.Intersect' in code),
        ('H4 insert 回并', 'Solid.Insert' in code),
        ('H5 镜像（探针/耦合区）', 'Transform.Mirror' in code or 'Mirror' in code),
        ('H6 阵列次数是参数引用',
         'int(xup)' in code and 'int(ydn/2)' in code),
    ]
    for label, ok in checks:
        record(label, 'OK' if ok else 'FAIL', '历史里可见' if ok else '历史里没找到')

    # 参数闭合性（复用 P4 §8.7 的工具）：死写入必须是 0
    try:
        import verify_model_parameter_usage as usage

        template_table, _ = usage.load_parameters(r'D:\TPC_out\tmp')
        before = len(usage.RESULTS)
        result = usage.audit_project(usage.resolve_project(output), template_table,
                                     label='MZI')
        for entry in usage.RESULTS[before:]:
            _results.append(entry)
            print(f'[{entry["status"]:^7}] {entry["item"]}: {entry["detail"]}',
                  flush=True)
        if result:
            record('H7 库下发参数没有死写入',
                   'FAIL' if result['dead_writes'] else 'OK',
                   f'死写入：{result["dead_writes"] or "无"}'
                   f'（已引用 {result["used"]} / 共 {result["defined"]}）')
    except Exception as exc:                            # noqa: BLE001
        record('H7 参数闭合性', 'UNKNOWN', f'{type(exc).__name__}: {exc}')

    # ---- 透镜路线（参考 `MZI-GRIB.ipynb` 的活代码环透镜，原先完全没验过）----
    run_lens_cases(workdir, MZISwitch, template)


def _history_params(project_path):
    path = os.path.join(os.path.splitext(project_path)[0], 'Model',
                        'Parameters.json')
    if not os.path.isfile(path):
        return {}
    with open(path, encoding='utf-8-sig') as handle:
        data = json.load(handle)
    return {p['name']: p.get('value') for p in data.get('parameters', [])}


def _history_captions(project_path):
    path = os.path.join(os.path.splitext(project_path)[0], 'Model', '3D',
                        'ModelHistory.json')
    if not os.path.isfile(path):
        return []
    with open(path, encoding='utf-8-sig') as handle:
        data = json.load(handle)
    return [str(entry.get('caption') or '') for entry in data.get('history', [])]


def run_lens_cases(workdir, MZISwitch, template):
    """两条透镜路线各建一次（`generate` 落 DXF / `insitu` **不落 DXF**）。

    参考口径（`开关尝试/AB/MZI-GRIB.ipynb`）：**单枚、近焦点在原点**
    ⇒ `place=False`，因此**不应登记 `Rbig`**（登记了就是死写入）。
    """
    from cst_dialog_guard import guard

    cases = (('generate', {'lens_method': 'generate'}, True),
             ('insitu', dict(lens_method='insitu', lens_layers=10,
                             lens_d0_layers=3), False))
    for tag, lens_kwargs, writes_dxf in cases:
        output = os.path.join(workdir, f'mzi_lens_{tag}.cst')
        mzi = None
        error = None
        try:
            with guard(f'MZI+透镜({tag}) 构造+建模+保存', timeout=2400):
                mzi = MZISwitch(template_cst=template, output_path=output,
                                lens_dxf_out=os.path.join(workdir,
                                                          f'mzi_{tag}.dxf'),
                                **SMALL, **lens_kwargs)
                mzi.build_all()
                mzi.save(output)
        except Exception as exc:                        # noqa: BLE001
            error = f'{type(exc).__name__}: {exc}'
            record(f'MZI+透镜({tag}) 建模', 'FAIL', error,
                   traceback=traceback.format_exc(limit=5))
        finally:
            if mzi is not None:
                messages = _messages(mzi.app)
                record(f'MZI+透镜({tag}) 建模',
                       'OK' if error is None and not messages else 'FAIL',
                       error or f'未抛异常；CST 消息 {len(messages)} 条',
                       messages=messages[:3], lens=mzi.lens_summary())
                try:
                    mzi.close()
                except Exception:                   # noqa: BLE001
                    pass
        if error is not None:
            continue

        code = '\n'.join(_history_code(output))
        params = _history_params(output)
        dxf_path = os.path.join(workdir, f'mzi_{tag}.dxf')
        has_dxf = os.path.isfile(dxf_path)
        has_import = 'Import' in code
        record(f'MZI+透镜({tag}) 路线语义一致（落 DXF ?= {writes_dxf}）',
               'OK' if (has_dxf == writes_dxf and has_import == writes_dxf) else 'FAIL',
               f'DXF 文件{"在" if has_dxf else "不在"}、历史里 DXF 导入'
               f'{"在" if has_import else "不在"}')
        record(f'MZI+透镜({tag}) 单枚透镜、没有多余的 Rbig',
               'OK' if 'Rbig' not in params else 'FAIL',
               f"Rbig={params.get('Rbig')}（该口径不需要）；Ls={params.get('Ls')}")
        captions = ' '.join(_history_captions(output))
        has_rot = f'rotation {mzi.lens_name}' in captions
        record(f'MZI+透镜({tag}) 单枚（没有旋转复制）',
               'OK' if not has_rot else 'FAIL',
               '历史 caption 里没有该透镜的 rotation 条目'
               if not has_rot else '出现了旋转复制，说明 place 没生效')
        if tag == 'insitu':
            ring = mzi.make_lens_ring()
            n_hex = sum(1 for line in _history_captions(output)
                        if line.strip().startswith('Hexagon: lens_epc-'))
            record('MZI+透镜(insitu) 逐 hexagon 建环',
                   'OK' if n_hex == len(ring['holes']) else 'FAIL',
                   f'历史里 Hexagon 条目 {n_hex} 条（离线象限孔 '
                   f'{len(ring["holes"])} 个）')
            n_bad = code.count('"component1:lens_epc')
            record('MZI+透镜(insitu) 变换/布尔指向正确组件',
                   'OK' if not n_bad else 'FAIL',
                   f'误指 component1 的指令 {n_bad} 条')


def main(argv=None):
    global _baseline
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument('--workdir', default=None)
    args = parser.parse_args(argv)

    try:
        import cst_solver

        lib = cst_solver.CST_PYTHON_LIB
        if lib and lib not in sys.path:
            sys.path.append(lib)
    except Exception as exc:                            # noqa: BLE001
        record('cst.interface 准备', 'WARN', f'{type(exc).__name__}: {exc}')

    _baseline = design_environment_baseline()
    print(f'基线 DE：{sorted(_baseline)}', flush=True)
    workdir = args.workdir or tempfile.mkdtemp(prefix='tpc_mzi_')
    os.makedirs(workdir, exist_ok=True)
    print(f'产物目录：{workdir}', flush=True)

    try:
        run(workdir)
    except Exception:                                   # noqa: BLE001
        record('核验过程异常', 'FAIL', traceback.format_exc(limit=3))
    finally:
        closed = close_extra_design_environments(_baseline, verbose=True)
        record('收尾', 'OK', f'关闭本次新建的 DE：{closed or "无"}')
        query = design_environment_query()
        record('收尾后的 DE', 'OK' if query['ok'] else 'UNKNOWN',
               f'{query["pids"]}（基线 {sorted(_baseline)}）'
               if query['ok'] else query['reason'])

    print('\n=== 汇总 ===')
    for entry in _results:
        print(f"{entry['status']:^7}  {entry['item']}")
    failed = [r for r in _results if r['status'] == 'FAIL']
    print(f'\nOK {len([r for r in _results if r["status"] == "OK"])} / '
          f'INFO {len([r for r in _results if r["status"] == "INFO"])} / '
          f'WARN {len([r for r in _results if r["status"] == "WARN"])} / '
          f'FAIL {len(failed)}')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
