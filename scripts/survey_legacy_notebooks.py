# -*- coding: utf-8 -*-
r"""
旧 notebook 清点（阶段 8 判据 3 的输入）
======================================
扫 `D:\成电博士生涯\拓扑光子晶体模型\硅基\` 下的 `.ipynb`，
逐个给出：目录分类、迁移优先级、是否含 CST 建模代码、是否已在新库里被覆盖。

**只读**：不改任何 notebook，不执行任何 notebook。

输出：`docs/guides/notebook_migration_inventory.md`

用法::

    python scripts/survey_legacy_notebooks.py            # 用默认源目录
    python scripts/survey_legacy_notebooks.py <源目录>   # 换目录
"""

import io
import json
import os
import re
import sys
from collections import Counter, OrderedDict

SRC_DEFAULT = r'D:\成电博士生涯\拓扑光子晶体模型\硅基'
OUT_DEFAULT = os.path.join('docs', 'guides', 'notebook_migration_inventory.md')

# ---- 分类规则：按目录判定（长前缀优先）----
CATEGORIES = [
    ('直波导',            'P0', '基础流水线（已有 StraightWaveguide 覆盖）'),
    ('普通单元天线',       'P0', '基础流水线（已有 UnitAntenna 覆盖）'),
    ('单元天线GRIB',       'P1', 'GRIN 透镜天线（最大类）'),
    ('椭圆透镜单元天线',    'P1', 'GRIN 透镜天线（最大类）'),
    ('多端口',            'P1', '多端口天线（验证多路径）'),
    ('MPMBA',            'P1', '多端口天线（验证多路径）'),
    ('功分器加天线',       'P2', '功分器 / 耦合器（验证分支结构）'),
    ('开关尝试',           'P2', 'MZI 开关（验证复杂干涉结构）'),
    ('Leaky',            'P2', '泄漏波天线（原表未单列，归 P2）'),
    ('针对隔离和开关的分析研究', 'P3', '分析类（原表 P3「分析/测试/优化」）'),
]

# ---- 代码特征 ----
#
# ⚠️ **教训（第一版踩的坑）**：用自由文本正则判「这个 notebook 在干什么」会严重虚高 ——
#   `split` 命中了 Python 的 `str.split()`（81/87 全中）、`Nx\b` 命中了普通变量（69/87）。
#   所以这里改成**两条更可靠的证据**：
#     ① CST 参数名（`.para('x1', …)` / `StoreParameter` / `('x1', 4, …)` 里的名字）——
#        参数表是这个模型的「物理指纹」；
#     ② 收紧后的分词正则（只在 code 里找、不用会命中标准库的裸词）。
PARAM_RE = re.compile(
    r"""(?:\.para|\.StoreParameter|StoreParameter)\s*\(\s*['"]([A-Za-z_][\w]*\s*)['"]"""
    r"""|['"]([A-Za-z_][\w*]*)['"]\s*,\s*[-\d.]+\s*,\s*['"]"""
)

#: 各特征用「参数名集合」判定
PARAM_SIGNATURES = {
    'lens':    ('ec_a', 'ec_b', 'ec_c', 'Nx', 'Ny', 'd0', 'r1', 'r2', 'ratio', 'a2'),
    'mzi':     ('MZI', 'mzi', 'arm', 'L1', 'L2', 'phase', 'nsm', 'Rbig'),
    'divider': ('1div', 'div2', 'div3', 'div4', 'lx1', 'lx2', 'nsm', 'Rbig'),
    'port':    ('port_num', 'num_ports', 'n_port', 'PortNum'),
}

#: 特征正则：**只保留不会被标准库命中的**
FEATURES = [
    ('cst_param',  re.compile(r'StoreParameter|\.para\s*\(|StoreParameters')),
    ('hex',        re.compile(r'hexlib|HEX_SIZE|create_hex_polygon|六边形孔')),
    ('dxf',        re.compile(r"\.dxf['\"]|save_to_dxf|dxf_import|DXF\s*\\?\"?")),
    ('rot',        re.compile(r'rotation\s*\(|repetition\s*=|旋转复制')),
    ('ga',         re.compile(r'fitness|种群|遗传|pop_init|crossover')),
    ('mzi_text',   re.compile(r'MZI')),                 # 仅作辅助证据
    ('divider_text', re.compile(r'1\s*分\s*[2-9]|功分|分路器|power_divider')),
]

PRIORITY_ORDER = ['P0', 'P1', 'P2', 'P3']


def classify(rel_dir: str):
    """按目录给 (分类, 优先级, 说明)；未命中归 P3。"""
    for prefix, pri, note in CATEGORIES:
        if rel_dir == prefix or rel_dir.startswith(prefix + os.sep) or \
                rel_dir.startswith(prefix):
            return prefix, pri, note
    return '未分类', 'P3', '原表 P3「其余未分类」'


def notebook_text(path: str, limit_bytes: int = 3_000_000) -> str:
    """把 .ipynb 的所有 code cell 源码拼起来（只读 JSON，不执行）。"""
    with io.open(path, encoding='utf-8', errors='replace') as fh:
        raw = fh.read(limit_bytes)
    try:
        nb = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    parts = []
    for cell in nb.get('cells', []):
        if cell.get('cell_type') != 'code':
            continue
        src = cell.get('source', '')
        parts.append(''.join(src) if isinstance(src, list) else str(src))
    return '\n'.join(parts)


def extract_params(text: str):
    """抽出这个 notebook 里出现过的 CST 参数名（去重、保持出现顺序）。"""
    names = []
    for m in PARAM_RE.finditer(text):
        name = (m.group(1) or m.group(2) or '').strip()
        if name and name not in names:
            names.append(name)
    return names


def detect(text: str, params):
    """
    判定特征：**参数名证据优先**，正则只作补充。

    :return: dict[特征名 -> bool]，另含 ``params`` 与 ``n_params``
    """
    pset = set(params)
    out = {}
    for feat, sig in PARAM_SIGNATURES.items():
        hit = pset & set(sig)
        out[feat] = bool(hit)
        out[f'{feat}_hits'] = sorted(hit)
    for name, pat in FEATURES:
        out[name] = bool(pat.search(text))
    out['params'] = params
    out['n_params'] = len(params)
    return out


def scan(src_root: str):
    rows = []
    for dirpath, dirnames, filenames in os.walk(src_root):
        dirnames[:] = [d for d in dirnames if d not in ('__pycache__', '.ipynb_checkpoints')]
        for fn in sorted(filenames):
            if not fn.endswith('.ipynb'):
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, src_root)
            rel_dir = os.path.dirname(rel)
            text = notebook_text(full)
            params = extract_params(text)
            cat, pri, note = classify(rel_dir)
            rows.append({
                'rel': rel.replace(os.sep, '/'),
                'dir': (rel_dir or '.').replace(os.sep, '/'),
                'name': fn,
                'category': cat,
                'priority': pri,
                'note': note,
                'size_kb': round(os.path.getsize(full) / 1024, 1),
                'code_lines': text.count('\n') + 1,
                'features': detect(text, params),
            })
    return rows


def main(argv):
    src = argv[1] if len(argv) > 1 else SRC_DEFAULT
    out = argv[2] if len(argv) > 2 else OUT_DEFAULT
    if not os.path.isdir(src):
        print(f'[FAIL] 源目录不存在：{src}')
        return 2
    rows = scan(src)
    if not rows:
        print(f'[FAIL] {src} 下没有 .ipynb')
        return 2

    by_cat = OrderedDict()
    for r in rows:
        by_cat.setdefault(r['category'], []).append(r)
    counts = Counter(r['priority'] for r in rows)

    L = []
    L.append('# 旧 notebook 清点表（阶段 8 判据 3 的输入）')
    L.append('')
    L.append('> **本文件由 `scripts/survey_legacy_notebooks.py` 生成**（只读扫描，不执行 notebook）。')
    L.append('> 用途：让「71 个 notebook 的迁移状态逐个可查」这句话变成一张**真的表**。')
    L.append('')
    L.append(f'- 源目录：`{src}`')
    L.append(f'- `.ipynb` 总数：**{len(rows)}**')
    L.append('- 扫描方式：只解析 `.ipynb` 的 JSON 结构、抽 code cell 源码做**正则特征匹配**；')
    L.append('  **不执行**任何单元格，也不改动任何源文件。')
    L.append('')
    L.append('## 1. 按优先级汇总')
    L.append('')
    L.append('| 优先级 | 含义 | notebook 数 |')
    L.append('|---|---|---|')
    pri_meaning = {
        'P0': '验证基础流水线（直波导 / 普通单元天线 / 透镜核心）',
        'P1': 'GRIN 透镜（最大类）+ 多端口天线',
        'P2': '功分器 / 耦合器 + MZI 开关',
        'P3': '分析/测试/优化 + 未分类（**保留，不迁移**）',
    }
    for pri in PRIORITY_ORDER:
        n = counts.get(pri, 0)
        if pri == 'P0':
            n = counts.get('P0', 0)
        L.append(f'| {pri} | {pri_meaning[pri]} | {n} |')
    L.append(f'| **合计** | | **{len(rows)}** |')
    L.append('')
    L.append('## 2. 按分类汇总')
    L.append('')
    L.append('| 分类（目录） | 优先级 | 数量 | 说明 | 新库里对应能力 |')
    L.append('|---|---|---|---|---|')
    cover = {
        '直波导': '✅ `StraightWaveguide`',
        '普通单元天线': '✅ `UnitAntenna`',
        '单元天线GRIB': '🔄 `builders/lens.py`（几何已就绪，模板待建）',
        '椭圆透镜单元天线': '🔄 `builders/lens.py`（几何已就绪，模板待建）',
        '多端口': '❌ 无（阶段 8 多路径）',
        'MPMBA': '❌ 无（阶段 8 多路径）',
        '功分器加天线': '❌ 无（阶段 8 功分器）',
        '开关尝试': '❌ 无（阶段 8 MZI）',
        'Leaky': '❌ 无',
        '针对隔离和开关的分析研究': '➖ 不迁移（分析类）',
        '未分类': '➖ 不迁移',
    }
    for cat, items in sorted(by_cat.items(), key=lambda kv: (PRIORITY_ORDER.index(kv[1][0]['priority']), -len(kv[1]))):
        L.append(f"| `{cat}` | {items[0]['priority']} | {len(items)} | {items[0]['note']} "
                 f"| {cover.get(cat, '—')} |")
    L.append('')
    L.append('## 3. 逐个清单（迁移前先看这一列）')
    L.append('')
    L.append('**证据说明**：`CST 参数` = 从 `.para(...)` / `StoreParameter` / CST 参数三元组里抽到的'
             '参数**个数**；`透镜 / MZI / 功分 / 端口` 由**参数名**是否命中对应签名判定'
             '（比自由文本正则可靠得多）；`六边 / DXF / 旋转 / GA` 是收紧后的正则特征。')
    L.append('')
    L.append('| # | 相对路径 | 优先级 | 大小(KB) | 代码行 | CST 参数 | 透镜 | MZI | 功分 | 端口 | 六边 | DXF | 旋转 | GA |')
    L.append('|---|---|---|---|---|---|---|---|---|---|---|---|---|---|')
    for i, r in enumerate(sorted(rows, key=lambda r: (PRIORITY_ORDER.index(r['priority']), r['rel'])), 1):
        f = r['features']
        mark = lambda k: '✓' if f[k] else ''
        L.append(f"| {i} | `{r['rel']}` | {r['priority']} | {r['size_kb']} | {r['code_lines']} "
                 f"| {f['n_params']} | {mark('lens')} | {mark('mzi')} | {mark('divider')} "
                 f"| {mark('port')} | {mark('hex')} | {mark('dxf')} | {mark('rot')} | {mark('ga')} |")
    L.append('')
    L.append('## 4. 特征交叉（用于判断「4/6 端口到底有没有数据依据」）')
    L.append('')
    L.append('| 问题 | 命中的 notebook |')
    L.append('|---|---|')
    checks = [
        ('参数表像**GRIN 透镜**（含 ec_a/ec_b/ec_c/Nx/Ny/d0/r1/r2/ratio/a2 之一）',
         lambda r: r['features']['lens']),
        ('参数表像**MZI / 干涉臂**（含 MZI/arm/L1/L2/phase/nsm/Rbig 之一）',
         lambda r: r['features']['mzi']),
        ('参数表像**功分器**（含 1div*/div2-4/lx1/lx2 之一）',
         lambda r: r['features']['divider']),
        ('代码里出现 `MZI` 字样（辅助证据，可能只是注释）',
         lambda r: r['features']['mzi_text']),
        ('代码里出现「功分 / 分路」字样（辅助证据）',
         lambda r: r['features']['divider_text']),
        ('含 DXF 导入（透镜的 DXF 路线）', lambda r: r['features']['dxf']),
        ('含遗传算法特征', lambda r: r['features']['ga']),
    ]
    for title, pred in checks:
        hits = [r['rel'] for r in rows if pred(r)]
        shown = ', '.join(f'`{h}`' for h in hits[:6]) + ('…' if len(hits) > 6 else '')
        L.append(f'| {title} | **{len(hits)}** 个' + (f'：{shown}' if hits else '') + ' |')
    L.append('')
    L.append('### 4.1 多端口的结构到底存不存在（红绿灯项）')
    L.append('')
    L.append('计划把「4 / 6 端口目前无数据依据」标成红灯，要求先确认这两种结构在旧代码里是否存在。'
             '下面是**按文件名**能直接看到的证据（不依赖任何启发式）：')
    L.append('')
    L.append('| 端口数 | 证据（文件名） |')
    L.append('|---|---|')
    for n, pat in ((2, r'Ant2_|1div2'), (3, r'Ant3_'), (4, r'Ant4_|1分4|1div4'),
                   (6, r'Ant6_|ANT6_')):
        names = [r['rel'] for r in rows if re.search(pat, r['rel'])]
        L.append(f'| **{n} 端口** | {len(names)} 个：' +
                 (', '.join(f'`{x}`' for x in names[:8]) + ('…' if len(names) > 8 else '')) +
                 ' |')
    L.append('')
    L.append('### 4.2 各分类里出现最多的参数名（用于补规格缺口）')
    L.append('')
    L.append('| 分类 | 出现最多的 CST 参数名（前 20） |')
    L.append('|---|---|')
    for cat, items in sorted(by_cat.items()):
        counter = Counter()
        for r in items:
            counter.update(r['features']['params'])
        top = ', '.join(f'`{k}`' for k, _ in counter.most_common(20))
        L.append(f'| `{cat}` | {top or "（未抽到参数名）"} |')
    L.append('')

    parent = os.path.dirname(os.path.abspath(out))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with io.open(out, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write('\n'.join(L))

    print(f'扫描 {src}')
    print(f'  .ipynb 总数：{len(rows)}')
    print('  按优先级：' + ', '.join(f'{k}={counts.get(k, 0)}' for k in PRIORITY_ORDER))
    print(f'  写出：{out}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
