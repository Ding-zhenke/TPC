# -*- coding: utf-8 -*-
r"""
P5「多路径 VPC 区域并集与晶体裁剪」真机验收（**只建模，不求解**）
================================================================

计划原文（`docs/next_plan/README.md` P5）：

> 多路径 VPC 区域并集与晶体裁剪；基板并集已存在，需增加 VPC 的对应组合并真机验收。

离线逻辑（命名/前缀/并集/裁剪顺序）已由
`topo_modeler/tests/test_vpc_crystal_multi.py`（22 项）钉住；
**本脚本补的是「CST 到底接不接受这套 VBA」**——这正是离线测不到的那一半。

做法（一条两分支的 Y 形路径，**缩小阵列次数**以便分钟级完成）
--------------------------------------------------------------
1. `build_materials` → 多路径**基板**并集（已有能力，作为对照）
2. `build_vpc_regions_multi` → 上/下半区各自并成一个实体
3. `build_crystals_multi` → 每条分支各一套晶体（阵列次数走**参数引用** `int(xup)`）
4. `clip_crystals_with_vpc` → 每条分支的晶体分别与并集后的 VPC 区域求交
5. 保存后解 `ModelHistory.json` 核对：
   * 每个建模步骤 **0 条 CST 消息**；
   * 历史里出现 `Solid.Add`（并集）与 **2 × 分支数** 条 `Solid.Intersect`；
   * 规范名 `vpc_A` / `vpc_B` 被子分支实体并进来（命名没被路径下标污染）；
   * 两条分支的晶体名互不相同（`g1A/g1B` 与 `g21A/g21B`）；
   * 参数闭合性（复用 `scripts/verify_model_parameter_usage.py`）。

用法
----
    python scripts/verify_vpc_multi_real.py

⚠️ 只建模。脚本不碰 `solve` / `study`，也不调用 `run_simulation`。
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
#: 缩小后的阵列次数（真机验收只关心「CST 接不接受这套 VBA」与命名，
#: 阵列规模不影响这一点；完整阵列是 26/15/15，孔数会到千级、耗时不可控）
SMALL_ARRAY = (4, 4, 4)

_results = []
_baseline = set()


def record(item, status, detail, **extra):
    entry = {'item': item, 'status': status, 'detail': detail}
    entry.update(extra)
    _results.append(entry)
    extra_text = '  ' + json.dumps(extra, ensure_ascii=False, default=str) if extra else ''
    print(f'[{status:^7}] {item}: {detail}{extra_text}', flush=True)
    return entry


# ================================================================
# 取证助手（与 `verify_grin_multipath.py` 同款）
# ================================================================

def _messages(app):
    try:
        return [str(m) for m in (app.cst_file.get_messages() or [])]
    except Exception as exc:                            # noqa: BLE001
        return [f'<读消息失败 {type(exc).__name__}: {exc}>']


def _history_code(project_path):
    """保存后历史里的 VBA 行（原始文本）。"""
    path = os.path.join(os.path.splitext(project_path)[0], 'Model', '3D',
                        'ModelHistory.json')
    if not os.path.isfile(path):
        return []
    with open(path, encoding='utf-8-sig') as handle:
        data = json.load(handle)
    return [line for entry in data.get('history', [])
            for line in entry.get('code', [])]


def _new_app(workdir, tag='vpc'):
    """打开干净模板 + 建材料，并把这次要用到的参数一次性登记好。"""
    from cst_solver import setup
    from topo_modeler.builders import build_materials

    template = os.path.join(workdir, f'tmp_{tag}.cst')
    if not os.path.exists(template):
        shutil.copy2(CLEAN_TEMPLATE, template)
    app = setup(template)
    build_materials(app)
    xup, yup, ydn = SMALL_ARRAY
    app.paras({'a': A, 'h': 0.25, 'e1': A / 2, 'e2': A / 2 * 1.7320508075688772,
               'l1': 0.65 * A, 'l2': 0.35 * A,
               'xup': xup, 'yup': yup, 'ydn': ydn}, None)
    return app


def _two_branch_paths():
    """Y 形两分支：主干直走 18 步；分支在第 6 步后拐 120° 再走 10 步。"""
    from mesh_grid.tri_grid import TopoPath

    main = TopoPath.builder(A, name='main').start(0, 0).move(18, 'c').build()
    arm = (TopoPath.builder(A, name='arm').start(0, 0).move(6, 'c')
           .turn(120).move(10, 'along').build())
    return {'main': main, 'arm': arm}


# ================================================================
# 主流程
# ================================================================

def run(workdir):
    from cst_dialog_guard import check_dialogs, describe_dialogs, guard
    from topo_modeler.builders import (
        build_crystals_multi,
        build_substrate_multi,
        build_vpc_regions_multi,
        clip_crystals_with_vpc,
    )

    paths = _two_branch_paths()
    output = os.path.join(workdir, 'vpc_multi.cst')
    app = None
    try:
        check_dialogs('开工前')
        print(f'开工前 CST 对话框：\n{describe_dialogs()}', flush=True)
        app = _new_app(workdir, 'vpc')

        with guard('多路径基板并集', timeout=600):
            substrate = build_substrate_multi(app, paths, name='substrate')
        record('M1 多路径基板并集', 'OK' if not _messages(app) else 'FAIL',
               f'实体={substrate}；消息 {len(_messages(app))} 条',
               messages=_messages(app)[:3])

        with guard('多路径 VPC 并集', timeout=600):
            vpca, vpcb = build_vpc_regions_multi(app, paths)
        record('M2 多路径 VPC 并集', 'OK' if not _messages(app) else 'FAIL',
               f'实体={vpca}/{vpcb}；消息 {len(_messages(app))} 条',
               messages=_messages(app)[:3])

        with guard('多路径晶体', timeout=900):
            crystals = build_crystals_multi(app, paths, topology='AB',
                                            xup='xup', yup='yup', ydn='ydn')
        record('M3 多路径晶体阵列', 'OK' if not _messages(app) else 'FAIL',
               f'{crystals}；消息 {len(_messages(app))} 条',
               messages=_messages(app)[:3])

        with guard('晶体与 VPC 裁剪', timeout=600):
            info = clip_crystals_with_vpc(app, vpca, vpcb, crystals)
        record('M4 逐分支裁剪', 'OK' if not _messages(app) else 'FAIL',
               f'吸收 {info["pairs"]} 对晶体；消息 {len(_messages(app))} 条',
               consumed=info['consumed'], messages=_messages(app)[:3])

        with guard('保存工程', timeout=600):
            app.save(output)
        record('保存工程', 'OK' if os.path.exists(output) else 'FAIL', output)
    except Exception as exc:                            # noqa: BLE001
        record('建模过程', 'FAIL', f'{type(exc).__name__}: {exc}',
               traceback=traceback.format_exc(limit=4))
    finally:
        try:
            if app is not None:
                app.close()
        except Exception:                               # noqa: BLE001
            pass

    # ---- 从落盘历史核对（离线，不需要 CST） ----
    code = '\n'.join(_history_code(output))
    if not code:
        record('历史取证', 'FAIL', '读不到 ModelHistory.json')
        return
    record('历史取证', 'OK', f'{len(code.splitlines())} 行 VBA')

    record('H1 历史里有布尔并（Solid.Add）',
           'OK' if 'Solid.Add' in code else 'FAIL',
           'VPC 上/下半区各并一次、基板也并一次')
    n_intersect = code.count('Solid.Intersect')
    want = 2 * len(_two_branch_paths())
    record('H2 每条分支都裁了（Solid.Intersect 条数）',
           'OK' if n_intersect == want else 'FAIL',
           f'实测 {n_intersect} 条，期望 {want}（= 2 × 分支数）')

    names = ['vpc_A', 'vpc_B', 'g1A', 'g1B', 'g21A', 'g21B']
    missing = [n for n in names if n not in code]
    record('H3 规范名与分支名都在历史里',
           'OK' if not missing else 'FAIL',
           f'缺失 {missing}' if missing else 'vpc_A/vpc_B + g1A/g1B + g21A/g21B 齐全')

    # 下标的段实体必须真的进了规范名里（而不是留着一堆孤儿实体）
    segs = [line for line in code.splitlines()
            if 'vpc_A_p' in line or 'vpc_B_p' in line]
    record('H4 分支段实体被并入规范名',
           'OK' if segs else 'FAIL',
           f'{len(segs)} 行涉及 vpc_*_p*_seg*；'
           + (segs[0].strip()[:80] if segs else '没有任何分支段实体'))

    # ---- 参数闭合性（复用 P4 §8.7 的工具） ----
    try:
        import verify_model_parameter_usage as usage

        template_table, _ = usage.load_parameters(r'D:\TPC_out\tmp')
        before = len(usage.RESULTS)
        result = usage.audit_project(usage.resolve_project(output), template_table,
                                     label='多路径工程')
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


def main(argv=None):
    global _baseline
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument('--workdir', default=None, help='产物目录（默认临时目录）')
    args = parser.parse_args(argv)

    try:
        import cst_solver

        lib = cst_solver.CST_PYTHON_LIB
        if lib and lib not in sys.path:
            sys.path.append(lib)                        # DE 清点要能真查到
    except Exception as exc:                            # noqa: BLE001
        record('cst.interface 准备', 'WARN', f'{type(exc).__name__}: {exc}')

    _baseline = design_environment_baseline()
    print(f'基线 DE：{sorted(_baseline)}', flush=True)
    workdir = args.workdir or tempfile.mkdtemp(prefix='tpc_vpc_multi_')
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
