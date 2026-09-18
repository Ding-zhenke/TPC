# -*- coding: utf-8 -*-
r"""
API 与发行一致性检查（P1）
==========================

检查什么
--------
``docs/next_plan/README.md`` P1 第 5 条要求核对「公开入口、类型存根、文档、
可选依赖及最低 Python 版本」，并「验证安装后的包而非仅源码目录可用」。
本脚本把这些**逐条做成可执行的检查**（而不是靠人读）：

1. **类型存根漂移** —— `*.pyi` 里声明的方法参数名必须与运行时实现一致
   （历史上的真实漂移：`cst_solver/simulation/setup.pyi` 的 `monitor2d`）；
2. **公开入口** —— `cst_solver/__init__.py` 必须显式给出 ``__all__``，
   且其中每个名字都能取到；
3. **打包白名单** —— 仓库里每个可导入的顶层包都要在
   `pyproject.toml` 的 ``packages.find.include`` 里，否则装出来的包会缺东西；
4. **安装态可用** —— 用 ``importlib.metadata`` 确认发行已安装、版本与
   pyproject 一致，并**从 site-packages 之外的 cwd** 导入一次（验证装的是包，
   不是当前目录的源码）；
5. **离线诊断入口** —— ``python -m cst_solver doctor`` 能给出 JSON 且不启动 CST。
6. **MCP 写入口纪律** —— P1「MCP 写入口接入校验层」的要求做成静态检查：
   会改工程状态的工具必须经共用运行服务提交，且 `cst_mcp/` 里不得出现 CST 原语
   或第二套校验规则（详见 `cst_mcp/tools.py` 的 ``WRITE_TOOLS`` 注释）。

用法::

    python scripts/check_api_consistency.py          # 打印报告，失败返回码 1
    pytest tests/test_api_consistency.py             # 同一套检查进 CI

@author: PC
"""

import ast
import glob
import inspect
import json
import os
import re
import subprocess
import sys
import tomllib
import warnings
from typing import Dict, List, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

#: 允许存在的存根/实现不一致（每条都必须写明原因；空字典表示零容忍）
STUB_EXCEPTIONS: Dict[str, str] = {}


def _rel(path: str) -> str:
    """仓库内路径给相对形式；跨盘符（例如临时目录在 C:）时退回绝对路径，不抛异常。"""
    try:
        return os.path.relpath(path, ROOT).replace('\\', '/')
    except ValueError:
        return os.path.abspath(path).replace('\\', '/')


# ============================================================
# 1. 存根漂移
# ============================================================

def _stub_functions(path: str) -> Dict[Tuple[str, str], List[str]]:
    """``{(类名, 方法名): [参数名, ...]}``；类外的函数类名为 ``''``。"""
    tree = ast.parse(open(path, encoding='utf-8').read(), filename=path)
    found: Dict[Tuple[str, str], List[str]] = {}

    def visit(node, class_name: str = ''):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                visit(child, child.name)
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args = child.args
                names = [a.arg for a in args.posonlyargs + args.args]
                if args.vararg:
                    names.append('*' + args.vararg.arg)
                names += [a.arg for a in args.kwonlyargs]
                if args.kwarg:
                    names.append('**' + args.kwarg.arg)
                found[(class_name, child.name)] = names
    visit(tree)
    return found


def _runtime_function_names(cls) -> Dict[str, List[str]]:
    """运行时类的可见方法 → 参数名列表（``self`` 已去掉）。"""
    import inspect

    out: Dict[str, List[str]] = {}
    for name, member in inspect.getmembers(cls, callable):
        if name.startswith('__'):
            continue
        try:
            params = list(inspect.signature(member).parameters)
        except (TypeError, ValueError):
            continue
        out[name] = [p for p in params if p != 'self']
    return out


def _normalize_params(params: List[str]) -> List[str]:
    """去掉 ``self`` 与 ``*``/``**`` 前缀，便于两侧比较。"""
    return [p.lstrip('*') for p in params if p != 'self']


def check_stub_drift() -> List[str]:
    """
    比对 ``.pyi`` 与运行时的参数名。

    :return: list[str], 问题描述（空列表 = 通过）
    """
    import cst_solver

    problems: List[str] = []
    stubs = [os.path.join(ROOT, 'cst_solver', 'setup.pyi'),
             os.path.join(ROOT, 'cst_solver', 'simulation', 'setup.pyi')]
    for stub in stubs:
        if not os.path.exists(stub):
            problems.append(f'{_rel(stub)} 不存在（存根缺失）')
            continue
        declared = _stub_functions(stub)
        runtime = _runtime_function_names(cst_solver.setup)
        for (class_name, method), stub_params in sorted(declared.items()):
            target = runtime.get(method)
            if target is None:
                continue                       # 别名/内部方法，逐条核对成本高
            stub_names = _normalize_params(stub_params)
            impl_names = _normalize_params(target)
            if set(stub_names) != set(impl_names):
                key = f'{_rel(stub)}::{class_name}.{method}'
                if key in STUB_EXCEPTIONS:
                    continue
                problems.append(
                    f'{key} 参数名与实现不一致：存根 {stub_names} vs 实现 {impl_names}')
    return problems


# ============================================================
# 2. 公开入口
# ============================================================

def check_public_surface() -> List[str]:
    """``cst_solver`` 必须有 ``__all__``，且其中每个名字可取到。"""
    import cst_solver

    problems: List[str] = []
    exported = getattr(cst_solver, '__all__', None)
    if not exported:
        problems.append('cst_solver/__init__.py 没有 __all__：公开入口没有显式声明')
        return problems
    for name in exported:
        if not hasattr(cst_solver, name):
            problems.append(f'cst_solver.__all__ 里的 {name!r} 取不到')
    return problems


# ============================================================
# 3. 打包白名单
# ============================================================

def _pyproject() -> dict:
    with open(os.path.join(ROOT, 'pyproject.toml'), 'rb') as handle:
        return tomllib.load(handle)


def _top_level_packages() -> List[str]:
    """仓库里带 ``__init__.py`` 的顶层包（排除测试与归档目录）。"""
    skip = {'archive', 'tests', 'scripts', 'docs', 'assets', '.git'}
    found = []
    for name in sorted(os.listdir(ROOT)):
        path = os.path.join(ROOT, name)
        if (name not in skip and os.path.isdir(path)
                and os.path.exists(os.path.join(path, '__init__.py'))):
            found.append(name)
    return found


def check_packaging() -> List[str]:
    """每个顶层包都要在 ``packages.find.include`` 里；py.typed 要有 package-data。"""
    config = _pyproject()
    include = config.get('tool', {}).get('setuptools', {}).get(
        'packages', {}).get('find', {}).get('include', [])
    problems: List[str] = []
    for package in _top_level_packages():
        if not any(pattern.rstrip('*') and package.startswith(pattern.rstrip('*'))
                   or pattern == package for pattern in include):
            problems.append(
                f'顶层包 {package} 不在 pyproject 的 packages.find.include 里：'
                f'装出来的包会缺它')
    data = config.get('tool', {}).get('setuptools', {}).get('package-data', {})
    if 'cst_solver/py.typed' and 'cst_solver' not in data:
        problems.append('pyproject 缺少 cst_solver 的 package-data（py.typed/*.pyi）')
    return problems


# ============================================================
# 4. 安装态
# ============================================================

def check_installed_distribution() -> List[str]:
    """
    发行已安装、版本与 pyproject 一致、仓库外能导入**全部**顶层包。

    安装模式分三类（都要能识别，否则会误报）：
    * ``pep660-editable``：PEP 660 可编辑安装（``direct_url.json`` 里 ``dir_info.editable``）；
    * ``legacy-develop``：老式开发安装（发行元数据是源码树里的 ``*.egg-info``）；
    * ``regular``：常规 wheel 安装（此时导入路径必须在 site-packages 里）。
    """
    problems: List[str] = []
    expected = _pyproject()['project']['version']
    from importlib.metadata import PackageNotFoundError, distribution
    try:
        dist = distribution('tpc-cst')
    except PackageNotFoundError:
        return ['tpc-cst 未安装（pip install -e . 之后才能核对安装态）']
    except Exception as exc:                          # noqa: BLE001
        return [f'无法查询发行信息：{exc!r}']

    if dist.version != expected:
        problems.append(f'安装版本 {dist.version} 与 pyproject 的 {expected} 不一致')

    mode = 'regular'
    dist_path = str(getattr(dist, '_path', '') or '')
    if dist_path.endswith('.egg-info'):
        mode = 'legacy-develop'
    try:
        direct = dist.read_text('direct_url.json')
        if direct:
            info = json.loads(direct)
            if info.get('dir_info', {}).get('editable'):
                mode = 'pep660-editable'
    except Exception:                                 # noqa: BLE001
        pass
    editable = mode in ('legacy-develop', 'pep660-editable')
    print(f'        安装模式：{mode}，版本 {dist.version}')

    # 顶层包必须都能在**仓库外**导入：新增顶层包后忘记重装就是在这里暴露的
    modules = ('cst_solver', 'mesh_grid', 'topo_modeler', 'topo_templates',
               'tpc_toolkit', 'tpc_service')
    script = ('import json, os, importlib\n'
              'out = {}\n'
              'for name in %r:\n'
              '    try:\n'
              '        mod = importlib.import_module(name)\n'
              '        out[name] = os.path.dirname(getattr(mod, "__file__", "") or "")\n'
              '    except Exception as exc:\n'
              '        out[name] = "ERROR: %%s: %%s" %% (type(exc).__name__, exc)\n'
              'print(json.dumps(out))\n' % (modules,))
    proc = subprocess.run([sys.executable, '-c', script], capture_output=True,
                          text=True, cwd=os.path.dirname(ROOT))
    if proc.returncode != 0:
        problems.append(f'仓库外导入顶层包失败：{proc.stderr.strip()[:300]}')
        return problems
    locations = json.loads(proc.stdout.strip().splitlines()[-1])
    for name, location in locations.items():
        if location.startswith('ERROR'):
            problems.append(
                f'仓库外导入 {name} 失败（{location[7:]}）—— 新增顶层包后需要重新 '
                f'`pip install -e .`，否则可编辑安装的映射里没有它')
    base_location = locations.get('cst_solver', '')
    if not editable and base_location and 'site-packages' not in base_location:
        problems.append(
            f'非可编辑安装下，仓库外导入却拿到 {base_location}；打包或安装方式有问题')
    return problems


# ============================================================
# 5. 离线诊断入口
# ============================================================

def check_doctor_entry() -> List[str]:
    """``python -m cst_solver doctor`` 必须是 JSON 且不启动 CST。"""
    proc = subprocess.run([sys.executable, '-m', 'cst_solver', 'doctor'],
                          capture_output=True, text=True, cwd=ROOT)
    try:
        # doctor 输出是**多行**的缩进 JSON，必须整体解析（不能只取最后一行）
        payload = json.loads(proc.stdout)
    except Exception as exc:                          # noqa: BLE001
        return [f'doctor 输出不是 JSON（{exc!r}）：stdout={proc.stdout[:200]!r}']
    problems: List[str] = []
    if 'status' not in payload:
        problems.append('doctor 报告缺少 status 字段')
    if payload.get('status') not in ('not_probed', 'importable', 'unavailable',
                                     'configuration_error'):
        problems.append(f'doctor status 取值意外：{payload.get("status")!r}')
    return problems


# ============================================================
# 6. MCP 写入口纪律（P1「MCP 写入口接入校验层」）
# ============================================================

#: 一旦在 MCP 层出现，就说明有人绕开共用能力自己下发/读取 CST
MCP_FORBIDDEN_PRIMITIVES = ('add_to_history', 'cst.interface', 'cst.results',
                            'model3d.', 'full_history_rebuild', 'StoreParameter')

#: 也不得自带一套「非法字符/非法名字」规则（应调用 `cst_solver.expressions`）
MCP_FORBIDDEN_VALIDATION = ('invalid_char', 'illegal_char', 'forbidden_char',
                            'invalid_name')


def _mcp_src_dir() -> str:
    return os.path.join(ROOT, 'integrations', 'cst-mcp', 'src')


def check_mcp_write_guard() -> List[str]:
    """
    MCP 写入口必须经共用运行服务与共用校验层，且不得重写 CST 原语/校验规则。

    见 `integrations/cst-mcp/src/cst_mcp/tools.py` 的 ``WRITE_TOOLS`` 说明；
    运行期由 `integrations/cst-mcp/tests/test_write_guard.py` 用替身把关。
    """
    src = _mcp_src_dir()
    package = os.path.join(src, 'cst_mcp')
    if not os.path.isdir(package):
        return [f'找不到 MCP 源码目录：{_rel(package)}']
    problems: List[str] = []

    if src not in sys.path:
        sys.path.insert(0, src)
    try:
        from cst_mcp import tools as mcp_tools
    except Exception as exc:                          # noqa: BLE001
        return [f'导入 cst_mcp.tools 失败：{type(exc).__name__}: {exc}']

    write = set(getattr(mcp_tools, 'WRITE_TOOLS', ()))
    read = set(getattr(mcp_tools, 'READ_TOOLS', ()))
    names = set(mcp_tools.tool_names())
    if not write:
        problems.append('cst_mcp.tools.WRITE_TOOLS 为空 —— 写入口必须显式归类')
    if write & read:
        problems.append(f'工具同时被标为写与只读：{sorted(write & read)}')
    unclassified = names - (write | read)
    if unclassified:
        problems.append(f'未归类的工具（新增工具必须显式归类）：{sorted(unclassified)}')

    # 写入口必须走 run service：源码里要出现 runtime.get_service()
    for name in sorted(write):
        handler = mcp_tools.HANDLERS.get(name)
        if handler is None:
            problems.append(f'写入口 {name} 没有对应 handler')
            continue
        try:
            source = inspect.getsource(handler)
        except OSError as exc:                        # pragma: no cover
            problems.append(f'读不到 {name} 的源码：{exc}')
            continue
        if 'get_service' not in source:
            problems.append(f'写入口 {name} 没有经 runtime.get_service() 提交任务 —— '
                            'MCP 层不得自己开 CST')

    # 静态：不得出现 CST 原语或第二套校验规则（整行注释里提到不算）
    for filename in sorted(os.listdir(package)):
        if not filename.endswith('.py'):
            continue
        path = os.path.join(package, filename)
        with open(path, encoding='utf-8') as handle:
            code = '\n'.join(line for line in handle
                             if not line.lstrip().startswith('#'))
        for token in MCP_FORBIDDEN_PRIMITIVES:
            if token in code:
                problems.append(f'{_rel(path)} 出现 CST 原语 {token!r}：'
                                'MCP 层必须复用共用能力')
        for token in MCP_FORBIDDEN_VALIDATION:
            if token in code:
                problems.append(f'{_rel(path)} 疑似自带校验规则 {token!r}：'
                                '必须调用 cst_solver.expressions')
    return problems


# ============================================================
# 7. 错误码表与代码的一致性
# ============================================================

#: 这些构造函数/辅助函数的**第一个位置参数**是错误码
_CODE_HELPERS = ('structured_error', 'error_dict', 'fail_result', 'error_payload',
                 'ServiceError', 'ToolError', '_error')
# ⚠️ `ConfigError(message, code='...')` 是**消息在前**，码只能从 `code=` 关键字取 ——
#    第一版把它按「首参即码」处理，于是把一堆错误消息当成了错误码。

#: `record_failure(operation, code, message, ...)` 的码在**第二个**位置
_CODE_HELPER_INDEX = {'record_failure': 1}

#: 会承载错误码的变量名（赋值形式：`code = 'tool_failed'`）
_CODE_VARS = ('code', 'error_code')

#: 码表命名惯例：`ERROR_CODES` / `RUN_ERROR_CODES` / `TOOL_ERROR_CODES` …
_VOCAB_SUFFIX = 'ERROR_CODES'


def _iter_py_files(roots=None):
    """
    仓库里需要扫描的 Python 源码（库包 + MCP 集成源），跳过 tests/缓存。

    :param roots: 序列 可选, 覆盖默认扫描根（测试用临时目录时需要）
    """
    if roots is None:
        roots = [os.path.join(ROOT, name) for name in
                 ('cst_solver', 'mesh_grid', 'topo_modeler', 'topo_templates',
                  'tpc_toolkit', 'tpc_service', 'scripts',
                  os.path.join('integrations', 'cst-mcp', 'src', 'cst_mcp'))]
    for root in roots:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames
                           if d not in ('__pycache__', 'tests', '.pytest_cache')]
            for filename in sorted(filenames):
                if filename.endswith('.py'):
                    yield os.path.join(dirpath, filename)


def _scan_error_codes(roots=None):
    """
    扫出「代码里实际用到的错误码」与「声明的码表」。

    :param roots: 序列 可选, 扫描根（默认见 :func:`_iter_py_files`）
    :return: (dict[code -> {文件}], dict[表名 -> (文件, [码])])
    """
    used: Dict[str, set] = {}
    vocab: Dict[str, tuple] = {}

    def _add(code: str, path: str) -> None:
        used.setdefault(code, set()).add(_rel(path))

    for path in _iter_py_files(roots):
        try:
            with open(path, encoding='utf-8') as handle:
                source = handle.read()
            with warnings.catch_warnings():
                # 仓库里有 Windows 路径字面量（`'D:\...'`），ast.parse 会为无效转义序列
                # 发 DeprecationWarning —— 与本检查无关，别让它刷屏
                warnings.simplefilter('ignore')
                tree = ast.parse(source)
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            # ① `NAME_ERROR_CODES = (...)` 形式的码表
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if (isinstance(target, ast.Name)
                            and target.id.endswith(_VOCAB_SUFFIX)
                            and isinstance(node.value, (ast.Tuple, ast.List))):
                        codes = [el.value for el in node.value.elts
                                 if isinstance(el, ast.Constant)
                                 and isinstance(el.value, str)]
                        vocab[target.id] = (_rel(path), codes)
                    # ③ `code = 'xxx'` 赋值形式
                    if isinstance(target, ast.Name) and target.id in _CODE_VARS \
                            and isinstance(node.value, ast.Constant) \
                            and isinstance(node.value.value, str):
                        _add(node.value.value, path)
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, 'attr', getattr(node.func, 'id', ''))
            # ⑤ `getattr(exc, 'code', 'expression_syntax_error')` 形式的兜底码
            #    （实测 `cst_solver/expressions.py` 就是这么产码的）
            if name == 'getattr' and len(node.args) >= 3:
                key, default = node.args[1], node.args[2]
                if isinstance(key, ast.Constant) and key.value in _CODE_VARS \
                        and isinstance(default, ast.Constant) \
                        and isinstance(default.value, str):
                    _add(default.value, path)
            # ② 构造函数/辅助函数的码参数
            index = _CODE_HELPER_INDEX.get(name)
            if index is None and name in _CODE_HELPERS:
                index = 0
            if index is not None and len(node.args) > index:
                arg = node.args[index]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    _add(arg.value, path)
            # ④ 关键字形式 `code='xxx'`（任意函数）
            for keyword in node.keywords:
                if keyword.arg in _CODE_VARS \
                        and isinstance(keyword.value, ast.Constant) \
                        and isinstance(keyword.value.value, str):
                    _add(keyword.value.value, path)
    return used, vocab


def check_error_codes(roots=None) -> List[str]:
    """
    代码里用到的每个错误码，都必须出现在某个 ``*_ERROR_CODES`` 表里。

    为什么需要：错误码是**跨层契约**（`cst_solver` → `tpc_service` → `cst_mcp`
    原样透传，不重编号）。手写字符串最容易出现「拼错一个字母」「加了新码忘了登记」，
    而调用方按码分支处理时完全看不出来。本项把它们钉住。

    2026-09-17 首次运行就抓到三处真实漂移：
    `ERROR_CODES` 缺 `cancelled_before_start` / `service_restarted`，
    `TOOL_ERROR_CODES` 缺 `tool_failed`（`dispatch()` 的兜底码）。

    :param roots: 序列 可选, 扫描根（测试用）
    """
    used, vocab = _scan_error_codes(roots)
    declared = set()
    for _name, (_path, codes) in vocab.items():
        declared.update(codes)
    problems: List[str] = []
    if not vocab:
        return ['没有扫描到任何 `*_ERROR_CODES` 表 —— 检查规则失效了']
    for code in sorted(used):
        if code not in declared:
            files = ', '.join(sorted(used[code])[:3])
            problems.append(f'错误码 {code!r} 未登记在任何 `*_ERROR_CODES` 表里（{files}）')
    # 声明了但没用到的码不算错（可能是给调用方看的保留码），但要在报告里可见
    unused = sorted(declared - set(used))
    if unused:
        print(f'        （提示）声明但当前未产出的码：{unused}')
    return problems


# ============================================================
# 8. 文档里的命令还能不能跑
# ============================================================

#: `python scripts/<name>.py`
_DOC_SCRIPT_RE = re.compile(r'python\s+(scripts[\\/][\w\.\-]+\.py)')

#: `pytest <path>` / `python -m pytest <path>`：只认**带路径分隔符或 .py** 的 token,
#: 否则会把「pytest 入口」「pytest 自动发现」这类正文当成路径（实测过的误报）
_DOC_PYTEST_RE = re.compile(r'pytest\s+(?:-[\w\-]+\s+)*([\w\.\-/\\]+(?:\.py)?)')

#: `pip install -e <path>`
_DOC_PIP_RE = re.compile(r'pip\s+install\s+-e\s+([\w\.\-/\\]+)')

#: 同一行里命令可能先 `cd <目录> &&`，后面的路径就相对该目录
_DOC_CD_RE = re.compile(r'cd\s+([\w\.\-/\\]+)\s*&&')


def _doc_base_dir(line: str) -> str:
    """
    取这一行命令里 `cd <目录> &&` 指定的基准目录（没有则返回仓库根）。

    :param line: str, 命令行
    :return: str, 相对仓库根的基准目录
    """
    match = _DOC_CD_RE.search(line)
    return match.group(1).replace('/', os.sep) if match else ''


def _doc_files():
    """参与检查的 markdown（docs/ + skills/ + 根 README + 集成包文档）。"""
    patterns = ('docs/**/*.md', 'skills/**/*.md', '*.md', 'integrations/**/*.md')
    found = set()
    for pattern in patterns:
        found.update(glob.glob(os.path.join(ROOT, pattern), recursive=True))
    return sorted(found)


def check_doc_commands() -> List[str]:
    """
    文档里写的 `python scripts/xxx.py` / `pytest 路径` / `pip install -e 路径`
    必须指向**真实存在**的文件。

    为什么需要：这类引用**不是 markdown 链接**（`check_md_links.py` 管不到），
    脚本改名/移动后文档会静默烂掉 —— 而文档正是使用者照着敲的地方。
    本轮实测（2026-09-17）没有发现坏引用，本项作为**防回归**门存在。
    """
    problems: List[str] = []
    checked = 0
    for path in _doc_files():
        try:
            text = open(path, encoding='utf-8', errors='replace').read()
        except OSError:
            continue
        for match in _DOC_SCRIPT_RE.finditer(text):
            checked += 1
            target = match.group(1).replace('/', os.sep)
            if not os.path.isfile(os.path.join(ROOT, target)):
                problems.append(f'{_rel(path)} 引用不存在的脚本：{match.group(1)}')
        for match in _DOC_PYTEST_RE.finditer(text):
            token = match.group(1).strip('`')
            if not (os.sep in token or token.endswith('.py')):
                continue                          # 正文里的「pytest 入口」不是路径
            checked += 1
            line = text[text.rfind('\n', 0, match.start()) + 1:
                        text.find('\n', match.start())]
            base = os.path.join(ROOT, _doc_base_dir(line))
            if not os.path.exists(os.path.join(base, token.replace('/', os.sep))):
                problems.append(f'{_rel(path)} 引用不存在的 pytest 路径：{token}')
        for match in _DOC_PIP_RE.finditer(text):
            checked += 1
            target = match.group(1).replace('/', os.sep)
            if not os.path.exists(os.path.join(ROOT, target)):
                problems.append(f'{_rel(path)} 引用不存在的安装路径：{match.group(1)}')
    if not checked:
        problems.append('没有扫描到任何文档命令 —— 检查规则可能失效了')
    return problems


def check_support_matrix() -> List[str]:
    """
    支持矩阵必须与**本机实际检测到的** CST 版本 / 解释器 ABI 一致，且不许偷偷
    把未验证的能力写成已验证。

    为什么需要（计划 P1「已验证 CST/Python 组合的公布」）：
    文档写「已验证 CST 2026 + Python 3.11.7」，而机器可能已经换成别的版本 ——
    那时矩阵就是**过期的承诺**。这里把「本机检测」（`describe_interface_abi()`，
    离线、只读安装目录）与文档对上：

    * 本机**没装 CST** ⇒ 跳过（返回空，不阻塞其它机器/CI）；
    * 装了 ⇒ `install_path` 里的版本号与 `interpreter_abi`（如 `cp311`）
      必须出现在 `docs/SUPPORT_MATRIX.md` 里；
    * 矩阵里必须**明确写着**求解（`solve`/`study`）未验证 —— 这是本仓库最容易被
      "顺手说成已完成"的一条（求解要 5300 s CPU，没人会顺手跑）。
    """
    problems: List[str] = []
    matrix = os.path.join(ROOT, 'docs', 'SUPPORT_MATRIX.md')
    if not os.path.isfile(matrix):
        return [f'缺少支持矩阵文档：{_rel(matrix)}']
    text = open(matrix, encoding='utf-8').read()

    try:
        from cst_solver.environment import describe_interface_abi
        abi = describe_interface_abi()
    except Exception as exc:                            # noqa: BLE001
        print(f'        (跳过：读不到本机 CST 信息：{type(exc).__name__}: {exc})')
        return problems

    install = abi.get('install_path') or ''
    if not install:
        print('        (跳过：本机没检测到 CST 安装)')
        return problems

    version = os.path.basename(install.rstrip('\\/')) or install
    years = re.findall(r'\d{4}', version)
    if years and not any(year in text for year in years):
        problems.append(
            f'本机 CST 是 {version!r}，但支持矩阵里没有出现年份 {years} —— '
            f'换版本后必须重新验证并更新矩阵')
    interpreter_abi = abi.get('interpreter_abi') or ''
    if interpreter_abi and interpreter_abi not in text:
        problems.append(
            f'本机解释器 ABI 是 {interpreter_abi!r}，支持矩阵里没有它 —— '
            f'请补一行（新组合未验证）')

    # 「未验证」的诚实口径：求解必须被明确列为未验证
    if 'solve' not in text or '未验证' not in text:
        problems.append('支持矩阵没有明确写「求解未验证」的口径')
    else:
        solve_rows = [line for line in text.splitlines()
                      if 'solve' in line and line.lstrip().startswith('|')]
        if not solve_rows or not any('未验证' in line for line in solve_rows):
            problems.append('支持矩阵里求解那张表没有写「未验证」')
    return problems


CHECKS = (
    ('stub-drift', '类型存根 vs 实现参数名', check_stub_drift),    ('public-surface', 'cst_solver 公开入口（__all__）', check_public_surface),
    ('packaging', 'pyproject 打包白名单与 package-data', check_packaging),
    ('installed', '安装态与发行版本', check_installed_distribution),
    ('doctor', 'python -m cst_solver doctor', check_doctor_entry),
    ('mcp-write-guard', 'MCP 写入口经共用服务与共用校验层', check_mcp_write_guard),
    ('error-codes', '错误码：用到的码必须已在某个 *_ERROR_CODES 表里', check_error_codes),
    ('doc-commands', '文档里的命令指向真实存在的脚本/路径', check_doc_commands),
    ('support-matrix', '支持矩阵 vs 本机检测到的 CST/解释器', check_support_matrix),
)


def run_all(verbose: bool = True) -> Dict[str, List[str]]:
    """跑全部检查，返回 ``{检查名: [问题, ...]}``。"""
    results: Dict[str, List[str]] = {}
    for name, title, fn in CHECKS:
        try:
            problems = fn()
        except Exception as exc:                      # noqa: BLE001
            problems = [f'检查本身出错：{type(exc).__name__}: {exc}']
        results[name] = problems
        if verbose:
            mark = 'OK  ' if not problems else 'FAIL'
            print(f'[{mark}] {name:<16} {title}')
            for problem in problems:
                print(f'        - {problem}')
    return results


def main() -> int:
    results = run_all(verbose=True)
    failed = sum(1 for problems in results.values() if problems)
    print(f'\n{len(CHECKS) - failed}/{len(CHECKS)} 项通过')
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
