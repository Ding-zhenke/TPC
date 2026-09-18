# -*- coding: utf-8 -*-
r"""
旧 notebook **导入兼容**审计（P1 验收判据「旧 notebook 导入兼容」）
=================================================================

计划里「旧 notebook 导入兼容」写的是「✅ 已完成」，但这个判据此前**没有被验证过** ——
本脚本把它变成可复现的检查：扫 87 个旧 notebook 的**导入语句**（只读 JSON，**不执行**
任何单元格），逐条判定它在**当前仓库**里是否能解析。

判定的四类
----------
============================  ====================================================
``stdlib``                    标准库（`sys.stdlib_module_names`）
``cst``                       CST 自带（`cst.interface` / `cst.results`）——
                              由 CST 安装提供，不在仓库里，也不算缺口
``current``                   当前顶层包（`cst_solver` / `mesh_grid` / `topo_modeler`
                              / `topo_templates` / `tpc_toolkit` / `tpc_service`
                              / `templates`）
``legacy``                    旧名，由 `archive/compat/` 下的兼容入口转发
``third-party``               需要另外 pip 安装的第三方包
``unknown``                   **两边都不是** —— 真正的缺口，要逐个交代
============================  ====================================================

对 ``current`` / ``legacy`` 的导入还会**逐个符号**核对（`from X import a` 里的 `a`
必须真的存在）。这一步只导入本仓库的包，**不会导入 CST**（库的契约就是导入期不加载 CST）。

输出：`docs/guides/notebook_import_audit.md`；缺 `current`/`legacy` 依赖时退出码 1。

用法::

    python scripts/check_notebook_imports.py                # 用默认源目录
    python scripts/check_notebook_imports.py <源目录>        # 换目录
    python scripts/check_notebook_imports.py --quiet        # 只打印汇总
"""

import argparse
import importlib
import importlib.util
import io
import json
import os
import re
import sys
from collections import OrderedDict

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

SRC_DEFAULT = r'D:\成电博士生涯\拓扑光子晶体模型\硅基'
OUT_DEFAULT = os.path.join('docs', 'guides', 'notebook_import_audit.md')
COMPAT_DIR = os.path.join(_REPO, 'archive', 'compat')

#: 当前仓库的顶层包（`templates` 是 `topo_templates` 的兼容 shim）
CURRENT_PACKAGES = ('cst_solver', 'mesh_grid', 'topo_modeler', 'topo_templates',
                    'tpc_service', 'tpc_toolkit', 'templates')

#: CST 安装提供（不要求可导入，只要有 CST 就好）
CST_MODULES = ('cst',)

#: 第三方：需要另外安装；不算仓库缺口，但要在报告里列出来
THIRD_PARTY = ('numpy', 'matplotlib', 'scipy', 'sympy', 'tqdm', 'pandas',
               'shapely', 'ezdxf', 'dxfgrabber', 'seaborn', 'sklearn',
               'plotly', 'PIL', 'cv2', 'gmsh')

#: 已知且**已交代**的缺口：名字 -> 说明（新增缺口会让测试失败，强制逐个交代）。
#: ⚠️ 能定位到等价实现的**不算缺口** —— 那属于 `MIGRATED_MODULES`。
KNOWN_MISSING = {}

#: 旧模块名 -> 它在当前库里的**等价实现**（同名 API 已迁移）。
#: 这类不需要"找回模块"，只需要把导入行改一下；本脚本会**核对目标模块真的提供同样的 API**，
#: 目标改名/删函数会让检查失败（所以这张表不会悄悄失效）。
MIGRATED_MODULES = {
    'metalen': {
        'target': 'tpc_toolkit.effective_medium',
        'names': ('hex_area_from_lattice', 'hex_area_from_side', 'ep_cal_air',
                  'permittivity_to_refractive_index'),
        'alias_to': 'mt',
        'note': '旧的自定义材料计算模块；四个函数在 `tpc_toolkit.effective_medium` 里'
                '**同名存在**（含 `ep_cal_air` 的比值公式），只需把导入行换成'
                '`from tpc_toolkit import effective_medium as mt`，其余代码不用动。',
        'notebooks': ('椭圆透镜单元天线/BA/D120/ep_cal.ipynb',),
    },
    'cst_solver.result': {
        'target': 'cst_solver',
        'names': ('result', 'Result', 'setup'),
        'alias_to': '',
        'note': 'v2.0 起 `cst_solver.result` **不再是子模块**：`result` 是顶层别名'
                '（`from cst_solver import result`），旧写法 '
                '`from cst_solver.result import result` 会 `ModuleNotFoundError`。'
                '⚠️ 这里**刻意不补** `cst_solver/result.py`：一旦存在同名子模块，'
                '导入它之后包的 `result` 属性会被**模块对象遮蔽**，'
                '反而破坏 `from cst_solver import result`（现有测试断言 `result` 是类）。'
                '所以只能改导入行。',
        'notebooks': ('Leaky/ANT_LEAKY_MK_GRID_opt.ipynb',),
    },
}

#: `archive/compat/` 提供的旧名（判符号时会按文档做法把该目录加进 `sys.path`）
COMPAT_NAMES = ('tri_lib', 'hexlib')


# ============================================================
# 解析
# ============================================================

_MAGIC_RE = re.compile(r'^\s*(%{1,2}\w|!\w|\?\w)')
_IMPORT_LINE_RE = re.compile(
    r'^\s*(?:from\s+([\w\.]+)\s+import\s+(.+)|import\s+([\w\.]+)(?:\s+as\s+(\w+))?)\s*$')


def strip_magics(source: str) -> str:
    """
    去掉 IPython 魔法/Shell 行，让 notebook 单元格能被 `ast` 解析。

    :param source: str, 单元格源码
    :return: str
    """
    lines = []
    for line in source.splitlines():
        if _MAGIC_RE.match(line):
            lines.append('')                     # 保持行号
        else:
            lines.append(line)
    return '\n'.join(lines)


def parse_imports(source: str):
    """
    解析一个单元格里的导入语句。

    :param source: str, 源码（可含魔法）
    :return: list[dict], ``{'module', 'names', 'asname', 'line'}``
        ``names`` 为 ``None`` 表示 ``import X``（不核对符号）；否则是要从 X 取的名字
    """
    import ast

    refs = []
    text = strip_magics(source)
    try:
        import warnings
        with warnings.catch_warnings():
            # 旧 notebook 里常写 Windows 路径（`'D:\成电...'`），`ast.parse` 会为此发
            # DeprecationWarning —— 那是**被审计对象的**写法，不该污染审计输出
            warnings.simplefilter('ignore')
            tree = ast.parse(text)
    except SyntaxError:
        return _parse_imports_by_regex(text)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                refs.append({'module': alias.name, 'names': None,
                             'asname': alias.asname, 'line': node.lineno})
        elif isinstance(node, ast.ImportFrom):
            if node.level:                       # 相对导入（notebook 里基本没有）
                continue
            if not node.module:
                continue
            refs.append({'module': node.module,
                         'names': [a.name for a in node.names],
                         'asname': None, 'line': node.lineno})
    return refs


def _parse_imports_by_regex(text: str):
    """`ast` 解析不了（单元格里有非 Python 片段）时的兜底：逐行正则。"""
    refs = []
    for index, line in enumerate(text.splitlines(), start=1):
        match = _IMPORT_LINE_RE.match(line)
        if not match:
            continue
        if match.group(1):                       # from X import a, b
            names = [n.strip().split(' as ')[0].strip()
                     for n in match.group(2).split(',') if n.strip()]
            refs.append({'module': match.group(1), 'names': names,
                         'asname': None, 'line': index})
        else:                                    # import X [as Y]
            refs.append({'module': match.group(3), 'names': None,
                         'asname': match.group(4), 'line': index})
    return refs


def notebook_text(path: str, limit_bytes: int = 3_000_000) -> str:
    """所有 code cell 的源码拼起来（只读，不执行）。"""
    with io.open(path, encoding='utf-8', errors='replace') as handle:
        raw = handle.read(limit_bytes)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    parts = []
    for cell in payload.get('cells', []):
        if cell.get('cell_type') != 'code':
            continue
        src = cell.get('source', '')
        parts.append(''.join(src) if isinstance(src, list) else str(src))
    return '\n'.join(parts)


# ============================================================
# 分类
# ============================================================

def classify(module: str) -> str:
    """
    判定一个顶层模块属于哪一类。

    :param module: str, 形如 ``cst_solver`` 或 ``mesh_grid.tri_grid``
    :return: str, ``stdlib`` / ``cst`` / ``current`` / ``legacy`` / ``migrated`` /
        ``third-party`` / ``unknown``
    """
    top = module.split('.')[0]
    if module in MIGRATED_MODULES:               # 先按**完整路径**判（子模块级迁移）
        return 'migrated'
    if top in CURRENT_PACKAGES:
        return 'current'
    if top in CST_MODULES:
        return 'cst'
    if _legacy_shim_path(top):
        return 'legacy'
    if top in getattr(sys, 'stdlib_module_names', ()):
        return 'stdlib'
    if top in THIRD_PARTY:
        return 'third-party'
    if top in MIGRATED_MODULES:
        return 'migrated'
    return 'unknown'


def _legacy_shim_path(top: str):
    """`archive/compat/` 下是否有这个旧名的兼容入口（`<name>.py` 或 `<name>_shim.py`）。"""
    if not os.path.isdir(COMPAT_DIR):
        return None
    for candidate in (f'{top}.py', f'{top}_shim.py'):
        path = os.path.join(COMPAT_DIR, candidate)
        if os.path.isfile(path):
            return path
    return None


def resolve_symbols(module: str, names, extra_paths=()):
    """
    核对 ``from module import names`` 里的名字是否真的存在。

    ⚠️ 会导入本仓库的包（导入期不加载 CST，这是库的契约），但**不会**导入 CST 本体。

    :param module: str, 模块名
    :param names: list[str]|None, None 表示不核对
    :param extra_paths: 序列, 解析期间额外加到 `sys.path` 前面的目录
        （旧名要按**文档给使用者的做法**来判：把 `archive/compat` 加到 `sys.path`）
    :return: (bool, list[str]), ``(ok, missing_names)``
    """
    if names is None:
        return True, []
    # `from X import *` 里的 `*` 不是可核对的符号：没有具名符号就跳过
    names = [name for name in names if name not in ('*', '')]
    if not names:
        return True, []
    if module.split('.')[0] in CST_MODULES:
        return True, []                           # CST 的符号不在本仓库核对
    added = [p for p in extra_paths if p and p not in sys.path]
    for path in added:
        sys.path.insert(0, path)
    saved = {name: sys.modules.pop(name, None)
             for name in (module, module.split('.')[0])}
    try:
        import warnings
        with warnings.catch_warnings():
            # 旧名会按设计发 FutureWarning —— 审计里不必刷屏
            warnings.simplefilter('ignore')
            obj = importlib.import_module(module)
    except Exception as exc:                      # noqa: BLE001
        return False, [f'<导入失败 {type(exc).__name__}: {exc}>']
    finally:
        for path in added:
            try:
                sys.path.remove(path)
            except ValueError:                    # pragma: no cover
                pass
        # 旧名解析出来的模块不要留在缓存里（它转发的是新包，但名字是旧的）
        for name, original in saved.items():
            if original is not None and name.split('.')[0] in COMPAT_NAMES:
                sys.modules[name] = original
            elif original is None and name.split('.')[0] in COMPAT_NAMES:
                sys.modules.pop(name, None)
    missing = [name for name in names if not hasattr(obj, name)]
    return not missing, missing


# ============================================================
# 审计
# ============================================================

def iter_notebooks(src_root: str):
    for dirpath, _dirnames, filenames in os.walk(src_root):
        for filename in sorted(filenames):
            if filename.endswith('.ipynb'):
                yield os.path.join(dirpath, filename)


def audit(src_root: str):
    """
    扫一遍源目录，返回审计结果。

    ⚠️ **按完整模块名统计**（`cst_solver` 与 `cst_solver.result` 分开算）——
    第一版按顶层包名合并，结果把「从哪个子模块取哪个名字」混在一起，
    一个子模块整体不存在（`ModuleNotFoundError`）反而被跳过，漏掉了真缺口。

    :param src_root: str, notebook 根目录
    :return: dict，含 ``notebooks`` / ``per_module`` / ``symbol_gaps``
    """
    per_module = OrderedDict()
    notebook_count = 0
    for path in iter_notebooks(src_root):
        notebook_count += 1
        rel = os.path.relpath(path, src_root)
        try:
            text = notebook_text(path)
        except OSError as exc:                    # pragma: no cover - 文件系统相关
            per_module.setdefault('__read_error__', {}).setdefault(
                'notebooks', []).append(f'{rel}: {exc}')
            continue
        for ref in parse_imports(text):
            module = ref['module']
            entry = per_module.setdefault(module, {
                'kind': classify(module), 'top': module.split('.')[0],
                'names': set(), 'notebooks': []})
            if ref['names']:
                entry['names'].update(ref['names'])
            if rel not in entry['notebooks']:
                entry['notebooks'].append(rel)

    symbol_gaps = []
    for module, entry in per_module.items():
        if module == '__read_error__' or entry['kind'] not in ('current', 'legacy',
                                                               'migrated'):
            continue
        top = entry['top']
        migrated = MIGRATED_MODULES.get(module) or MIGRATED_MODULES.get(top)
        if entry['kind'] == 'migrated' and migrated:
            # 旧名已不在仓库里，改为核对**等价实现**是否真的提供同样的 API
            target = migrated['target']
            ok, missing = resolve_symbols(target, list(migrated['names']))
            if not ok:
                symbol_gaps.append({'module': f'{module} → {target}',
                                    'missing': missing,
                                    'notebooks': entry['notebooks'][:3]})
            continue
        extra = (COMPAT_DIR,) if entry['kind'] == 'legacy' else ()
        ok, missing = resolve_symbols(module, sorted(entry['names']),
                                      extra_paths=extra)
        if not ok:
            symbol_gaps.append({'module': module, 'missing': missing,
                                'notebooks': entry['notebooks'][:3]})
    return {'src_root': src_root, 'notebooks': notebook_count,
            'per_module': per_module, 'symbol_gaps': symbol_gaps}


def summarize(report):
    """把审计结果压成计数（按**顶层**模块归类）。"""
    kind_by_top = {}
    for module, entry in report['per_module'].items():
        if 'kind' not in entry or module == '__read_error__':
            continue
        kind_by_top.setdefault(entry['top'], entry['kind'])
    counts = OrderedDict((kind, 0) for kind in
                         ('current', 'legacy', 'migrated', 'cst', 'stdlib',
                          'third-party', 'unknown'))
    for kind in kind_by_top.values():
        counts[kind] += 1
    tops = {kind: sorted(top for top, k in kind_by_top.items() if k == kind)
            for kind in counts}
    # ⚠️ 迁移条目按**完整模块名**列（`cst_solver.result` 这种子模块级迁移的顶层包
    #    仍是 `current`，只按顶层归类会漏报）
    migrated = sorted(module for module, entry in report['per_module'].items()
                      if entry.get('kind') == 'migrated')
    return {'counts': counts, 'unknown': tops['unknown'], 'legacy': tops['legacy'],
            'migrated': migrated, 'symbol_gaps': report['symbol_gaps']}


# ============================================================
# 报告
# ============================================================

def render_markdown(report, summary) -> str:
    """生成 markdown 报告（给 `docs/guides/`）。"""
    lines = ['# 旧 notebook 导入兼容审计', '',
             f'- 源目录：`{report["src_root"]}`',
             f'- `.ipynb` 总数：**{report["notebooks"]}**',
             '- 方式：只解析 `.ipynb` 的 code cell 源码（去 IPython 魔法后 `ast` 解析），'
             '**不执行**任何单元格；对 `current`/`legacy` 的导入逐个符号核对。',
             f'- 生成：`python scripts/check_notebook_imports.py`', '',
             '## 1. 分类汇总', '',
             '| 类别 | 顶层模块数 |', '|---|---|']
    for kind, count in summary['counts'].items():
        lines.append(f'| `{kind}` | {count} |')
    lines += ['', '## 2. 逐个模块', '',
              '| 模块 | 类别 | 用到的 notebook 数 | 取用的名字 |', '|---|---|---|---|']
    ordered = sorted(report['per_module'].items(),
                     key=lambda kv: (kv[1].get('kind', 'zz'), kv[0]))
    for module, entry in ordered:
        if module == '__read_error__':
            continue
        names = ', '.join(f'`{n}`' for n in sorted(entry['names'])[:6]) or '（`import X`）'
        if len(entry['names']) > 6:
            names += ' …'
        lines.append(f"| `{module}` | `{entry.get('kind')}` | "
                     f"{len(entry['notebooks'])} | {names} |")

    lines += ['', '## 3. 缺口与等价实现', '']
    if summary['migrated']:
        lines += ['### 3.1 旧名已迁移（改一行导入即可，不必找回模块）', '',
                  '| 旧写法 | 等价实现 | 改成 |', '|---|---|---|']
        for module in summary['migrated']:
            info = MIGRATED_MODULES[module]
            alias = info.get('alias_to') or ''
            if alias:
                replacement = (f"`from {'.'.join(info['target'].split('.')[:-1])} "
                               f"import {info['target'].split('.')[-1]} as {alias}`")
                old = f'`import {module} as {alias}`'
            else:
                replacement = f"`from {info['target']} import {module.split('.')[-1]}`"
                old = f'`from {module} import {module.split(".")[-1]}`'
            lines.append(f'| {old} | `{info["target"]}` | {replacement} |')
        for module in summary['migrated']:
            lines.append('')
            lines.append(f"> `{module}`：{MIGRATED_MODULES[module]['note']}")
            used = MIGRATED_MODULES[module].get('notebooks') or ()
            if used:
                lines.append('> 用到的 notebook：' + '、'.join(f'`{n}`' for n in used))
    lines += ['', '### 3.2 仍未定位的模块', '']
    if summary['unknown']:
        lines += ['| 模块 | 状态 |', '|---|---|']
        for module in summary['unknown']:
            lines.append(f"| `{module}` | {KNOWN_MISSING.get(module, '**未交代**')} |")
    else:
        lines.append('（没有未交代的模块）')
    if summary['symbol_gaps']:
        lines += ['', '符号级缺口：', '', '| 模块 | 缺失符号 | 例 |', '|---|---|---|']
        for gap in summary['symbol_gaps']:
            lines.append(f"| `{gap['module']}` | `{gap['missing']}` | "
                         f"{gap['notebooks'][0] if gap['notebooks'] else ''} |")
    lines += ['', '## 4. 怎么让旧 notebook 继续跑', '',
              '旧名（`tri_lib` / `hexlib`）由 `archive/compat/` 下的兼容入口转发到新包。'
              '在 notebook 开头加一行即可（**不必改 notebook 正文里的其它代码**）：', '',
              '```python',
              'import sys',
              r"sys.path.append(r'D:\成电博士生涯\自动建模算法尝试\TPC\archive\compat')",
              'import tri_lib   # 旧名仍可用，会发 FutureWarning',
              '```',
              '',
              '已迁移到新包、又不想改调用代码的旧名（如 `metalen`），'
              '把导入行换成等价模块的别名即可（见 §3.1）。', '']
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description='旧 notebook 导入兼容审计')
    parser.add_argument('src', nargs='?', default=SRC_DEFAULT, help='notebook 根目录')
    parser.add_argument('--out', default=OUT_DEFAULT, help='报告输出路径')
    parser.add_argument('--quiet', action='store_true', help='只打印汇总')
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if not os.path.isdir(args.src):
        print(f'源目录不存在：{args.src}（审计需要本机的旧 notebook 目录）')
        return 2

    report = audit(args.src)
    summary = summarize(report)
    print(f'扫了 {report["notebooks"]} 个 notebook，'
          f'{len(report["per_module"])} 个模块（按完整模块名）')
    print('  分类计数（按顶层包）：')
    for kind, count in summary['counts'].items():
        print(f'    {kind:<12} {count}')
    for module in summary['migrated']:
        print(f'  [migrated] {module} → {MIGRATED_MODULES[module]["target"]}'
              f'（改导入行即可）')
    if summary['migrated']:
        print(f'  （迁移条目按完整模块名计：{len(summary["migrated"])} 条；'
              f'上方 migrated 计数按顶层包计）')
    for module in summary['unknown']:
        print(f'  [unknown] {module}：{KNOWN_MISSING.get(module, "未交代！")}')
    for gap in summary['symbol_gaps']:
        print(f'  [gap] {gap["module"]} 缺 {gap["missing"]}')

    if not args.quiet:
        out = os.path.join(_REPO, args.out) if not os.path.isabs(args.out) else args.out
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, 'w', encoding='utf-8') as handle:
            handle.write(render_markdown(report, summary))
        print(f'报告已写出：{out}')

    undeclared = [m for m in summary['unknown'] if m not in KNOWN_MISSING]
    problems = summary['symbol_gaps'] or undeclared
    return 1 if problems else 0


if __name__ == '__main__':
    raise SystemExit(main())
