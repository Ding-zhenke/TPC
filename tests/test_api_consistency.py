# -*- coding: utf-8 -*-
"""
API 与发行一致性测试（P1）
==========================

把 `scripts/check_api_consistency.py` 的检查接进 pytest，让
「类型存根漂移 / 公开入口没声明 / 打包白名单缺包 / 安装态不一致 / doctor 不输出 JSON」
在 CI 里就失败，而不是等到用户装完包才发现。

⚠️ 这些检查发现过真实问题（`cst_solver/setup.pyi` 的 `rotation` 少了
`object`/`auto_destination`；`simulation/setup.pyi` 的 `monitor2d` 多了
`field_type`/`subvolume`），所以它们不是形式主义。

运行方式::

    pytest tests/test_api_consistency.py -v
"""

import importlib.util
import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

_SCRIPT = os.path.join(ROOT, 'scripts', 'check_api_consistency.py')
_spec = importlib.util.spec_from_file_location('check_api_consistency', _SCRIPT)
checker = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(checker)


@pytest.mark.parametrize('name,title,fn', checker.CHECKS,
                         ids=[c[0] for c in checker.CHECKS])
def test_consistency_check(name, title, fn, capsys):
    """每项检查都必须通过；失败时把问题逐条列出来。"""
    problems = fn()
    capsys.readouterr()
    assert not problems, f'[{name}] {title}：\n  - ' + '\n  - '.join(problems)


def test_stub_drift_detects_a_real_regression(monkeypatch):
    """反向验证：故意改坏一条存根，检查必须报出来。"""
    original = checker._stub_functions

    def fake_stub_functions(path):
        declared = original(path)
        if path.endswith('setup.pyi'):
            declared[('_SolverMixin', 'run')] = ['self', 'totally_bogus_param']
        return declared

    monkeypatch.setattr(checker, '_stub_functions', fake_stub_functions)
    problems = checker.check_stub_drift()
    assert any('run' in p and 'totally_bogus_param' in p for p in problems)


def _matrix_fixture(tmp_path, monkeypatch, text):
    """造一个临时支持矩阵 + 把检查器的 ROOT 指向它，并伪造本机 CST 信息。"""
    docs = tmp_path / 'docs'
    docs.mkdir(parents=True, exist_ok=True)
    (docs / 'SUPPORT_MATRIX.md').write_text(text, encoding='utf-8')
    monkeypatch.setattr(checker, 'ROOT', str(tmp_path))

    def fake_abi():
        return {'install_path': r'C:\SOFTWARE\CST Studio Suite 2026',
                'interpreter_abi': 'cp311', 'abi_match': True}

    monkeypatch.setattr('cst_solver.environment.describe_interface_abi', fake_abi)
    return str(docs / 'SUPPORT_MATRIX.md')


_GOOD_MATRIX = (
    '# 支持矩阵\n\n'
    '| CST | Python |\n|---|---|\n'
    '| CST Studio Suite 2026 | 3.11.7（cp311） |\n\n'
    '| 能力 | 状态 |\n|---|---|\n'
    '| 求解 `solve` | ❌ 未验证 |\n'
)


def test_support_matrix_accepts_a_matching_document(tmp_path, monkeypatch):
    """本机 CST 年份与解释器 ABI 都在文档里、且求解答明未验证 ⇒ 通过。"""
    _matrix_fixture(tmp_path, monkeypatch, _GOOD_MATRIX)
    assert checker.check_support_matrix() == []


def test_support_matrix_flags_a_stale_cst_version(tmp_path, monkeypatch):
    """反向验证：本机换了 CST 版本而文档没跟上，必须报错。"""
    _matrix_fixture(tmp_path, monkeypatch,
                    _GOOD_MATRIX.replace('2026', '2025'))
    problems = checker.check_support_matrix()
    assert any('2026' in p for p in problems), problems


def test_support_matrix_flags_a_missing_interpreter_abi(tmp_path, monkeypatch):
    """反向验证：文档没写本机 ABI（cp311）时必须报错。"""
    _matrix_fixture(tmp_path, monkeypatch, _GOOD_MATRIX.replace('cp311', 'cp310'))
    problems = checker.check_support_matrix()
    assert any('cp311' in p for p in problems), problems


def test_support_matrix_requires_the_solve_caveat(tmp_path, monkeypatch):
    """反向验证：把「求解未验证」悄悄抹掉（例如改成"支持"）必须报错。"""
    _matrix_fixture(tmp_path, monkeypatch,
                    _GOOD_MATRIX.replace('❌ 未验证', '✅ 已验证'))
    problems = checker.check_support_matrix()
    assert any('未验证' in p for p in problems), problems


def test_support_matrix_skips_when_no_cst(tmp_path, monkeypatch):
    """没装 CST 的机器上不能因为这个检查而失败（跳过 + 打印说明）。"""
    _matrix_fixture(tmp_path, monkeypatch, '随便什么内容\n')
    monkeypatch.setattr('cst_solver.environment.describe_interface_abi',
                        lambda: {'install_path': '', 'interpreter_abi': ''})
    assert checker.check_support_matrix() == []


def test_support_matrix_requires_the_document(tmp_path, monkeypatch):
    """文档不存在 ⇒ 直接报缺（不能静默跳过）。"""
    monkeypatch.setattr(checker, 'ROOT', str(tmp_path))
    problems = checker.check_support_matrix()
    assert any('支持矩阵' in p for p in problems)


def test_mcp_write_guard_detects_violations(monkeypatch, tmp_path):
    """
    反向验证：MCP 写入口里出现 CST 原语、或没走 run service，检查必须报出来。

    用临时包替换 `integrations/cst-mcp/src/cst_mcp`，并临时清掉 `cst_mcp*`
    的模块缓存（否则 `from cst_mcp import tools` 会命中真包）。
    """
    src = tmp_path / 'src'
    package = src / 'cst_mcp'
    package.mkdir(parents=True)
    (package / '__init__.py').write_text('', encoding='utf-8')
    (package / 'tools.py').write_text(
        'WRITE_TOOLS = ("build_model",)\n'
        'READ_TOOLS = ()\n'
        '\n'
        'def tool_names():\n'
        '    return ["build_model"]\n'
        '\n'
        'def handle_build_model(arguments):\n'
        '    add_to_history("bad", "VBA")\n'
        '\n'
        'HANDLERS = {"build_model": handle_build_model}\n', encoding='utf-8')

    monkeypatch.setattr(checker, '_mcp_src_dir', lambda: str(src))
    saved = {key: value for key, value in sys.modules.items()
             if key == 'cst_mcp' or key.startswith('cst_mcp.')}
    for key in saved:
        del sys.modules[key]
    saved_path = list(sys.path)
    sys.path.insert(0, str(src))
    try:
        problems = checker.check_mcp_write_guard()
    finally:
        sys.path[:] = saved_path
        for key in [k for k in sys.modules
                    if k == 'cst_mcp' or k.startswith('cst_mcp.')]:
            del sys.modules[key]
        sys.modules.update(saved)

    assert any('add_to_history' in p for p in problems), problems
    assert any('get_service' in p for p in problems), problems


# ============================================================
# 错误码一致性（error-codes）
# ============================================================

def _write_module(tmp_path, name, body):
    package = tmp_path / 'pkg'
    package.mkdir(exist_ok=True)
    (package / name).write_text(body, encoding='utf-8')
    return tmp_path


def test_error_code_scanner_finds_every_production_form(tmp_path):
    """四种产码写法都要被扫到：首参、次参、`code=` 关键字、`getattr` 兜底、赋值。"""
    _write_module(tmp_path, 'producer.py', (
        "ERROR_CODES = ('a_code',)\n"
        "def f(exc):\n"
        "    raise ServiceError('b_code', 'msg')\n"
        "def g():\n"
        "    record_failure('op', 'c_code', 'msg')\n"
        "def h():\n"
        "    raise ConfigError('这是消息，不是码', code='d_code')\n"
        "def i(exc):\n"
        "    code = getattr(exc, 'code', 'e_code')\n"
        "    return code\n"
        "def j():\n"
        "    code = 'f_code'\n"
        "    return code\n"))
    used, vocab = checker._scan_error_codes([str(tmp_path)])
    assert vocab['ERROR_CODES'][1] == ['a_code']
    for expected in ('b_code', 'c_code', 'd_code', 'e_code', 'f_code'):
        assert expected in used, f'{expected} 没被扫到：{sorted(used)}'
    # 消息串绝不能被当成错误码
    assert '这是消息，不是码' not in used


def test_error_codes_check_reports_undeclared_code(tmp_path):
    """反向验证：用了未登记的码，检查必须报出来。"""
    _write_module(tmp_path, 'producer.py', (
        "ERROR_CODES = ('known_code',)\n"
        "def f():\n"
        "    raise ServiceError('typo_code', 'msg')\n"))
    problems = checker.check_error_codes([str(tmp_path)])
    assert any('typo_code' in p for p in problems), problems
    assert not any('known_code' in p for p in problems), problems


def test_error_codes_check_passes_when_code_is_declared(tmp_path):
    """登记的码放行；声明了但没产出的码只提示、不算失败。"""
    _write_module(tmp_path, 'producer.py', (
        "RUN_ERROR_CODES = ('used_code', 'reserved_code')\n"
        "def f():\n"
        "    raise ServiceError('used_code', 'msg')\n"))
    assert checker.check_error_codes([str(tmp_path)]) == []


# ============================================================
# 文档命令一致性（doc-commands）
# ============================================================

def _docs_fixture(tmp_path, monkeypatch, text):
    """造一个临时文档 + 把检查器的 ROOT/文档列表指向它。"""
    (tmp_path / 'scripts').mkdir(exist_ok=True)
    doc = tmp_path / 'NOTES.md'
    doc.write_text(text, encoding='utf-8')
    monkeypatch.setattr(checker, 'ROOT', str(tmp_path))
    monkeypatch.setattr(checker, '_doc_files', lambda: [str(doc)])
    return doc


def test_doc_commands_flags_missing_script(tmp_path, monkeypatch):
    (tmp_path / 'scripts').mkdir()
    (tmp_path / 'scripts' / 'here.py').write_text('# ok', encoding='utf-8')
    _docs_fixture(tmp_path, monkeypatch,
                  'python scripts/here.py\npython scripts/gone.py\n')
    problems = checker.check_doc_commands()
    assert len(problems) == 1 and 'gone.py' in problems[0], problems


def test_doc_commands_flags_missing_pytest_path(tmp_path, monkeypatch):
    (tmp_path / 'scripts').mkdir()
    _docs_fixture(tmp_path, monkeypatch, 'python -m pytest tests/nope.py -q\n')
    problems = checker.check_doc_commands()
    assert len(problems) == 1 and 'tests/nope.py' in problems[0], problems


def test_doc_commands_handles_cd_prefix(tmp_path, monkeypatch):
    """`cd sub && pytest tests/x.py` 里的路径相对 `sub`，不能按仓库根去判。"""
    (tmp_path / 'scripts').mkdir()
    (tmp_path / 'sub' / 'tests').mkdir(parents=True)
    (tmp_path / 'sub' / 'tests' / 'test_x.py').write_text('', encoding='utf-8')
    _docs_fixture(tmp_path, monkeypatch,
                  'cd sub && python -m pytest tests/test_x.py -q\n')
    assert checker.check_doc_commands() == []


def test_doc_commands_ignores_prose_about_pytest(tmp_path, monkeypatch):
    """正文里的「pytest 入口」「pytest 自动发现」不是路径，不能误报。"""
    (tmp_path / 'scripts').mkdir()
    (tmp_path / 'scripts' / 'ok.py').write_text('# ok', encoding='utf-8')
    _docs_fixture(tmp_path, monkeypatch,
                  '把检查接进 pytest 入口；另外 pytest 自动发现也能用。\n'
                  'python scripts/ok.py\n')          # 至少一条真命令，避免「规则失效」提示
    assert checker.check_doc_commands() == []


def test_doc_commands_flags_missing_install_path(tmp_path, monkeypatch):
    (tmp_path / 'scripts').mkdir()
    (tmp_path / 'pkg').mkdir()
    _docs_fixture(tmp_path, monkeypatch,
                  'pip install -e pkg\npip install -e nowhere\n')
    problems = checker.check_doc_commands()
    assert len(problems) == 1 and 'nowhere' in problems[0], problems
