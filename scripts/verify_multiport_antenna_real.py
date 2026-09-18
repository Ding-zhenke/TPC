# -*- coding: utf-8 -*-
r"""
P5「MultiPortAntenna 模板」真机验收（**只建模，不求解**）
=======================================================

离线部分（拓扑/端口/参数登记/馈源族覆盖）由
`topo_templates/tests/test_multiport_antenna.py`（15 项）与
`tests/test_template_param_registration.py`（14 项）钉住；
**本脚本补的是「CST 到底接不接受这套 VBA」**。

建的东西（设计记录 D1：本库口径 —— 中心线派生 + 多路径并集，**不是** notebook 的
逐字节复刻）：

1. 材料 → **多路径基板**（主干 + 两条分支）
2. **多路径 VPC 区域**（上/下半区各并成一个实体）
3. **逐分支晶体阵列**（阵列次数走参数引用 `int(xup)`）
4. **逐分支裁剪**（`vpc intersect g{k}A`，每条分支都被吸收）
5. **双馈源**：AB 型 `feed1` + BA 型 `feed2`（两族参数都要登记）
6. **两条铜波导**：AB 范围 `[-lf1-lf2-lf3, -lf1]` + BA 范围 `[-lf5-lf6-lf4, -lf4]`
7. **3 个端口**（编号由模板参数给；面号 `'10'`/`'22'`）

⚠️ 为了分钟级完成：天线用**小尺寸**（`straight_length=4 / arm_length=3`），
阵列范围随之变小。**不求解**：只 `build_all()` + `save()`。

用法
----
    python scripts/verify_multiport_antenna_real.py
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
SMALL = dict(straight_length=4, arm_length=3)

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


def run_lens_cases(workdir, MultiPortAntenna, template):
    """两条透镜路线各建一次（`generate` 落 DXF / `insitu` 不落 DXF）。

    参考口径（`MPMBA\\Ant3_epc.ipynb`）：**单枚透镜、近焦点在原点** ——
    没有 `Rbig` 平移、没有 6 份旋转复制 ⇒ 本模板用 `place=False`，
    也因此**不应登记 `Rbig`**（登记了就是死写入）。
    """
    from cst_dialog_guard import guard

    cases = (('generate', {'lens_method': 'generate'}, True),
             ('insitu', dict(lens_method='insitu', lens_layers=10,
                             lens_d0_layers=3), False))
    for tag, lens_kwargs, writes_dxf in cases:
        output = os.path.join(workdir, f'multiport_lens_{tag}.cst')
        antenna = None
        error = None
        try:
            with guard(f'多端口+透镜({tag}) 构造+建模+保存', timeout=2400):
                antenna = MultiPortAntenna(
                    template_cst=template, output_path=output,
                    lens_dxf_out=os.path.join(workdir, f'mp_lens_{tag}.dxf'),
                    **SMALL, **lens_kwargs)
                antenna.build_all()
                antenna.save(output)
        except Exception as exc:                        # noqa: BLE001
            error = f'{type(exc).__name__}: {exc}'
            record(f'多端口+透镜({tag}) 建模', 'FAIL', error,
                   traceback=traceback.format_exc(limit=5))
        finally:
            if antenna is not None:
                messages = _messages(antenna.app)
                record(f'多端口+透镜({tag}) 建模',
                       'OK' if error is None and not messages else 'FAIL',
                       error or f'未抛异常；CST 消息 {len(messages)} 条',
                       messages=messages[:3], lens=antenna.lens_summary())
                try:
                    antenna.close()
                except Exception:                   # noqa: BLE001
                    pass
        if error is not None:
            continue

        code = '\n'.join(_history_code(output))
        params = _history_params(output)
        dxf_path = os.path.join(workdir, f'mp_lens_{tag}.dxf')
        has_dxf = os.path.isfile(dxf_path)
        has_import = 'Import' in code
        record(f'多端口+透镜({tag}) 路线语义一致（落 DXF ?= {writes_dxf}）',
               'OK' if (has_dxf == writes_dxf and has_import == writes_dxf) else 'FAIL',
               f'DXF 文件{"在" if has_dxf else "不在"}、历史里 DXF 导入'
               f'{"在" if has_import else "不在"}')
        # 参考口径：单枚、放原点 ⇒ 不该有 Rbig（登记了就是死写入）
        record(f'多端口+透镜({tag}) 单枚透镜、没有多余的 Rbig',
               'OK' if 'Rbig' not in params else 'FAIL',
               f"Rbig={params.get('Rbig')}（该口径不需要）；"
               f"Ls={params.get('Ls')}")
        captions = ' '.join(_history_captions(output))
        has_rot = f'rotation {antenna.lens_name}' in captions
        record(f'多端口+透镜({tag}) 单枚（没有旋转复制）',
               'OK' if not has_rot else 'FAIL',
               '历史 caption 里没有该透镜的 rotation 条目'
               if not has_rot else '出现了旋转复制，说明 place 没生效')
        if tag == 'insitu':
            ring = antenna.make_lens_ring()
            n_hex = sum(1 for line in _history_captions(output)
                        if line.strip().startswith('Hexagon: lens_epc-'))
            record('多端口+透镜(insitu) 逐 hexagon 建环',
                   'OK' if n_hex == len(ring['holes']) else 'FAIL',
                   f'历史里 Hexagon 条目 {n_hex} 条（离线象限孔 '
                   f'{len(ring["holes"])} 个）')
            n_bad = code.count('"component1:lens_epc')
            record('多端口+透镜(insitu) 变换/布尔指向正确组件',
                   'OK' if not n_bad else 'FAIL',
                   f'误指 component1 的指令 {n_bad} 条')


def run(workdir):
    from cst_dialog_guard import check_dialogs, describe_dialogs, guard
    from topo_templates import MultiPortAntenna

    check_dialogs('开工前')
    print(f'开工前 CST 对话框：\n{describe_dialogs()}', flush=True)
    template = os.path.join(workdir, 'tmp_mpa.cst')
    shutil.copy2(CLEAN_TEMPLATE, template)
    output = os.path.join(workdir, 'multiport_antenna.cst')

    antenna = None
    error = None
    try:
        with guard('多端口天线 构造+建模+保存', timeout=1800):
            antenna = MultiPortAntenna(template_cst=template, output_path=output,
                                       **SMALL)
            antenna.build_all()
            antenna.save(output)
    except Exception as exc:                            # noqa: BLE001
        error = f'{type(exc).__name__}: {exc}'
        record('建模', 'FAIL', error, traceback=traceback.format_exc(limit=5))
    finally:
        if antenna is not None:
            messages = _messages(antenna.app)
            record('多端口天线建模（多路径 + 双馈源 + 3 端口）',
                   'OK' if error is None and not messages else 'FAIL',
                   error or f'未抛异常；CST 消息 {len(messages)} 条',
                   messages=messages[:3])
            parts = getattr(antenna, '_parts', {})
            record('部件清单', 'OK' if parts.get('ports') else 'FAIL',
                   f"晶体 {len(parts.get('crystals', {}))} 套、"
                   f"端口 {len(parts.get('ports', []))} 个、"
                   f"feed1={parts.get('feed1')}、feed2={parts.get('feed2')}、"
                   f"wg1={parts.get('wg1', {}).get('name') if isinstance(parts.get('wg1'), dict) else parts.get('wg1')}",
                   clip=parts.get('clip'))
            try:
                antenna.close()
            except Exception:                       # noqa: BLE001
                pass

    code = '\n'.join(_history_code(output))
    if not code:
        record('历史取证', 'FAIL', '读不到 ModelHistory.json')
        return
    record('历史取证', 'OK', f'{len(code.splitlines())} 行 VBA')

    record('H1 多路径并集（Solid.Add）', 'OK' if 'Solid.Add' in code else 'FAIL',
           '基板/VPC 各分支并成一个实体')
    # 3 条分支 × 2 个晶体（A/B）= 6 条 Intersect
    n_intersect = code.count('Solid.Intersect')
    record('H2 每条分支的晶体都被裁（Intersect 条数）',
           'OK' if n_intersect >= 6 else 'FAIL',
           f'实测 {n_intersect} 条（期望 ≥ 6 = 3 分支 × 2 晶体）')
    names = ['vpc_A', 'vpc_B', 'feed1', 'feed2', 'wg1', 'wg2']
    missing = [n for n in names if n not in code]
    record('H3 关键实体名齐全', 'OK' if not missing else 'FAIL',
           f'缺 {missing}' if missing else 'vpc_A/vpc_B + feed1/feed2 + wg1/wg2 都在')
    record('H4 阵列次数是参数引用',
           'OK' if 'int(xup)' in code and 'int(ydn/2)' in code else 'FAIL',
           '历史里出现 int(xup) / int(yup/2) / int(ydn/2)')

    # 参数闭合性（复用 P4 §8.7 的工具）：死写入必须是 0
    try:
        import verify_model_parameter_usage as usage

        template_table, _ = usage.load_parameters(r'D:\TPC_out\tmp')
        before = len(usage.RESULTS)
        result = usage.audit_project(usage.resolve_project(output), template_table,
                                     label='多端口天线')
        for entry in usage.RESULTS[before:]:
            _results.append(entry)
            print(f'[{entry["status"]:^7}] {entry["item"]}: {entry["detail"]}',
                  flush=True)
        if result:
            record('H5 库下发参数没有死写入',
                   'FAIL' if result['dead_writes'] else 'OK',
                   f'死写入：{result["dead_writes"] or "无"}'
                   f'（已引用 {result["used"]} / 共 {result["defined"]}）')
    except Exception as exc:                            # noqa: BLE001
        record('H5 参数闭合性', 'UNKNOWN', f'{type(exc).__name__}: {exc}')

    # ---- 透镜路线（参考里 6 个多端口 notebook 都带透镜，原先完全没验过）----
    run_lens_cases(workdir, MultiPortAntenna, template)


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
    workdir = args.workdir or tempfile.mkdtemp(prefix='tpc_mpa_')
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
