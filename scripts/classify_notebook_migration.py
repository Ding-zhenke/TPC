# -*- coding: utf-8 -*-
r"""
P5「87 个 notebook 迁移」—— **全量分类与登记**（只读，不执行 notebook）
=====================================================================

计划原文（`docs/next_plan/README.md` P5）：

> 按 87 个 notebook 清点表的 P0/P1/P2 顺序迁移，每个登记迁移结果及几何/仿真验收；
> P3 保留并注明不迁移原因。

P0 批次（5 个）已由 `scripts/verify_notebook_p0_migration.py` 逐值比对登记
（[P0 登记表](../guides/notebook_migration_p0.md)）。本脚本补 **P1/P2/P3 的其余 82 个**：

判据（全部离线：只解析 `.ipynb` 的 JSON，**不执行**任何单元格、不改源文件）
----------------------------------------------------------------------
对每个 notebook 抽三样证据，再决定"谁能覆盖它"：

1. **目录分类** → 器件类别（`直波导` / `普通单元天线` / `单元天线GRIB` /
   `椭圆透镜单元天线` / `多端口` / `MPMBA` / `开关尝试` / `功分器加天线` / `Leaky` / 分析类）；
2. **参数表特征**：是否出现透镜参数（`HEX_SIZE` / `ec_a` / `lens_*`）、MZI 特征（`ax/ay`、
   `px1..py6`）、功分特征（`1div` / `xq/yq`）、端口特征（`add_port` / `pick_face`）；
3. **模板覆盖**：本库现在有的 6 个模板（`StraightWaveguide` / `UnitAntenna` /
   `GRINLensAntenna` / `MultiPortAntenna` / `MZISwitch` / `PowerDivider`）里
   哪一个**在拓扑与参数口径上对应**。

结论状态
--------
``COVERED``       有模板对应，且关键参数口径能对上（可迁移）
``PARTIAL``       有模板对应，但该 notebook 有模板**未覆盖**的特征（列出）
``NO_TEMPLATE``   本库还没有对应器件模板（列出缺什么）
``NOT_MIGRATED``  P3：分析/测试/优化类，**保留不迁移**（写明原因）

⚠️ 本表**不是**"几何等价"结论：P0 那 5 个有参考工程可逐值核对，
P1/P2 的复杂器件模板走的是**本库口径**（设计记录 D1），所以这里只登记
「分类 / 对应模板 / 未覆盖特征 / 验收口径」，几何等价需按器件单独取证。

⚠️ **特征只从"去掉注释后的代码"里取**（2026-09-17 修正）：参考 notebook 里有大量
被注释掉的实验代码（8 个 MZI notebook 的 GRIB 透镜建环就是整段注释），
按原文匹配会凭空造出缺口。判据由
`tests/test_notebook_migration_classifier.py::test_commented_out_lens_code_is_not_a_feature`
等三条钉住。

⚠️ **特征要匹配"CST 参数/建模调用"，不要匹配裸标识符**（2026-09-18 修正）：
`dphi` 还出现在**分析/绘图**代码里（`mzi_opt_cal_feed.ipynb` 用它画相位差曲线），
于是 `phase_dphi` 被误判成器件缺口。现在只认 `para('dphi…')` 这种 CST 用法。
`2H4L` 同理：它出现在**docstring 的交叉引用**里（"参照 Ant6_2H4L_epc.ipynb 更新"），
现在只认结构本身（`xq` 数组 / `para('xq…')`）。
⇒ 判据错一次，缺口表就错一片 —— 这类"判据自身出错"目前有**四个**已知案例
（通用写法、注释代码、裸标识符、docstring 交叉引用），都由测试钉住。

⚠️ **带透镜的 notebook 判为 `COVERED` 的语义**：表示"该能力在本库有对应实现
（三条路线 `generate`/`dxf`/`insitu` + 相位），**不代表几何等价**" ——
**透镜的 per-arm 定位仍然未实现**（模板把透镜建在 0° 顶点/原点附近，
参考是把每枚透镜各自 `rotation(dphiN)` + `translate` 到臂端），
这一点在每个模板的证据文档里都记着。

用法::

    python scripts/classify_notebook_migration.py            # 打印汇总
    python scripts/classify_notebook_migration.py --write    # 写登记表
"""

import argparse
import io
import json
import os
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

#: 旧 notebook 源目录（与清点表同源）
LEGACY_ROOT = r'D:\成电博士生涯\拓扑光子晶体模型\硅基'
INVENTORY = PROJECT_ROOT / 'docs' / 'guides' / 'notebook_migration_inventory.md'
DOC = PROJECT_ROOT / 'docs' / 'guides' / 'notebook_migration_p1p2.md'

#: 目录 → （器件类别, 对应模板名, 优先级）
CATEGORY_RULES = (
    ('直波导',            '直波导',            'StraightWaveguide', 'P0'),
    ('普通单元天线',       '单元天线',          'UnitAntenna',       'P0'),
    ('单元天线GRIB',       'GRIN 透镜单元天线',  'GRINLensAntenna',   'P1'),
    ('椭圆透镜单元天线',    'GRIN 透镜单元天线',  'GRINLensAntenna',   'P1'),
    ('多端口',            '多端口天线',        'MultiPortAntenna',  'P1'),
    ('MPMBA',            '多端口天线',        'MultiPortAntenna',  'P1'),
    ('开关尝试',          'MZI 开关',         'MZISwitch',         'P2'),
    ('功分器加天线',       '功分器',            'PowerDivider',      'P2'),
    ('Leaky',            '泄漏波天线',        None,                'P2'),
    ('针对隔离和开关的分析研究', '分析/测试/优化',  None,            'P3'),
)

#: notebook 源码里的**器件类别特征**（只放"确有器件含义"的写法）。
#: ⚠️ 不放 `wg1` / `add_port` / `ax` 这类通用写法 —— 它们在几乎每个 notebook 里都有，
#: 会把一切都判成"有缺口"（第一版就是这么错的：68/82 全 PARTIAL，等于没有结论）。
FEATURE_PATTERNS = {
    'grin_lens': re.compile(r'HEX_SIZE|ec_a|para_init|gridlens', re.I),
    'lens_dxf': re.compile(r'dxf_import', re.I),
    'lens_in_situ': re.compile(r'\.hexagon\(', re.I),
    'lens_subproject': re.compile(r'import_subproject|\.sab', re.I),
    #: ⚠️ `dphi` 只认 **CST 参数用法**（`para('dphi…')`）。裸标识符 `dphi` 还会命中
    #: **分析/绘图代码**（`mzi_opt_cal_feed.ipynb` 用 `dphi = np.rad2deg(np.angle(...))`
    #: 画相位差曲线）—— 那是"对结果做的分析"，不是器件特征（2026-09-18 修正，
    #: 与"注释里的代码不算特征"同属**判据自身出错**）。
    'phase_dphi': re.compile(r"para\(\s*'dphi", re.I),
    'twisted_waveguide': re.compile(r'rotate_port|rotation_face', re.I),
    'mzi_arms_axay': re.compile(r"\.para\(\s*'a[xX]'", re.I),
    'pump_switching': re.compile(r'pump\d|create_material_custom', re.I),
    'mzi_parallel': re.compile(r'px10|py10', re.I),
    'mzi_anti': re.compile(r"\.para\(\s*'ax1'", re.I),
    #: ⚠️ `2H4L` **只认结构本身**（`xq` 数组 / `para('xq…')`），不认名字：三个 MPMBA
    #: notebook 里 `2H4L` 只出现在**docstring 的交叉引用**里
    #: （"参照 Ant6_2H4L_epc.ipynb 更新"），按名字匹配会凭空造出缺口
    #: （2026-09-18 修正 —— 与"注释代码""分析变量"同属**判据自身出错**）。
    'divider_2h4l': re.compile(r"\.para\(\s*'xq|\bxq\s*=", re.I),
}

#: 每个模板**能覆盖**的类别特征；其余特征出现即为缺口
TEMPLATE_CAPABILITIES = {
    'StraightWaveguide': set(),
    'UnitAntenna': set(),
    #: `phase_dphi` 有两层含义，两个模板各覆盖一层：
    #: * `GRINLensAntenna(lens_rotation=…)` = **透镜绕自身近焦点自转**（参考的 `dphi`）；
    #: * `PowerDivider(lens_phase=(dphi1,dphi2))` = 把透镜绕 z 转后当**第二个相位副本**。
    'GRINLensAntenna': {'grin_lens', 'lens_dxf', 'lens_in_situ', 'phase_dphi'},
    #: 多端口批次带透镜的 notebook：参考用 `dxf_import(component='gridlens')` 导入椭圆透镜，
    #: 本库三条路线（`generate`/`dxf`/`insitu`）都能建 —— 且按参考口径**单枚放原点**
    #: （`place=False`，无 Rbig 平移、无 6 份旋转复制）。
    'MultiPortAntenna': {'grin_lens', 'lens_dxf', 'lens_in_situ'},
    #: MZI 批次：`MZI-GRIB.ipynb` 的整段 GRIB 环透镜建环是**活代码** ⇒
    #: `MZISwitch` 的三条透镜路线覆盖它（口径同样是"单枚、近焦点在原点"）。
    'MZISwitch': {'mzi_arms_axay', 'pump_switching',
                  'grin_lens', 'lens_dxf', 'lens_in_situ'},
    #: 功分器家族：`pump_switching`（自定义材料 + 开关圆柱 + 区域副本求交 + insert）
    #: 与 `phase_dphi`（第二枚相位副本）都已实现。
    'PowerDivider': {'grin_lens', 'lens_dxf', 'lens_in_situ', 'phase_dphi',
                     'pump_switching'},
}

#: 缺口特征 → 人话说明（写进登记表）
GAP_MEANING = {
    'lens_in_situ': '该 notebook 在 CST 内用 `app.hexagon()` 逐环建透镜；'
                    '`GRINLensAntenna(lens_method="insitu")` 与 '
                    '`PowerDivider(lens_method="insitu")` 都已覆盖这条路线，'
                    '出现在这里说明该 notebook 对应的模板两者都不是',
    'lens_subproject': '透镜来自 CST 子工程（`.sab`），本库无对应入口',
    'twisted_waveguide': '扭波导（`rotate_port`/`rotation_face`），本库无对应入口',
    'mzi_parallel': 'MZI 并联（10 点路径），本模板只实现 6 点的 basic（== cascade）',
    'mzi_anti': 'MZI anti（两组 `ax/ay` + 不对称泵浦），本模板未实现',
    'divider_2h4l': '2H4L 双透镜组结构，1分6 用的不是本模板的 2×3 级联',
    'grin_lens': '该 notebook 带 GRIN 透镜参数，而对应模板本身不含透镜',
    'lens_dxf': '该 notebook 用 DXF 导入透镜，而对应模板本身不含透镜',
    'phase_dphi': '该 notebook 用相位差 `dphi`（转透镜实现），对应模板未实现',
    'pump_switching': '该 notebook 有泵浦/开关结构（`pump`、自定义材料），对应模板未实现',
}

_results = []


def record(item, status, detail, **extra):
    entry = {'item': item, 'status': status, 'detail': detail}
    entry.update(extra)
    _results.append(entry)
    return entry


# ================================================================
# 读清点表（拿到 notebook 列表与优先级）
# ================================================================

def inventory_rows():
    """从清点表里读 ``[(相对路径, 优先级), ...]``。"""
    if not os.path.isfile(INVENTORY):
        return []
    text = io.open(INVENTORY, encoding='utf-8').read()
    rows = []
    pattern = re.compile(r'^\|\s*\d+\s*\|\s*`([^`]+\.ipynb)`\s*\|\s*(P\d)\s*\|')
    for line in text.splitlines():
        match = pattern.match(line.strip())
        if match:
            rows.append((match.group(1).replace('/', os.sep), match.group(2)))
    return rows


# ================================================================
# 读 notebook（只解析 JSON，不执行）
# ================================================================

def notebook_source(path):
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding='utf-8') as handle:
            nb = json.load(handle)
    except Exception:                                   # noqa: BLE001
        return None
    return '\n'.join(''.join(cell.get('source', []))
                     for cell in nb.get('cells', [])
                     if cell.get('cell_type') == 'code')


def classify(rel_path):
    """按目录前缀分类：返回 (类别, 模板名, 优先级)。"""
    head = rel_path.split(os.sep)[0]
    for prefix, category, template, priority in CATEGORY_RULES:
        if head == prefix or head.startswith(prefix):
            return category, template, priority
    return '未分类', None, 'P3'


def strip_comments(text):
    """去掉**整行注释与行尾注释**（简易状态机，只跟踪单/双引号）。

    ⚠️ 为什么必须做（2026-09-17 发现）：notebook 里有大量**被注释掉的实验代码**，
    例如 8 个 MZI notebook 把整段 GRIB 环透镜建环代码注释掉了
    （`#     app1.hexagon('r1','h', …)`）。按原文匹配特征会把"注释里的透镜"
    当成"这个器件要透镜"，凭空造出 9 个不存在的缺口。

    只按 `#` 切分（跳过字符串里的 `#`，例如颜色 `'#ff0000'`）；
    **不**处理三引号块（本仓 notebook 的特征代码不在其中）。
    """
    out = []
    for line in (text or '').splitlines():
        res = []
        quote = None
        for ch in line:
            if quote:
                res.append(ch)
                if ch == quote:
                    quote = None
            elif ch in '"\'':
                quote = ch
                res.append(ch)
            elif ch == '#':
                break
            else:
                res.append(ch)
        out.append(''.join(res))
    return '\n'.join(out)


def features_of(text):
    """notebook 源码命中了哪些特征（**注释不算**）。"""
    return {name for name, pattern in FEATURE_PATTERNS.items()
            if pattern.search(text or '')}


def audit_one(rel_path, priority):
    """登记一个 notebook。"""
    path = os.path.join(LEGACY_ROOT, rel_path)
    label = rel_path.replace(os.sep, '/')
    text = notebook_source(path)
    if text is None:
        record(label, 'FAIL', f'读不到：{path}')
        return {'notebook': label, 'status': 'FAIL', 'notes': '文件缺失或不是合法 ipynb'}

    # ⚠️ 判据一律基于**去掉注释后**的代码：注释里的实验代码不代表器件需求
    code = strip_comments(text)
    category, template, _prio = classify(rel_path)
    feats = features_of(code)
    n_para = len(re.findall(r'\.para\(', code))
    has_port = bool(feats & {'multiport'})

    if priority == 'P3' or template is None:
        reason = ('P3：分析/测试/优化类，按计划**保留不迁移**'
                  if priority == 'P3' else '本库还没有对应器件模板')
        return {'notebook': label, 'priority': priority, 'category': category,
                'template': template, 'status': 'NOT_MIGRATED' if priority == 'P3'
                else 'NO_TEMPLATE',
                'features': sorted(feats), 'n_para': n_para,
                'notes': reason, 'has_port': has_port}

    covered = TEMPLATE_CAPABILITIES.get(template, set())
    gaps = sorted(feats - covered)
    status = 'COVERED' if not gaps else 'PARTIAL'
    detail = ('；'.join(GAP_MEANING.get(g, g) for g in gaps)
              if gaps else '拓扑/参数口径对应')
    return {'notebook': label, 'priority': priority, 'category': category,
            'template': template, 'status': status, 'features': sorted(feats),
            'gaps': gaps, 'n_para': n_para, 'has_port': has_port,
            'notes': detail, 'gap_notes': [GAP_MEANING.get(g, g) for g in gaps]}


def main(argv=None):
    global LEGACY_ROOT
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument('--legacy-root', default=LEGACY_ROOT)
    parser.add_argument('--write', action='store_true')
    parser.add_argument('--only', default=None, help='只看某个优先级（P1/P2/P3）')
    args = parser.parse_args(argv)

    LEGACY_ROOT = args.legacy_root

    rows = inventory_rows()
    if not rows:
        print(f'⚠️ 清点表里没读到 notebook 行：{INVENTORY}')
        return 1
    print(f'清点表：{len(rows)} 个 notebook')

    results = []
    for rel_path, priority in rows:
        if priority == 'P0':
            continue                                    # P0 已由另一个脚本逐值登记
        if args.only and priority != args.only:
            continue
        results.append(audit_one(rel_path, priority))

    from collections import Counter
    by_status = Counter(r['status'] for r in results)
    by_template = Counter(r.get('template') or '（无模板）' for r in results)
    by_category = Counter(r.get('category', '?') for r in results)

    print('\n=== 状态 ===')
    for key, count in by_status.most_common():
        print(f'  {key:<14} {count}')
    print('\n=== 按器件类别 ===')
    for key, count in by_category.most_common():
        print(f'  {key:<20} {count}')
    print('\n=== 对应模板 ===')
    for key, count in by_template.most_common():
        print(f'  {key:<20} {count}')
    print('\n=== 有缺口的 notebook（前 20）===')
    shown = 0
    for r in results:
        if r['status'] in ('PARTIAL', 'NO_TEMPLATE'):
            print(f"  [{r['status']}] {r['notebook']}"
                  f" → {r.get('template') or '无模板'}；{r.get('notes')}")
            shown += 1
            if shown >= 20:
                break

    if args.write:
        write_doc(results, by_status, by_category, by_template)
    failed = [r for r in _results if r['status'] == 'FAIL']
    return 1 if failed else 0


def write_doc(results, by_status, by_category, by_template):
    lines = ['# 旧 notebook 迁移登记：P1/P2/P3 批次', '',
             '> 本表由 `python scripts/classify_notebook_migration.py --write` 生成'
             '（只解析 `.ipynb` 的 JSON，**不执行** notebook、不改源文件）。',
             '> P0 的 5 个见 [P0 登记表](./notebook_migration_p0.md)；',
             '> 清点表见 [notebook_migration_inventory.md](./notebook_migration_inventory.md)。', '',
             '## 1. 汇总', '', '| 状态 | 数量 |', '|---|---|']
    for key, count in by_status.most_common():
        lines.append(f'| {key} | {count} |')
    lines += ['', '| 器件类别 | 数量 | 对应模板 |', '|---|---|---|']
    template_by_category = {}
    for r in results:
        template_by_category.setdefault(r.get('category', '?'),
                                        r.get('template') or '（无模板）')
    for key, count in by_category.most_common():
        lines.append(f'| {key} | {count} | {template_by_category.get(key, "—")} |')

    lines += ['', '## 2. 状态含义', '',
              '| 状态 | 含义 |', '|---|---|',
              '| `COVERED` | 有模板对应，拓扑/参数口径能对上（可迁移） |',
              '| `PARTIAL` | 有模板对应，但该 notebook 有模板**未覆盖**的特征（见列） |',
              '| `NO_TEMPLATE` | 本库还没有对应器件模板（列出缺什么） |',
              '| `NOT_MIGRATED` | P3 分析/测试/优化类，**保留不迁移** |', '']

    # 缺口汇总：按特征聚合（这是本表最有行动价值的部分）
    from collections import Counter
    gap_counts = Counter()
    gap_examples = {}
    for item in results:
        for gap in item.get('gaps', []):
            gap_counts[gap] += 1
            gap_examples.setdefault(gap, item['notebook'])
    if gap_counts:
        lines += ['## 3. 缺口汇总（按特征聚合）', '',
                  '| 缺口特征 | 影响 notebook 数 | 含义 | 例子 |', '|---|---|---|---|']
        for gap, count in gap_counts.most_common():
            meaning = GAP_MEANING.get(gap, gap)
            lines.append(f'| `{gap}` | {count} | {meaning} | `{gap_examples[gap]}` |')
        lines.append('')
        top = gap_counts.most_common(3)
        lines += ['> **缺口性质**：`lens_in_situ`（在 CST 内用 `app.hexagon()` 逐环建透镜）'
                  '**本库已实现** —— `GRINLensAntenna(lens_method="insitu")`，'
                  '见 [P5 就地环透镜证据](../validation/p5_grin_lens_insitu_evidence.md)。'
                  '它在下面仍出现，是因为命中该特征的 notebook 对应的模板**不是** '
                  '`GRINLensAntenna`（模板归属由目录分类决定），'
                  '而不是「库里做不到」——真要把它们迁进来，仍需要给对应器件补透镜能力。',
                  '',
                  '> 当前影响最大的三项缺口：'
                  + '、'.join(f'`{g}`（{c} 个）' for g, c in top) + '。', '']
        header_offset = 4
    else:
        header_offset = 3

    lines += [f'## {header_offset}. 逐条登记', '',
              '| # | notebook | 优先级 | 类别 | 模板 | 状态 | CST 参数行 | 未覆盖特征 |',
              '|---|---|---|---|---|---|---|---|']
    for index, item in enumerate(results, 1):
        lines.append(f"| {index} | `{item['notebook']}` | {item.get('priority', '—')} | "
                     f"{item.get('category', '—')} | `{item.get('template') or '—'}` | "
                     f"{item['status']} | {item.get('n_para', '—')} | "
                     f"{', '.join(item.get('gaps', [])) or '—'} |")
    lines += ['', '## 4. 验收口径', '',
              '* **几何验收**：P0 已逐值比对；P1/P2 的复杂器件模板走**本库口径**'
              '（设计记录 D1），因此本表只登记「分类 / 对应模板 / 未覆盖特征」，'
              '**不声称几何等价**；每个器件要单独取证才有几何结论。',
              '* **仿真验收**：**全部未做**（需要真实求解）—— 属计划 P4/V2、V7、V9，'
              '等用户确认算例与开销。',
              '* **迁移方式**：不重写 notebook，而是登记「旧 notebook → 新库模板」的映射；'
              '有缺口的部分要么补模板能力，要么在计划里明确不做。', '']
    DOC.parent.mkdir(parents=True, exist_ok=True)
    DOC.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f'\n登记表已写入：{DOC}')


if __name__ == '__main__':
    sys.exit(main())
