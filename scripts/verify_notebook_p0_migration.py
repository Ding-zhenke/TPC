# -*- coding: utf-8 -*-
r"""
P5「87 个 notebook 迁移」—— **P0 批次的离线几何验收**（只读、不执行 notebook）
=============================================================================

计划原文（`docs/next_plan/README.md` P5）：

> 按 87 个 notebook 清点表的 P0/P1/P2 顺序迁移，每个登记迁移结果及
> 几何/仿真验收；P3 保留并注明不迁移原因。

P0 批次 = 5 个 notebook（`直波导` 3 个 + `普通单元天线` 2 个），它们的功能
**已经由 `StraightWaveguide` / `UnitAntenna` 覆盖**，所以这一批的迁移动作不是"重写
notebook"，而是**证明新库与旧 notebook 的几何逐值一致**，并把差异登记下来。

判据（全部离线，`--no-cst`，不启动 CST、不执行 notebook）
--------------------------------------------------------
对每个 notebook 从 code cell 里抽：
1. `x` / `y` 数组与路径点构造（`p1=(0,-1)`、`p2=(0,x[0])`、`p3=(y[0],x[0])`）——
   换算出**路径格点**，与新库 `TopoPath.path_lattice` 比；
2. 阵列范围公式（`xup = x[0]+int(y[0]/2)[+1 for BA]`、`yup = ydn = y[0]`）——
   与新库模板的 `xup/yup/ydn` 比；
3. 基础几何参数（`a/h/l1/l2` 的取值与表达式）——与新库比；
4. 馈源/波导参数（`x0/wf1/lf1..lf3/wg_a/wg_b/wg_t`）——与新库**实际定义**的参数比；
5. 有参考工程（文件夹形式 `Parameters.json`）时再交叉核对一次。

结论状态
--------
``EQUIVALENT``   几何逐值一致（可迁移）
``DIFF``         有差异，附具体项（必须说清差异是什么）
``NEEDS_FEATURE``需要新库补能力才能等价（例如模板没暴露的馈源参数）

用法::

    python scripts/verify_notebook_p0_migration.py            # 打印结论
    python scripts/verify_notebook_p0_migration.py --write    # 顺手把登记表写进文档
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

#: 旧 notebook 源目录（清点表的同源）
LEGACY_ROOT = r'D:\成电博士生涯\拓扑光子晶体模型\硅基'
DOC = PROJECT_ROOT / 'docs' / 'guides' / 'notebook_migration_p0.md'

#: P0 批次：notebook → 新库模板与构造映射
#:
#: `feed_type` 是**从 notebook 源码取证**出来的（2026-09-17）：旧 notebook 建的是
#: `feed1`（AB 型椭圆探针，用 lf1/lf2/wf1/x0）还是 `feed2`（BA 型渐变探针，
#: 用 wf2/lf4/lf5 + 波导范围 `[-lf5-lf6-lf4, -lf4]`），决定映射到模板的哪条路。
P0 = (
    {'notebook': r'普通单元天线\Ant1_D_AB_120D_cylinder_DF.ipynb',
     'template': 'unit_antenna', 'topology': 'AB', 'radiator': 'cylinder',
     'feed_type': 'ab_elliptical',
     'reference': r'普通单元天线\Ant1_D_AB_120_cylinder-DF'},
    {'notebook': r'普通单元天线\Ant1_D_BA_120D_circle_DF.ipynb',
     'template': 'unit_antenna', 'topology': 'BA', 'radiator': 'cylinder',
     'feed_type': 'ba_tapered',
     'reference': r'普通单元天线\Ant1_D_BA_120_cylinder-DF'},
    {'notebook': r'直波导\AB\AB_feed.ipynb',
     'template': 'straight_waveguide', 'topology': 'AB',
     'feed_type': 'ab_elliptical',
     'reference': r'直波导\AB\AB_feed'},
    {'notebook': r'直波导\BA\优化后的\BA_feed_epc.ipynb',
     'template': 'straight_waveguide', 'topology': 'BA',
     'feed_type': 'ba_tapered',          # 该 notebook 建的是 feed2 + BA 波导范围
     'reference': None},
    {'notebook': r'直波导\短探针\short.ipynb',
     'template': 'straight_waveguide', 'topology': 'AB',
     'feed_type': 'short_probe_variant',   # ⚠️ 不是两族之一（见登记表）
     'reference': None},
)

_results = []


def record(item, status, detail, **extra):
    entry = {'item': item, 'status': status, 'detail': detail}
    entry.update(extra)
    _results.append(entry)
    extra_text = '  ' + json.dumps(extra, ensure_ascii=False, default=str) if extra else ''
    print(f'[{status:^7}] {item}: {detail}{extra_text}', flush=True)
    return entry


# ================================================================
# 读 notebook（只解析 JSON，不执行）
# ================================================================

def notebook_source(path):
    """把 code cell 的源码拼成一段文本（**不执行**任何单元格）。"""
    if not os.path.isfile(path):
        return None
    with open(path, encoding='utf-8') as handle:
        nb = json.load(handle)
    return '\n'.join(''.join(cell.get('source', []))
                     for cell in nb.get('cells', [])
                     if cell.get('cell_type') == 'code')


_ARRAY = re.compile(r"^\s*([xy])\s*=\s*np\.array\(\[(.*?)\]\)", re.S | re.M)
_SCALAR = re.compile(r"^\s*([A-Za-z_][A-Za-z_0-9]*)\s*=\s*([-\d.]+)\s*(?:#.*)?$", re.M)
_POINT = re.compile(r"^\s*p(\d)\s*=\s*\(\s*([^)]+?)\s*\)", re.M)
_PARA = re.compile(r"\.para\(\s*'([^']+)'\s*,\s*([^)]+?)\s*\)")


def parse_notebook(text):
    """抽出几何/参数证据（容错：抽不到就是 None，不猜）。"""
    arrays = {}
    for match in _ARRAY.finditer(text):
        values = [v.strip() for v in match.group(2).replace('\n', ' ').split(',')
                  if v.strip()]
        arrays[match.group(1)] = values
    scalars = {}
    for name, value in _SCALAR.findall(text):
        scalars.setdefault(name, value)          # 取第一次赋值（参数表那一次）
    points = {f'p{m.group(1)}': m.group(2) for m in _POINT.finditer(text)}
    paras = {m.group(1): m.group(2).strip() for m in _PARA.finditer(text)}
    return {'x': arrays.get('x'), 'y': arrays.get('y'),
            'scalars': scalars, 'points': points, 'paras': paras}


def _notebook_usage(text, name):
    """参数 `name` 在 notebook 源码里**被几何引用**的行数（排除定义行）。

    ⚠️ 不用"参考工程历史里出现过"判定：参考工程是从 `tmp.cst` 起步的，历史里
    混着**模板遗留**的参数定义/引用（P4 §8.7 记录的同一类坑），会把
    "定义了没用"误判成"被引用"。直接看 notebook 自己怎么写最准。
    """
    pattern = re.compile(rf'(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])')
    count = 0
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        if re.match(rf'^{re.escape(name)}\s*=', stripped):        # Python 赋值
            continue
        if re.search(rf"\.para\(\s*'{re.escape(name)}'", stripped):  # CST 参数定义
            continue
        if pattern.search(stripped):
            count += 1
    return count


def _referenced_params(rel):
    """参考工程的**建模历史真的引用了**哪些参数（复用 P4 §8.7 的工具）。

    为什么需要：旧 notebook 常常"定义了一堆参数但几何根本不引用"
    （实测 12 个多端口 notebook 里 `lf4-lf6/wf2/wg_*` 全部只定义不使用）。
    拿这些当"模板缺能力"去补，就是**凭想象扩张缺口**。
    """
    if not rel:
        return None
    project = os.path.join(LEGACY_ROOT, rel)
    if not os.path.isdir(os.path.join(project, 'Model')):
        return None
    try:
        import verify_model_parameter_usage as usage

        table, _ = usage.load_parameters(project)
        texts, _ = usage._history_strings(project)
        if not table or texts is None:
            return None
        corpus = list(texts) + [item['expr'] for item in table.values()]
        return {name for name in table if usage._references(name, corpus)}
    except Exception:                                   # noqa: BLE001
        return None


def reference_params(rel):
    """参考工程（文件夹形式）的 `Parameters.json` → ``{名字: 表达式}``。"""
    if not rel:
        return None
    path = os.path.join(LEGACY_ROOT, rel, 'Model', 'Parameters.json')
    if not os.path.isfile(path):
        return None
    with open(path, encoding='utf-8-sig') as handle:
        data = json.load(handle)
    return {p['name']: p.get('expr') for p in data.get('parameters', [])}


# ================================================================
# 新旧对比
# ================================================================

def _num(value):
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


#: 模板**登记到 CST 参数表**的馈源参数**取决于 feed_type** ——
#: 两个族引用的参数不同（AB：x0/wf1/lf1/lf2/lf3；BA：x01/wf2/lf4/lf5 + 波导要 lf6）
EXPOSED_FEED_PARAMS = {
    ('straight_waveguide', 'ba_tapered'): ('x01', 'wf2', 'lf4', 'lf5', 'lf6'),
    ('straight_waveguide', 'ab_elliptical'): ('x0', 'wf1', 'lf1', 'lf2', 'lf3'),
    ('unit_antenna', 'ba_tapered'): ('x01', 'wf2', 'lf4', 'lf5'),
    ('unit_antenna', 'ab_elliptical'): ('x0', 'wf1', 'lf1', 'lf2', 'lf3'),
}


def build_template(spec, parsed):
    """按 notebook 的取值建新库模板（离线，不需要 CST）。

    ⚠️ **必须把 notebook 里的馈源取值传进去**再比：模板的 ctor 默认值是
    `AB_feed.ipynb` 那一组，而其它 notebook（如 `short.ipynb`）用的是别的值 ——
    拿默认值去比会把"传参即可等价"误判成"有差异"。
    """
    import warnings
    warnings.simplefilter('ignore')
    x = parsed['x'] or []
    y = parsed['y'] or []
    scalars = parsed['scalars']
    common = dict(lattice_constant=_num(scalars.get('a', 0.2425)),
                  height=_num(scalars.get('h', 0.25)))
    feed = {}
    exposed = EXPOSED_FEED_PARAMS.get(
        (spec['template'], spec.get('feed_type')), ())
    for name in exposed:
        value = _num(scalars.get(name))
        if value is not None:
            feed[name] = value
    # 模板构造签名里没有的馈源参数走**覆盖入口** `feed_params={...}`
    # （AB 族的 x0/wf1/lf1/lf2/lf3 本身是 StraightWaveguide 的构造参数，
    #   不属于这里；UnitAntenna 与 BA 族的那些是模板内部写死的）
    overrides = {n: feed.pop(n) for n in list(feed)
                 if n not in _ctor_params(spec['template'])}
    if overrides:
        feed['feed_params'] = overrides
    feed_type = spec.get('feed_type')
    if feed_type in ('ab_elliptical', 'ba_tapered'):
        feed['feed_type'] = feed_type
    import inspect
    if spec['template'] == 'unit_antenna':
        from topo_templates import UnitAntenna as cls
        geometry = {'straight_length': int(float(x[0])),
                    'arm_length': int(float(y[0])), 'bend_angle': 120,
                    'topology': spec['topology'],
                    'radiator': spec.get('radiator')}
    else:
        from topo_templates import StraightWaveguide as cls
        geometry = {'length': int(float(x[0])), 'width': int(float(y[0])),
                    'topology': spec['topology']}
    accepted = set(inspect.signature(cls.__init__).parameters)
    kwargs = {k: val for k, val in dict(common, **geometry, **feed).items()
              if k in accepted}
    # 模板构造签名里没有的参数（例如 `UnitAntenna` 的 x0/wf1 是内部固定值）：
    # 不传给 ctor，但下面会比对"登记到 CST 参数表里的值"。
    return cls(**kwargs)


def _ctor_params(template_name):
    """模板构造签名里的参数名（用来判断"模板能不能改这个值"）。"""
    import inspect
    if template_name == 'unit_antenna':
        from topo_templates import UnitAntenna as cls
    else:
        from topo_templates import StraightWaveguide as cls
    return set(inspect.signature(cls.__init__).parameters) - {'self'}


class _ParaRecorder:
    """只记 `para` 的假 app（用来读模板**登记到 CST 的值**）。"""

    def __init__(self):
        self.values = {}

    def __getattr__(self, item):
        def _f(*a, **k):
            if item == 'para' and a:
                self.values[a[0]] = a[1] if len(a) > 1 else k.get('value')
            return None
        return _f


def registered_values(template):
    """模板 `_define_all_params()` 实际登记到 CST 参数表里的值（离线）。"""
    app = _ParaRecorder()
    template.app = app
    try:
        template._define_all_params()
    except Exception:                                   # noqa: BLE001
        return {}
    return dict(app.values)


#: **已定论的差异**：旧 notebook 的路径起点是 `(0,-1)`（19 格），新库是 `(0,0)`（18 格）。
#: 依据：`topo_templates/straight_waveguide.py` §3.2 的注释 —— 旧写法终点虽也对，
#: 但整条路径是 19 格，基板/VPC/晶体在 x 方向比参考工程多一个晶格周期；
#: 新库以**参考工程 `AB_feed.cst` 的 `xup = x1+int(y1/2) = 25`** 为准做了修正。
#: 这条差异是**有意的、有据可查的**，不算迁移缺口。
KNOWN_DELTAS = {
    'path_start': '旧 `start(0,-1)`（19 格）vs 新 `start(0,0)`（18 格）——'
                  '新库按参考工程 `AB_feed.cst` 的 `xup=25` 修正过，'
                  '见 docs/packages/topo_templates.md §3.2',
    'arm_from_mirror': '旧 notebook 的预览只画了直段（`path1 = vstack((p1,p2))`），'
                       '臂段是由 `mirror`/`area2` 生成的；新库按**参考工程**建完整三点路径'
                       '（臂端 `(6.0625,∓2.9402)` 已与参考工程逐位核对，见 P4 §4.5）',
}


def _normalize_start(lattice):
    """把 `(0,-1)` 起点归一成 `(0,0)`，用于判定"除了那处已定论差异之外是否一致"。"""
    if lattice and lattice[0] == (0, -1):
        return [(0, 0)] + list(lattice[1:])
    return list(lattice)


def compare_one(spec):
    """对比一个 notebook。返回结果 dict。"""
    nb_rel = spec['notebook']
    path = os.path.join(LEGACY_ROOT, nb_rel)
    text = notebook_source(path)
    label = nb_rel.replace('\\', '/')
    if text is None:
        record(label, 'FAIL', f'notebook 不存在：{path}')
        return {'notebook': nb_rel, 'status': 'FAIL', 'notes': '文件不存在'}

    parsed = parse_notebook(text)
    parsed['template'] = spec['template']
    if not parsed['x'] or not parsed['y']:
        record(label, 'FAIL', '抽不到 x/y 数组（解析规则可能失效）')
        return {'notebook': nb_rel, 'status': 'FAIL', 'notes': 'x/y 缺失'}

    antenna = spec['template'] == 'unit_antenna'
    x0, y0 = int(float(parsed['x'][0])), int(float(parsed['y'][0]))
    # 旧 notebook 的路径：天线用它的三点（`p1/p2/p3`），直波导是两点
    if antenna and 'p3' in parsed['points']:
        legacy_lattice = [(0, -1), (0, x0), (y0, x0)]
    else:
        legacy_lattice = [(0, -1), (0, x0)]
    template = build_template(spec, parsed)
    new_lattice = list(template.path.path_lattice)

    diffs, notes, deltas = [], [], []
    if _normalize_start(legacy_lattice) != _normalize_start(new_lattice):
        if antenna and 'p3' not in parsed['points'] and len(new_lattice) == 3:
            deltas.append(KNOWN_DELTAS['arm_from_mirror'])
        else:
            diffs.append(f'路径格点：旧 {legacy_lattice} vs 新 {new_lattice}')
    elif legacy_lattice != new_lattice:
        deltas.append(KNOWN_DELTAS['path_start'])

    # 阵列范围（旧 notebook 的公式：xup = x0 + int(y0/2)[+1 for BA]，yup = ydn = y0）
    want_xup = x0 + int(y0 / 2) + (1 if (antenna and spec['topology'] == 'BA') else 0)
    got = (template.xup, template.yup, template.ydn)
    if got != (want_xup, y0, y0):
        diffs.append(f'阵列范围：旧公式 ({want_xup}, {y0}, {y0}) vs 新 {got}')

    # 基础几何：l1/l2 口径（旧 notebook：AB 用 l1=0.65a 大孔、BA 侧互换）
    legacy_l1 = parsed['paras'].get('l1')
    if legacy_l1:
        want_l1 = _num(legacy_l1.replace('a', '').replace('*', '')) or None
        if want_l1 and abs(template.l1 / template.a - want_l1) > 1e-9:
            diffs.append(f'l1 比值：旧 {want_l1} vs 新 {template.l1 / template.a:.4f}')

    # 馈源参数：比对**模板登记到 CST 的值**（覆盖那些不能从 ctor 传的参数）
    exposed = EXPOSED_FEED_PARAMS.get(
        (spec['template'], spec.get('feed_type')), ())
    registered = registered_values(template)
    ctor_params = set(_ctor_params(spec['template']))
    missing = []
    value_gaps = []
    for name in exposed:
        legacy = _num(parsed['scalars'].get(name))
        if legacy is None:
            continue
        new_value = _num(registered.get(name, getattr(template, name, None)))
        if new_value is None:
            missing.append(name)                        # 模板压根没登记
        elif abs(legacy - new_value) > 1e-12:
            if name in ctor_params:
                diffs.append(f'{name}：旧 {legacy} vs 新库登记值 {new_value}')
            else:
                # 值不同、而且**模板没把它做成构造参数** ⇒ 这个模型复现不了：
                # 归"需补能力"（补一个 ctor 覆盖入口），不是"几何算错了"
                value_gaps.append(f'{name}：旧 {legacy} vs 模板写死 {new_value}'
                                  f'（模板未暴露为构造参数）')
    # notebook 用到、但模板没暴露的馈源参数
    for name in ('lf1', 'lf2', 'lf3', 'lf4', 'lf5', 'lf6', 'wf1', 'wf2', 'x0', 'x01'):
        if name in parsed['scalars'] and name not in exposed:
            missing.append(name)

    # 参考工程交叉核对（有的话）：参数值 + **哪些参数真的被几何引用**
    ref = reference_params(spec.get('reference'))
    ref_note = ''
    referenced = None
    if ref:
        for name in exposed:
            if name in ref and name in parsed['scalars']:
                if _num(ref[name]) != _num(parsed['scalars'][name]):
                    diffs.append(f'参考工程 {name}={ref[name]} vs notebook '
                                 f'{parsed["scalars"][name]}')
        ref_note = f'参考工程已交叉核对（{len(ref)} 项参数）'
        referenced = _referenced_params(spec.get('reference'))
    elif spec.get('reference'):
        ref_note = '参考工程无文件夹形式参数表，未交叉核对'

    # 未暴露的参数：**只有 notebook 自己的几何真的引用它**才算缺口；
    # "定义了没用"的（多端口族里大量存在）不算缺口。
    gaps = list(value_gaps)
    if missing:
        really_used = sorted(n for n in missing if _notebook_usage(text, n) > 0)
        unused_here = sorted(n for n in missing if _notebook_usage(text, n) == 0)
        if really_used:
            gaps.append('模板未暴露、但旧 notebook 的几何**确实引用**（需补能力）：'
                        + ', '.join(really_used))
        if unused_here:
            notes.append('模板未暴露、旧 notebook 里也**只定义不使用**（不算缺口）：'
                         + ', '.join(unused_here))

    status = 'DIFF' if diffs else ('NEEDS_FEATURE' if gaps else 'EQUIVALENT')
    detail = ('几何逐值一致' if status == 'EQUIVALENT' else
              '；'.join(diffs + gaps + notes))
    if deltas and status == 'EQUIVALENT':
        detail = '几何一致（含已定论差异：' + '；'.join(deltas) + '）'
    if notes and status == 'EQUIVALENT' and not deltas:
        detail = '几何一致（' + '；'.join(notes) + '）'
    record(label, 'OK' if status == 'EQUIVALENT' else
           ('INFO' if status == 'NEEDS_FEATURE' else 'FAIL'), detail,
           verdict=status, ref_note=ref_note, lattice=new_lattice,
           array_range=list(got), expose_missing=missing, known_deltas=deltas)
    return {'notebook': nb_rel, 'status': status, 'diffs': diffs, 'notes': notes,
            'gaps': gaps, 'deltas': deltas, 'ref_note': ref_note,
            'lattice': new_lattice, 'array_range': list(got), 'x': parsed['x'],
            'y': parsed['y'], 'topology': spec['topology'],
            'template': spec['template']}


# ================================================================
# 登记表
# ================================================================

def write_doc(results):
    lines = ['# 旧 notebook 迁移登记：P0 批次（5 个）', '',
             '> 本表由 `python scripts/verify_notebook_p0_migration.py --write` 生成'
             '（只解析 `.ipynb` 的 JSON，**不执行** notebook、不改任何源文件）。',
             '> 判据与口径见脚本 docstring；清点表见 '
             '[notebook_migration_inventory.md](./notebook_migration_inventory.md)。', '',
             '## 1. 结论表', '',
             '| # | notebook | 拓扑 | 新库模板 | 路径格点（新库实测） | 阵列范围 | 状态 | 差异/说明 |',
             '|---|---|---|---|---|---|---|---|']
    for index, item in enumerate(results, 1):
        rel = item['notebook'].replace('\\', '/')
        status = item['status']
        mark = {'EQUIVALENT': '✅ 几何一致（可迁移）',
                'NEEDS_FEATURE': '⚠️ 需补能力',
                'DIFF': '❌ 有差异',
                'FAIL': '❌ 取证失败'}.get(status, status)
        parts = item.get('diffs', []) + item.get('gaps', []) + item.get('notes', [])
        if not parts:
            parts = item.get('deltas', [])
        elif item.get('deltas'):
            parts = item['deltas'] + parts
        note = '；'.join(parts) or '—'
        lines.append(f"| {index} | `{rel}` | {item.get('topology', '—')} | "
                     f"`{item.get('template', '—')}` | {item.get('lattice', '—')} | "
                     f"{item.get('array_range', '—')} | {mark} | {note} |")
    lines += ['', '## 2. 验收口径', '',
              '* **几何验收（本表）**：路径格点、阵列范围、基础参数、馈源参数逐值比对'
              ' —— 全部离线，不需要 CST；',
              '* **仿真验收**：本批次**未做**（需要真实求解；单次时域求解约 5300 s CPU），'
              '属计划 P4/V2、V7、V9，等用户确认算例与开销；',
              '* 迁移方式：P0 批次的功能已被 `StraightWaveguide` / `UnitAntenna` 覆盖，'
              '因此不重写 notebook，而是**登记「旧 notebook → 新库模板」的映射与差异**。', '']
    DOC.parent.mkdir(parents=True, exist_ok=True)
    DOC.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f'\n登记表已写入：{DOC}', flush=True)


def main(argv=None):
    global LEGACY_ROOT
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument('--legacy-root', default=LEGACY_ROOT)
    parser.add_argument('--write', action='store_true', help='把登记表写进文档')
    args = parser.parse_args(argv)

    LEGACY_ROOT = args.legacy_root
    if not os.path.isdir(LEGACY_ROOT):
        record('旧 notebook 源目录', 'UNKNOWN',
               f'不存在：{LEGACY_ROOT}（跳过取证）')
        return 0
    record('旧 notebook 源目录', 'OK', LEGACY_ROOT)

    results = [compare_one(spec) for spec in P0]
    if args.write:
        write_doc(results)

    print('\n=== 汇总 ===')
    for item in results:
        print(f"{item['status']:>14}  {item['notebook'].replace(chr(92), '/')}")
    bad = [r for r in results if r['status'] == 'FAIL']
    print(f'\n一致 {sum(1 for r in results if r["status"] == "EQUIVALENT")} / '
          f'需补能力 {sum(1 for r in results if r["status"] == "NEEDS_FEATURE")} / '
          f'有差异 {sum(1 for r in results if r["status"] == "DIFF")} / '
          f'取证失败 {len(bad)}')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
