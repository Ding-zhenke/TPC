# -*- coding: utf-8 -*-
r"""
P5「GRINLensAntenna 模板」真机验收（**只建模，不求解**）
=======================================================

离线部分（几何一致、两条入口、`Rbig`/`Ls` 登记、天线部分未改坏）由
`topo_templates/tests/test_grin_lens_antenna.py`（14 项）钉住；
**本脚本补的是「CST 到底接不接受这套 VBA」**：

* A：`lens_method='generate'` —— 现算孔阵列 → 落 DXF → 建 6 个透镜；
* B：`lens_method='dxf'` —— 拿 A 落下的 DXF 当「别人的 DXF」再建一次
  （**不回头算几何**，孔数统计为 `None`）；
* C：落盘取证 —— 历史里要有 DXF 导入、椭圆拉伸、减孔、旋转复制；
  参数表里要有 `Rbig` / `Ls`（缺了它们 CST 会弹「输入变量值」模态对话框挂住）。

⚠️ 为了分钟级完成：天线用**小尺寸**（`straight_length=6 / arm_length=8`，
阵列 10/8/8），透镜用默认 `nx=16/ny=13`（上半 373 条多段线）。
**不求解**：脚本只调 `build_all()`（建模 + 保存），不碰 `run`/`solve`。

用法
----
    python scripts/verify_grin_lens_antenna_real.py
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
SMALL = dict(straight_length=6, arm_length=8)

_results = []
_baseline = set()


def record(item, status, detail, **extra):
    entry = {'item': item, 'status': status, 'detail': detail}
    entry.update(extra)
    _results.append(entry)
    extra_text = '  ' + json.dumps(extra, ensure_ascii=False, default=str) if extra else ''
    print(f'[{status:^7}] {item}: {detail}{extra_text}', flush=True)
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


def _params(project_path):
    path = os.path.join(os.path.splitext(project_path)[0], 'Model',
                        'Parameters.json')
    if not os.path.isfile(path):
        return {}
    with open(path, encoding='utf-8-sig') as handle:
        data = json.load(handle)
    return {p['name']: p.get('value') for p in data.get('parameters', [])}


def _build(workdir, tag, template_path, output, **lens_kwargs):
    """建一个工程（建模 + 保存），返回 (模板对象, 错误文本或 None)。"""
    from cst_dialog_guard import guard
    from topo_templates import GRINLensAntenna

    antenna = None
    error = None
    try:
        with guard(f'{tag} 构造+建模+保存', timeout=900):
            antenna = GRINLensAntenna(
                bend_angle=120, topology='AB', template_cst=template_path,
                output_path=output, lens_dxf_out=os.path.join(workdir, f'{tag}.dxf'),
                **SMALL, **lens_kwargs)
            antenna.build_all()
            antenna.save(output)
    except Exception as exc:                            # noqa: BLE001
        error = f'{type(exc).__name__}: {exc}'
        if antenna is not None and antenna.app is not None:
            record(f'{tag} 建模', 'FAIL', error,
                   messages=_messages(antenna.app)[:3],
                   traceback=traceback.format_exc(limit=4))
            return antenna, error
    finally:
        pass
    messages = _messages(antenna.app) if antenna is not None else []
    record(f'{tag} 建模（含透镜）', 'OK' if error is None and not messages else 'FAIL',
           error or f'未抛异常；CST 消息 {len(messages)} 条',
           messages=messages[:3],
           lens=antenna.lens_info if antenna is not None else None)
    try:
        if antenna is not None:
            antenna.close()
    except Exception:                                   # noqa: BLE001
        pass
    return antenna, error


def run(workdir):
    from cst_dialog_guard import check_dialogs, describe_dialogs

    check_dialogs('开工前')
    print(f'开工前 CST 对话框：\n{describe_dialogs()}', flush=True)
    template = os.path.join(workdir, 'tmp_grin.cst')
    shutil.copy2(CLEAN_TEMPLATE, template)

    # ---- A：generate 入口 ----
    out_a = os.path.join(workdir, 'grin_gen.cst')
    antenna_a, error_a = _build(workdir, 'A(generate)', template, out_a)
    dxf_a = os.path.join(workdir, 'A(generate).dxf')
    if antenna_a is not None:
        info = antenna_a.lens_info or {}
        record('A1 孔阵列已落 DXF', 'OK' if os.path.isfile(dxf_a) else 'FAIL',
               f'{os.path.basename(dxf_a)} '
               f'{os.path.getsize(dxf_a) // 1024 if os.path.isfile(dxf_a) else 0} KB',
               n_holes_total=info.get('n_holes_total'),
               n_holes_dxf=info.get('n_holes_dxf'))
        record('A2 透镜实体与几何参数', 'OK' if info.get('name') else 'FAIL',
               f"name={info.get('name')} / holes_generated={info.get('holes_generated')}"
               f" / ec_a={info.get('ec_a')} ec_c={info.get('ec_c')}")
    code_a = '\n'.join(_history_code(out_a))
    if code_a:
        missing = [kw for kw in ('Import', 'Ellipse', 'Subtract', 'Rotate')
                   if kw not in code_a]
        record('A3 历史里有透镜步骤', 'OK' if not missing else 'FAIL',
               f'缺 {missing}' if missing else
               'DXF 导入 / 椭圆 / 减孔 / 旋转复制 都在')
    params_a = _params(out_a)
    record('A4 参数表里有 Rbig / Ls',
           'OK' if {'Rbig', 'Ls'} <= set(params_a) else 'FAIL',
           f"Rbig={params_a.get('Rbig')} Ls={params_a.get('Ls')}")

    # ---- B：现成 DXF 入口 ----
    if not os.path.isfile(dxf_a):
        record('B 现成 DXF 入口', 'UNKNOWN', 'A 没产出 DXF，跳过')
        return
    out_b = os.path.join(workdir, 'grin_dxf.cst')
    antenna_b, error_b = _build(workdir, 'B(dxf)', template, out_b,
                               lens_method='dxf', lens_dxf=dxf_a)
    if antenna_b is not None:
        info = antenna_b.lens_info or {}
        record('B1 用现成 DXF 建成且不猜孔数',
               'OK' if info.get('holes_generated') is False
               and info.get('n_holes_total') is None else 'FAIL',
               f"holes_generated={info.get('holes_generated')} "
               f"n_holes_total={info.get('n_holes_total')}（现成 DXF 不回头算几何）")
    code_b = '\n'.join(_history_code(out_b))
    record('B2 两个工程的历史都含 DXF 导入',
           'OK' if 'Import' in code_b and 'Import' in code_a else 'FAIL',
           '两条入口都真的导入了 DXF')


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
    workdir = args.workdir or tempfile.mkdtemp(prefix='tpc_grin_lens_')
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
