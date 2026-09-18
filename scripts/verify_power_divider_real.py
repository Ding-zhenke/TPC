# -*- coding: utf-8 -*-
r"""
P5「PowerDivider 模板」真机验收（**只建模，不求解**）
===================================================

离线部分（分路数/级联结构/端口与馈源/透镜相位校验）由
`topo_templates/tests/test_power_divider.py`（20 项）钉住；
**本脚本补的是「CST 到底接不接受这套 VBA」**，四种分路数各建一次：
**1 分 2 / 1 分 3 / 1 分 4（2×2 级联）/ 1 分 6（2×3 级联）**。

建的东西（设计记录 D1：本库口径 —— 中心线派生 + 多路径并集，不是 notebook 复刻）：

1. 材料 → **多路径基板**（主干 + 所有输出路径）
2. **多路径 VPC 区域**（上下半区各并成一个实体）
3. **逐输出分支的晶体阵列**（阵列次数走参数引用 `int(xup)`）
4. **逐分支裁剪**（`vpc intersect g{k}A`）
5. **单馈源**（AB 型 `feed1`）+ **单铜波导** `wg1` + **1 个端口**（面 `'10'`）

⚠️ 为了分钟级完成：用**小尺寸**（`trunk_length=4 / arm_length=3 / sub_length=2`）。
**不求解**：只 `build_all()` + `save()`。

用法
----
    python scripts/verify_power_divider_real.py
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
SMALL = dict(trunk_length=4, arm_length=3, sub_length=2)
SPLIT_RATIOS = (2, 3, 4, 6)
#: 透镜验收用的小孔阵（`insitu` 的象限孔数 = 91，分钟级完成）
LENS_SMALL = dict(lens_layers=10, lens_d0_layers=3)

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


def run_lens_cases(workdir, PowerDivider, template):
    """两条透镜路线各建一次：`generate`（现算 + 落 DXF）与 `insitu`（不落 DXF）。

    ⚠️ 这段是**补历史缺口**：模板原先没登记 `Rbig`/`Ls`，而
    `build_grin_lens_from_dxf` 对它们有前置拦截 ⇒ 透镜路线在真机上根本走不通；
    本脚本以前也完全没碰透镜（`lens` 一词都没出现）。
    """
    from cst_dialog_guard import guard

    cases = (
        ('generate', {'lens_method': 'generate'}, True),
        ('insitu', dict(lens_method='insitu', **LENS_SMALL), False),
    )
    for tag, lens_kwargs, writes_dxf in cases:
        output = os.path.join(workdir, f'divider_lens_{tag}.cst')
        divider = None
        error = None
        try:
            with guard(f'1分4 + 透镜({tag}) 构造+建模+保存', timeout=2400):
                divider = PowerDivider(
                    split_ratio=4, template_cst=template, output_path=output,
                    lens_phase=(30, 10), lens_name='lens_epc',
                    lens_dxf_out=os.path.join(workdir, f'div_lens_{tag}.dxf'),
                    **SMALL, **lens_kwargs)
                divider.build_all()
                divider.save(output)
        except Exception as exc:                        # noqa: BLE001
            error = f'{type(exc).__name__}: {exc}'
            record(f'1分4+透镜({tag}) 建模', 'FAIL', error,
                   traceback=traceback.format_exc(limit=5))
        finally:
            if divider is not None:
                messages = _messages(divider.app)
                record(f'1分4+透镜({tag}) 建模',
                       'OK' if error is None and not messages else 'FAIL',
                       error or f'未抛异常；CST 消息 {len(messages)} 条',
                       messages=messages[:3],
                       lens=divider.lens_summary())
                try:
                    divider.close()
                except Exception:                   # noqa: BLE001
                    pass
        if error is not None:
            continue

        code = '\n'.join(_history_code(output))
        params = _history_params(output)
        # ① DXF 落盘与否，必须与路线声明一致（"不落 DXF" 是可验证的承诺）
        dxf_path = os.path.join(workdir, f'div_lens_{tag}.dxf')
        has_dxf = os.path.isfile(dxf_path)
        has_import = 'Import' in code
        record(f'1分4+透镜({tag}) 路线语义一致（落 DXF ?= {writes_dxf}）',
               'OK' if (has_dxf == writes_dxf and has_import == writes_dxf) else 'FAIL',
               f'DXF 文件{"在" if has_dxf else "不在"}、历史里 DXF 导入'
               f'{"在" if has_import else "不在"}')
        # ② Rbig 必须有；Ls 只有 DXF 路线要（就地路线登记它就是死写入）
        want_ls = tag != 'insitu'
        ok = 'Rbig' in params and (('Ls' in params) == want_ls)
        record(f'1分4+透镜({tag}) 前置参数口径（Rbig 必有 / Ls 按路线）',
               'OK' if ok else 'FAIL',
               f"Rbig={params.get('Rbig')} Ls={params.get('Ls')} "
               f"（该路线 {'要' if want_ls else '不要'} Ls）")
        # ③ 相位：给了两个角度 ⇒ 必须有一次 rotation 复制，且**打在真实实体的组件上**
        #    （DXF 路线的实体在 `component1`、就地路线在 `lens_component` —— 真机教训）
        captions_raw = _history_captions(output)
        captions = ' '.join(captions_raw)
        want_component = 'component1' if tag != 'insitu' else divider.lens_component
        record(f'1分4+透镜({tag}) 相位副本（rotation 出现且组件正确）',
               'OK' if f'rotation {divider.lens_name}' in captions
               and ('dphi1' in params) else 'FAIL',
               f"dphi1={params.get('dphi1')} dphi2={params.get('dphi2')}；"
               f"rotation 出现在历史 caption 里；实体组件应为 {want_component}")
        # ④ 就地路线：逐 hexagon 建环 + 组件口径
        if tag == 'insitu':
            ring = divider.make_lens_ring()
            n = len(ring['holes'])
            n_hex = sum(1 for line in _history_captions(output)
                        if line.strip().startswith('Hexagon: lens_epc-'))
            record('1分4+透镜(insitu) 逐 hexagon 建环',
                   'OK' if n_hex == n else 'FAIL',
                   f'历史里 Hexagon 条目 {n_hex} 条（离线象限孔 {n} 个）')
            n_bad = code.count('"component1:lens_epc')
            record('1分4+透镜(insitu) 变换/布尔指向正确组件',
                   'OK' if not n_bad else 'FAIL',
                   f'误指 component1 的指令 {n_bad} 条')
        # ⑤ 相位旋转必须打在**真实存在**的实体名上
        #    （真机教训：就地路线的最终实体曾叫 `{name}-sub`，相位旋转打到
        #     `lens_epc` ⇒ CST 报 `Shape does not exist: gridlens:lens_epc`）
        captions = ' '.join(_history_captions(output))
        record(f'1分4+透镜({tag}) 相位旋转指向真实实体',
               'OK' if f'rotation {divider.lens_name}' in captions else 'FAIL',
               f"历史里出现 `rotation {divider.lens_name}`")


def run_switch_case(workdir, PowerDivider, template):
    """开关/泵浦区真机验收（`pump_switching` 能力）。

    参考做法（`Ant2_1div2_BA_120D_epc.ipynb` / `Ant6_2H4L_epc.ipynb`）：
    `create_material_custom` + 圆柱 + **区域副本求交** + `insert` 回区域。
    """
    from cst_dialog_guard import guard

    tag = 'switch'
    output = os.path.join(workdir, 'divider_switch.cst')
    divider = None
    error = None
    try:
        with guard('1分3 + 开关 构造+建模+保存', timeout=2400):
            divider = PowerDivider(split_ratio=3, template_cst=template,
                                   output_path=output, switch_mode='arm_mid',
                                   switch_sigma=100, **SMALL)
            divider.build_all()
            divider.save(output)
    except Exception as exc:                            # noqa: BLE001
        error = f'{type(exc).__name__}: {exc}'
        record(f'1分3+开关({tag}) 建模', 'FAIL', error,
               traceback=traceback.format_exc(limit=5))
    finally:
        if divider is not None:
            messages = _messages(divider.app)
            record(f'1分3+开关({tag}) 建模',
                   'OK' if error is None and not messages else 'FAIL',
                   error or f'未抛异常；CST 消息 {len(messages)} 条',
                   messages=messages[:3],
                   switch_positions=divider.switch_positions())
            try:
                divider.close()
            except Exception:                       # noqa: BLE001
                pass
    if error is not None:
        return

    code = '\n'.join(_history_code(output))
    params = _history_params(output)
    n_sw = len(divider.switch_positions())
    record('1分3+开关 半径/电导率是 CST 参数',
           'OK' if 'rc1' in params and 'sigma1' in params else 'FAIL',
           f"rc1={params.get('rc1')} sigma1={params.get('sigma1')}")
    n_cyl = code.count('With Cylinder')
    n_inter = code.count('Solid.Intersect')
    n_insert = code.count('Solid.Insert')
    record('1分3+开关 每个开关都走「圆柱 + 区域副本求交 + insert」',
           'OK' if (n_cyl >= n_sw and n_inter >= n_sw and n_insert >= n_sw)
           else 'FAIL',
           f'开关 {n_sw} 个 ⇒ Cylinder {n_cyl} 条 / Intersect {n_inter} 条 / '
           f'Insert {n_insert} 条')
    record('1分3+开关 自定义材料已建',
           'OK' if 'switch1' in code else 'FAIL',
           '历史里出现 switch1（epsilon=11.9 + kappa=sigma1）')


def _history_params(project_path):
    """保存后的参数表（名字 → 值文本）。"""
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


def run(workdir):
    from cst_dialog_guard import check_dialogs, describe_dialogs, guard
    from topo_templates import PowerDivider

    check_dialogs('开工前')
    print(f'开工前 CST 对话框：\n{describe_dialogs()}', flush=True)
    template = os.path.join(workdir, 'tmp_div.cst')
    shutil.copy2(CLEAN_TEMPLATE, template)

    for ratio in SPLIT_RATIOS:
        output = os.path.join(workdir, f'divider_1div{ratio}.cst')
        divider = None
        error = None
        try:
            with guard(f'1分{ratio} 构造+建模+保存', timeout=1800):
                divider = PowerDivider(split_ratio=ratio, template_cst=template,
                                       output_path=output, **SMALL)
                divider.build_all()
                divider.save(output)
        except Exception as exc:                        # noqa: BLE001
            error = f'{type(exc).__name__}: {exc}'
            record(f'1分{ratio} 建模', 'FAIL', error,
                   traceback=traceback.format_exc(limit=5))
        finally:
            if divider is not None:
                messages = _messages(divider.app)
                record(f'1分{ratio} 建模（多路径 + 单馈源 + 1 端口）',
                       'OK' if error is None and not messages else 'FAIL',
                       error or f'未抛异常；CST 消息 {len(messages)} 条',
                       messages=messages[:3],
                       paths=len(divider.output_paths()),
                       array_range=list(divider.modeler.array_range()))
                try:
                    divider.close()
                except Exception:                   # noqa: BLE001
                    pass

        code = '\n'.join(_history_code(output))
        if not code:
            record(f'1分{ratio} 历史取证', 'FAIL', '读不到 ModelHistory.json')
            continue
        n_intersect = code.count('Solid.Intersect')
        want = ratio * 2
        record(f'1分{ratio} H1 多路径并集 + 逐分支裁剪',
               'OK' if 'Solid.Add' in code and n_intersect >= want else 'FAIL',
               f'Solid.Add 在；Solid.Intersect {n_intersect} 条（期望 ≥ {want} '
               f'= {ratio} 分支 × 2 晶体）')
        record(f'1分{ratio} H2 阵列次数是参数引用',
               'OK' if 'int(xup)' in code and 'int(ydn/2)' in code else 'FAIL',
               '历史里出现 int(xup) / int(yup/2) / int(ydn/2)')
        record(f'1分{ratio} H3 单端口 + 单馈源',
               'OK' if 'feed1' in code and 'wg1' in code else 'FAIL',
               'feed1 / wg1 都在历史里')

    # ---- 透镜路线（原先**完全没验过**；模板当时连 Rbig/Ls 都没登记）----
    run_lens_cases(workdir, PowerDivider, template)

    # ---- 开关/泵浦区（`pump_switching`：自定义材料 + 圆柱 + 区域副本求交 + insert）----
    run_switch_case(workdir, PowerDivider, template)

    # 参数闭合性：只查最后一个工程（规模固定，代表性足够）
    last = os.path.join(workdir, f'divider_1div{SPLIT_RATIOS[-1]}.cst')
    try:
        import verify_model_parameter_usage as usage

        template_table, _ = usage.load_parameters(r'D:\TPC_out\tmp')
        before = len(usage.RESULTS)
        result = usage.audit_project(usage.resolve_project(last), template_table,
                                     label='功分器')
        for entry in usage.RESULTS[before:]:
            _results.append(entry)
            print(f'[{entry["status"]:^7}] {entry["item"]}: {entry["detail"]}',
                  flush=True)
        if result:
            record('H4 库下发参数没有死写入',
                   'FAIL' if result['dead_writes'] else 'OK',
                   f'死写入：{result["dead_writes"] or "无"}'
                   f'（已引用 {result["used"]} / 共 {result["defined"]}）')
    except Exception as exc:                            # noqa: BLE001
        record('H4 参数闭合性', 'UNKNOWN', f'{type(exc).__name__}: {exc}')


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
    workdir = args.workdir or tempfile.mkdtemp(prefix='tpc_div_')
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
