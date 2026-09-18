# -*- coding: utf-8 -*-
r"""
结果读取的**失败诊断**（离线，不需要 CST）
==========================================

`cst_solver.Result(path)` 打开结果失败时，必须给出**可执行的原因**，
而不是把 CST 读取器的原始错误直接甩给用户。理由（2026-09-17 实测，CST 2026）：

* 路径**不存在**且含非 ASCII 字符 ⇒ CST 的 `cst.results.ProjectFile()` 抛
  ``UnicodeDecodeError: 'utf-8' codec can't decode byte 0xb2 ...`` ——
  看起来像编码问题，其实是「文件不存在」（错误消息里带着本地代码页编码的路径，
  读取器又按 UTF-8 解它）；纯 ASCII 的不存在路径则正常报 `FileNotFoundError`。
* 工程被认为「正在 CST 里打开」 ⇒ `UserWarning: Project is opened in CST Studio Suite`。

⚠️ 顺带更正一个**曾经被误判**的结论：**非 ASCII 路径本身不影响读取** ——
中文路径下的已求解工程实测能正常读出 31 个结果树条目（见
`tests/test_result_reading_real_project.py`）。当时把「路径写错」误当成了「编码限制」。

运行方式::

    pytest cst_solver/tests/test_result_open.py -v
"""

import os
import sys

import pytest

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from cst_solver import _result_core                     # noqa: E402
from cst_solver._result_core import (                   # noqa: E402
    Result, describe_result_open_failure,
)


def test_missing_ascii_path_says_file_missing(tmp_path):
    message = describe_result_open_failure(
        str(tmp_path / 'nope.cst'), FileNotFoundError("File does not exist: 'x'"))
    assert '工程文件不存在' in message
    assert 'UnicodeDecodeError' not in message          # ASCII 路径不涉及那个坑


def test_missing_non_ascii_path_explains_the_misleading_error(tmp_path):
    message = describe_result_open_failure(
        str(tmp_path / '不存在的工程.cst'),
        UnicodeDecodeError('utf-8', b'\xb2', 33, 34, 'invalid start byte'))
    assert '工程文件不存在' in message
    assert 'UnicodeDecodeError' in message              # 原始原因保留
    assert '编码' in message                            # 并说明它容易误导


def test_opened_in_cst_gets_an_actionable_hint(tmp_path):
    existing = tmp_path / 'here.cst'
    existing.write_text('x', encoding='utf-8')
    message = describe_result_open_failure(
        str(existing), UserWarning('Project is opened in CST Studio Suite.'))
    assert 'CST' in message and 'allow_interactive' in message


def test_unknown_failure_keeps_the_original_reason(tmp_path):
    existing = tmp_path / 'here.cst'
    existing.write_text('x', encoding='utf-8')
    message = describe_result_open_failure(str(existing), OSError('磁盘错误'))
    assert 'OSError' in message and '磁盘错误' in message


def test_result_wraps_reader_failure_and_chains_the_cause(monkeypatch, tmp_path):
    """`Result(...)` 必须包装成 RuntimeError 并保留原始异常链。"""
    class _BrokenModule:
        @staticmethod
        def ProjectFile(path, allow_interactive=True):
            raise UnicodeDecodeError('utf-8', b'\xb2', 0, 1, 'invalid start byte')

    monkeypatch.setattr(_result_core, '_load_cst_module',
                        lambda name: _BrokenModule)
    target = str(tmp_path / '不存在.cst')

    with pytest.raises(RuntimeError) as caught:
        Result(target)
    assert '工程文件不存在' in str(caught.value)
    assert isinstance(caught.value.__cause__, UnicodeDecodeError)


def test_result_success_path_does_not_touch_the_wrapper(monkeypatch):
    """成功路径照旧：包装层只在不成功时才介入。"""
    class _Module:
        class _Result:
            def get_3d(self):
                return 'mini-3d'

        ProjectFile = staticmethod(lambda path, allow_interactive=True: _Module._Result())

    monkeypatch.setattr(_result_core, '_load_cst_module', lambda name: _Module)
    result = Result(os.path.join(_ROOT, 'pyproject.toml'))
    assert result.result_module == 'mini-3d'
    assert result.last_errors == {}
