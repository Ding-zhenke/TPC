# -*- coding: utf-8 -*-
r"""
P5「就地 hexagon 环透镜（`lens_method='insitu'`）」真机验收（**只建模，不求解**）
=============================================================================

背景
----
参考工程里有 **33 个 notebook** 的透镜是「在 CST 里逐个 `hexagon` 建孔 → 镜像 →
圆柱切半 → 取孔阵负形」（`功分器加天线\1分4\…circle_DF.ipynb`），
而本库原先只有「算孔阵列 → 落 DXF → `dxf_import`」那条路。
离线几何与下发序列由 `topo_modeler/tests/test_grin_lens_insitu.py`
与 `topo_templates/tests/test_grin_lens_antenna.py` 钉住；
**本脚本补的是「CST 到底接不接受这套 VBA」**——这正是离线测不到的那一半。

做法
----
* A：**裸工程**（干净模板 + 材料 + `a/h/Rbig`）直接调 `build_grin_lens_insitu()`；
* B：**端到端模板** `GRINLensAntenna(lens_method='insitu')`（小尺寸天线 + 小孔阵）；
* 落盘后解 `ModelHistory.json` 的 **caption** 逐条对账（这是我们下发的，还是 CST 自己加的，
  看 caption 就分得清）：

  `` Hexagon:`` × 象限孔数 / ``add`` × (孔数−1) / ``mirror`` ×1 /
  ``Cylinder:`` ×1 / ``Square:`` ×1 / ``subtract`` ×2 / ``translate`` ×2 / ``rotation`` ×1

* 参数表必须有 `HEX_SIZE / a2 / N / d0 / r1 / r2`（缺一个 CST 就弹
  「请输入变量值」的**模态对话框**把脚本挂住，而不是抛异常）+ 模板的 `Rbig / Ls`；
* 历史里**不应有** `Import`（这就是「不落 DXF」这条路的本质）；
* 参数闭合性复用 `scripts/verify_model_parameter_usage.py`。

⚠️ **只建模**：脚本不碰 `solve` / `study`，也不调用 `run_simulation`。
⚠️ 孔数提醒：默认只为分钟级完成取 `layers=10 / d0_layers=3`（≈176 孔）；
参考配置是 `layers=30 / d0_layers=8`（≈1426 孔，≈1455 条建模指令），
要跑那个请显式加 `--full`。

用法
----
    python scripts/verify_grin_lens_insitu_real.py
    python scripts/verify_grin_lens_insitu_real.py --full
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
A = 0.2425
SMALL = dict(straight_length=6, arm_length=8)
#: 参考配置（`1分4` 的 `N=(y[1]+2)*2` / `d0=8 层`）
FULL_RING = dict(layers=30, d0_layers=8)
#: 分钟级完成的小孔阵（下面 A/B 默认用它）
SMALL_RING = dict(layers=10, d0_layers=3)

_results = []
_baseline = set()


def record(item, status, detail, **extra):
    entry = {'item': item, 'status': status, 'detail': detail}
    entry.update(extra)
    extra_text = '  ' + json.dumps(extra, ensure_ascii=False, default=str) if extra else ''
    print(f'[{status:^7}] {item}: {detail}{extra_text}', flush=True)
    return entry


# ================================================================
# 取证助手
# ================================================================

def _messages(app):
    try:
        return [str(m) for m in (app.cst_file.get_messages() or [])]
    except Exception as exc:                            # noqa: BLE001
        return [f'<读消息失败 {type(exc).__name__}: {exc}>']


def _history(project_path):
    """保存后的历史条目（`caption` + `code` 行）—— caption 能分清是谁加的。"""
    path = os.path.join(os.path.splitext(project_path)[0], 'Model', '3D',
                        'ModelHistory.json')
    if not os.path.isfile(path):
        return []
    with open(path, encoding='utf-8-sig') as handle:
        data = json.load(handle)
    return data.get('history', [])


def _captions(project_path):
    return [str(entry.get('caption') or '') for entry in _history(project_path)]


def _code(project_path):
    return '\n'.join(line for entry in _history(project_path)
                     for line in entry.get('code', []))


def _params(project_path):
    path = os.path.join(os.path.splitext(project_path)[0], 'Model',
                        'Parameters.json')
    if not os.path.isfile(path):
        return {}
    with open(path, encoding='utf-8-sig') as handle:
        data = json.load(handle)
    return {p['name']: p.get('value') for p in data.get('parameters', [])}


def _count(captions, needle, prefix=False):
    if prefix:
        return sum(1 for c in captions if c.strip().startswith(needle))
    return sum(1 for c in captions if needle in c)


def _expected_counts(ring, name):
    """离线几何 ⇒ 期望的下发条数（与 `build_grin_lens_insitu()` 的序列一一对应）。

    ⚠️ 计数**必须带透镜自己的名字前缀**：端到端模板（B）里天线本身也会
    `add` / `Square` / `subtract` / `translate`，全库计数会把它们算进来
    （首版就是这么误报的：`add=103`、`Square=5`、`subtract=6`）。

    ⚠️ 另外 CST 落盘时**会去掉 caption 的前导空格**（下发时 ``" translate "``，
    落盘后 ``"translate grib-sub['0', 'r1', '0'] 1"``），所以按「以
    ``translate <名字>`` 开头」计数，而不是按 ``' translate '``。
    """
    n = len(ring['holes'])
    # ⚠️ 最终透镜实体就是 `name`（不是 `{name}-sub`）—— 2026-09-17 真机教训：
    #    名字对不上时，模板里的相位旋转会打到不存在的实体上
    #    （`Shape does not exist: gridlens:lens_epc`）。
    clip = name
    return {
        f'Hexagon:{name}-': (n, f'Hexagon: {name}-', True),
        f'{name}-0 add': (n - 1, f'{name}-0 add ', True),
        f'{name}-0 mirror': (1, f'{name}-0  mirror', True),
        f'Cylinder:{clip}': (1, f'Cylinder: {clip}', True),
        f'Square:{name}-cut': (1, f'Square: {name}-cut', True),
        f'{clip} subtract': (2, f'{clip} subtract', True),
        f'translate {clip}': (2, f'translate {clip}', True),
        f'rotation {clip}': (1, f'rotation {clip}', True),
    }


def _check_counts(label, project_path, ring, name):
    """A/B 共用的「下发条数 = 离线几何」对账（只数透镜自己那串 caption）。"""
    captions = _captions(project_path)
    spec = _expected_counts(ring, name)
    actual = {}
    want = {}
    for key, (count, needle, prefix) in spec.items():
        actual[key] = _count(captions, needle, prefix=prefix)
        want[key] = count
    bad = {k: (v, want[k]) for k, v in actual.items() if v != want[k]}
    record(f'{label} 下发条数与离线几何一致', 'OK' if not bad else 'FAIL',
           f'象限孔 {want[f"Hexagon:{name}-"]} 个 ⇒ ' + ' / '.join(
               f'{k.split(":")[-1].split(" ")[0]}={actual[k]}'
               for k in spec)
           + ('' if not bad else f'；不符：{bad}'),
           counts=actual, expected=want)
    return actual


def _check_params(label, project_path, ring, need_extra=(), forbid=()):
    params = _params(project_path)
    need = ['HEX_SIZE', 'a2', 'N', 'd0', 'r1', 'r2'] + list(need_extra)
    missing = [n for n in need if n not in params]
    record(f'{label} 参数表齐全（缺一个就会弹模态框挂住脚本）',
           'OK' if not missing else 'FAIL',
           f'缺 {missing}' if missing else
           ' / '.join(f'{n}={params[n]}' for n in need),
           ring_expected={'N': ring['n_layers'], 'd0': ring['d0'],
                          'HEX_SIZE': ring['hex_size']})
    if not missing:
        ok_n = abs(float(params['N']) - ring['n_layers']) < 1e-9
        ok_d0 = abs(float(params['d0']) - ring['d0']) < 1e-12
        record(f'{label} 参数值与离线几何逐值相同',
               'OK' if ok_n and ok_d0 else 'FAIL',
               f"N={params['N']}（离线 {ring['n_layers']}） / "
               f"d0={params['d0']}（离线 {ring['d0']}）")
    present = [n for n in forbid if n in params]
    if forbid:
        record(f'{label} 不登记用不到的参数（避免死写入）',
               'OK' if not present else 'FAIL',
               f'不该出现的参数：{present}（{forbid} 只被 DXF 路线的楔形裁剪用到）'
               if present else f"{' / '.join(forbid)} 都不在参数表里")
    return params


def _check_no_dxf(label, project_path):
    code = _code(project_path)
    has_import = 'Import' in code or 'dxf' in code.lower()
    record(f'{label} 不落 DXF（这条路线的本质）',
           'OK' if not has_import else 'FAIL',
           '历史里没有任何 DXF 导入' if not has_import
           else '历史里出现了 DXF 导入相关指令')
    return not has_import


def _check_component(label, project_path, component, lens_name):
    """**真机回归**：布尔运算/变换里的 ``"组件:名字"`` 必须是 `component`。

    2026-09-17 首跑就是在这里挂的：`translate` / `rotation` 的默认组件是
    `'component1'`，实体却在 `component` 里 ⇒ CST 报
    ``Shape does not exist: component1:<name>``，整段透镜建不出来。
    """
    code = _code(project_path)
    inline = f'{component}:{lens_name}'
    bad = f'"component1:{lens_name}'
    n_good = code.count(f'"{inline}')
    n_bad = code.count(bad)
    record(f'{label} 变换/布尔都指向正确组件（`{component}`）',
           'OK' if n_good and not n_bad else 'FAIL',
           f'指向 {inline!r} 的指令 {n_good} 条 / 误指 component1 的 {n_bad} 条')
    return n_good and not n_bad


# ================================================================
# A：裸工程直接调 builder
# ================================================================

def _new_app(workdir, tag, ring, extra_params=None):
    """干净模板 + 材料 + 这次要用的参数（`a` / `h` / `Rbig` [+ 额外的]）。"""
    from cst_solver import setup
    from topo_modeler.builders import build_materials

    template = os.path.join(workdir, f'tmp_{tag}.cst')
    shutil.copy2(CLEAN_TEMPLATE, template)
    app = setup(template)
    build_materials(app)
    params = {'a': A, 'h': 0.25, 'Rbig': 2.91}
    params.update(extra_params or {})
    app.paras(params, None)
    return app


def run_bare(workdir, ring):
    from cst_dialog_guard import guard
    from topo_modeler.builders import build_grin_lens_insitu

    tag = 'A(insitu)'
    output = os.path.join(workdir, 'insitu_lens.cst')
    app = None
    info = None
    error = None
    messages = []
    try:
        with guard(f'{tag} 构造+建模+保存', timeout=1800):
            app = _new_app(workdir, 'insitu', ring)
            info = build_grin_lens_insitu(
                app, ring, name='grib', height='h', component='grib',
                log=lambda s='': print(f'  · {s}', flush=True))
            app.save(output)
            app.close()
    except Exception as exc:                            # noqa: BLE001
        error = f'{type(exc).__name__}: {exc}'
        if app is not None:
            messages = _messages(app)
    record(f'{tag} 建模（{len(ring["holes"])} 个象限孔 / 共 '
           f'{2 * len(ring["holes"])} 孔）',
           'OK' if error is None and not messages else 'FAIL',
           error or f'未抛异常；CST 消息 {len(messages)} 条',
           messages=messages[:3])
    if error is not None or messages:
        return
    _check_counts(tag, output, ring, 'grib')
    _check_params(tag, output, ring)
    _check_no_dxf(tag, output)
    _check_component(tag, output, 'grib', 'grib')
    record(f'{tag} 透镜实体名',
           'OK' if info and info.get('name') else 'FAIL',
           f"name={info.get('name')} / holes={info.get('n_holes')} "
           f"/ placed={info.get('placed')} / n_lenses={info.get('n_lenses')}")
    return output


# ================================================================
# B：端到端模板
# ================================================================

def run_template(workdir, ring):
    from cst_dialog_guard import guard
    from topo_templates import GRINLensAntenna

    tag = 'B(template)'
    template = os.path.join(workdir, 'tmp_template.cst')
    shutil.copy2(CLEAN_TEMPLATE, template)
    output = os.path.join(workdir, 'grin_insitu_antenna.cst')
    antenna = None
    error = None
    messages = []
    try:
        with guard(f'{tag} 构造+建模+保存', timeout=2400):
            antenna = GRINLensAntenna(
                bend_angle=120, topology='AB', template_cst=template,
                output_path=output, lens_method='insitu',
                lens_layers=ring['n_layers'], lens_d0_layers=ring['d0_layers'],
                **SMALL)
            antenna.build_all()
            antenna.save(output)
            messages = _messages(antenna.app)
            antenna.close()
    except Exception as exc:                            # noqa: BLE001
        error = f'{type(exc).__name__}: {exc}'
        if antenna is not None and antenna.app is not None:
            messages = _messages(antenna.app)
    record(f'{tag} 端到端建模（天线 + 就地环透镜）',
           'OK' if error is None and not messages else 'FAIL',
           error or f'未抛异常；CST 消息 {len(messages)} 条',
           messages=messages[:3])
    if error is not None or messages:
        return
    _check_counts(tag, output, ring, 'lens_epc')
    _check_params(tag, output, ring, need_extra=('Rbig',), forbid=('Ls',))
    _check_component(tag, output, 'gridlens', 'lens_epc')
    # 天线部分确实还在（馈源/端口/波导）
    code = _code(output)
    for needle, label in (('Waveguide', '波导'), ('Port', '端口')):
        present = needle in code
        record(f'{tag} 天线部分未受影响（{label}）',
               'OK' if present else 'FAIL',
               f'{needle} 在历史里' if present else f'历史里没有 {needle}')
    # 离线摘要与真机一致
    summary = antenna.lens_summary()
    record(f'{tag} 透镜摘要（离线）',
           'OK' if summary.get('n_holes') == len(ring['holes']) else 'FAIL',
           f"method={summary.get('method')} / dxf={summary.get('dxf')} / "
           f"n_holes={summary.get('n_holes')} / layers={summary.get('layers')}")
    return output


def run_rotation_case(workdir, ring):
    """`lens_rotation`（参考的 `dphi`：透镜绕自身近焦点自转）真机验收。

    验证三件事：① `dphi` 被登记为 CST 参数（不是把角度烘进 VBA）；
    ② 历史里真的多了一条 `rotation`（自转）；③ 全程 0 条 CST 消息。
    """
    from cst_dialog_guard import guard
    from topo_modeler.builders import build_grin_lens_insitu

    tag = 'C(rotation)'
    output = os.path.join(workdir, 'insitu_lens_rot.cst')
    app = None
    info = None
    error = None
    messages = []
    try:
        with guard(f'{tag} 构造+建模+保存', timeout=1800):
            # ⚠️ `dphi` **必须先登记**：它是 `self_rotation` 引用的参数名，
            #    漏登记时 CST 不报错、而是弹「请输入变量值」模态框把脚本挂住
            #    （2026-09-18 实测挂了 30+ 分钟，`cst_dialog_guard` 都看不到那个框）。
            app = _new_app(workdir, 'rotation', ring, extra_params={'dphi': 10})
            info = build_grin_lens_insitu(
                app, ring, name='grib_rot', height='h', component='grib',
                self_rotation='dphi',
                log=lambda s='': print(f'  · {s}', flush=True))
            app.save(output)
            messages = _messages(app)
            app.close()
    except Exception as exc:                            # noqa: BLE001
        error = f'{type(exc).__name__}: {exc}'
        if app is not None:
            messages = _messages(app)
    record(f'{tag} 建模（透镜自转 dphi）',
           'OK' if error is None and not messages else 'FAIL',
           error or f'未抛异常；CST 消息 {len(messages)} 条', messages=messages[:3])
    if error is not None or messages:
        return
    params = _params(output)
    record(f'{tag} `dphi` 是 CST 参数（不是烘死的角度）',
           'OK' if 'dphi' in params else 'FAIL',
           f"dphi={params.get('dphi')}", params_dphi=params.get('dphi'))
    captions = _captions(output)
    # 自转 + 放置各一次 ⇒ 一共 2 条 rotation
    n_rot = _count(captions, 'rotation', prefix=True)
    record(f'{tag} 自转步骤真的下发（rotation ×2）',
           'OK' if n_rot == 2 else 'FAIL',
           f'历史 caption 里 rotation {n_rot} 条（自转 1 + 旋转复制 1）')
    record(f'{tag} 实体名与组件', 'OK' if info and info.get('name') else 'FAIL',
           f"name={info.get('name')} / self_rotation={info.get('self_rotation')}")
    return output


def run(workdir, ring):
    from cst_dialog_guard import check_dialogs, describe_dialogs

    check_dialogs('开工前')
    print(f'开工前 CST 对话框：\n{describe_dialogs()}', flush=True)

    output_a = run_bare(workdir, ring)
    output_b = run_template(workdir, ring)
    run_rotation_case(workdir, ring)

    # ---- 参数闭合性（复用 P4 §8.7 的工具） ----
    for label, output in (('A', output_a), ('B', output_b)):
        if not output:
            continue
        try:
            import verify_model_parameter_usage as usage

            template_table, _ = usage.load_parameters(r'D:\TPC_out\tmp')
            before = len(usage.RESULTS)
            result = usage.audit_project(usage.resolve_project(output),
                                         template_table,
                                         label=f'insitu {label}')
            for entry in usage.RESULTS[before:]:
                _results.append(entry)
                print(f'[{entry["status"]:^7}] {entry["item"]}: '
                      f'{entry["detail"]}', flush=True)
            if result:
                record(f'{label} 参数闭合性（库下发参数无死写入）',
                       'FAIL' if result['dead_writes'] else 'OK',
                       f'死写入：{result["dead_writes"] or "无"}'
                       f'（已引用 {result["used"]} / 共 {result["defined"]}）')
        except Exception as exc:                        # noqa: BLE001
            record(f'{label} 参数闭合性', 'UNKNOWN', f'{type(exc).__name__}: {exc}')


def main(argv=None):
    global _baseline
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument('--workdir', default=None, help='产物目录（默认临时目录）')
    parser.add_argument('--full', action='store_true',
                        help='跑参考配置（layers=30 / d0_layers=8，≈1455 条指令，慢）')
    parser.add_argument('--layers', type=int, default=None, help='覆盖网格层数 N')
    parser.add_argument('--d0-layers', type=int, default=None, dest='d0_layers',
                        help='覆盖 d0 的层数系数（参考 8）')
    args = parser.parse_args(argv)

    ring_kwargs = dict(FULL_RING if args.full else SMALL_RING)
    if args.layers is not None:
        ring_kwargs['layers'] = args.layers
    if args.d0_layers is not None:
        ring_kwargs['d0_layers'] = args.d0_layers

    from topo_modeler.builders import grin_ring_holes

    ring = grin_ring_holes(A, n_layers=ring_kwargs['layers'],
                           d0_layers=ring_kwargs['d0_layers'])
    print(f"孔阵：N={ring['n_layers']} / d0={ring['d0']:.4f} / "
          f"HEX_SIZE={ring['hex_size']:.6f} / 象限孔 {len(ring['holes'])} ⇒ "
          f"共 {2 * len(ring['holes'])} 孔", flush=True)

    try:
        import cst_solver

        lib = cst_solver.CST_PYTHON_LIB
        if lib and lib not in sys.path:
            sys.path.append(lib)
    except Exception as exc:                            # noqa: BLE001
        record('cst.interface 准备', 'WARN', f'{type(exc).__name__}: {exc}')

    _baseline = design_environment_baseline()
    print(f'基线 DE：{sorted(_baseline)}', flush=True)
    workdir = args.workdir or tempfile.mkdtemp(prefix='tpc_grin_insitu_')
    os.makedirs(workdir, exist_ok=True)
    print(f'产物目录：{workdir}', flush=True)

    try:
        run(workdir, ring)
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
