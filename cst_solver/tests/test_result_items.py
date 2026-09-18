# -*- coding: utf-8 -*-
r"""
结果项的**路径写法容错**与**失败诊断**（离线，不需要 CST）
==========================================================

两个真实坑（2026-09-17 实测，CST 2026）：

1. `read_1D()` 一直**无条件**给路径加 ``1D Results\\`` 前缀，而
   `get_tree_items()` 返回的是**完整**路径 —— 于是「查出路径再读回来」这最自然的用法
   会得到 ``1D Results\\1D Results\\…`` 并报 ``tree path not found``。
   现在两种写法都接受（完整路径原样用，相对路径补前缀）。
2. `ANT_LEAKY_EPC_GRID.cst` 里 63 个结果项中 **45 个正常、18 个
   ``1D Results\\farfield (f=…)`` 项在 `get_result_item()` 阶段就抛
   `UnicodeDecodeError`**（同工程的括号名、材料色散、端口信息等条目都正常 ⇒
   不是路径写法问题）。裸抛这个异常对使用者毫无帮助，故翻译成可执行的话。

运行方式::

    pytest cst_solver/tests/test_result_items.py -v
"""

import os
import sys

import pytest

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from cst_solver import _result_core                     # noqa: E402
from cst_solver._result_core import (                   # noqa: E402
    Result, describe_result_item_failure,
)

_PREFIX = '1D Results\\'
#: 结果树的一级分类（与 `Result._TREE_PREFIXES` 一致）
_ROOTS = ('1D Results\\', '2D/3D Results\\', 'Tables\\', 'Farfields\\')


class _Item:
    """最小结果项替身。"""

    def __init__(self, path):
        self.path = path

    def get_xdata(self):
        return [1.0, 2.0, 3.0]

    def get_ydata(self):
        return [10.0, 20.0, 30.0]


class _Module:
    """
    假 `cst.results` 模块：只认**带前缀的完整路径**；可指定某路径抛异常。

    :param bad_paths: 集合, 这些完整路径会抛 UnicodeDecodeError
    """

    def __init__(self, bad_paths=()):
        self.calls = []
        self.bad_paths = set(bad_paths)

    def get_result_item(self, path, run_id=0, *args, **kwargs):
        self.calls.append(path)
        if path in self.bad_paths:
            raise UnicodeDecodeError('utf-8', b'\xb3', 23, 24, 'invalid start byte')
        if not path.startswith(_ROOTS):
            raise UserWarning(f"tree path not found: {path!r}.")
        return _Item(path)


def _result_with(module):
    """构造一个 `Result`，把底层模块换成替身（不碰 CST）。"""
    result = Result.__new__(Result)                 # 跳过 __init__（会去导入 cst.results）
    result.app_result = module
    result.result_module = module
    result.last_errors = {}
    return result


# ============================================================
# 1. 两种路径写法都接受
# ============================================================

def test_relative_path_gets_the_prefix():
    module = _Module()
    data = _result_with(module).read_1D('S-Parameters\\S1,1')
    assert module.calls == [_PREFIX + 'S-Parameters\\S1,1']
    assert data.shape == (3, 2)


def test_full_path_is_used_as_is():
    """`get_tree_items()` 返回的完整路径直接可用（老实现会拼成双层前缀）。"""
    module = _Module()
    full = _PREFIX + 'S-Parameters\\S1,1'
    _result_with(module).read_1D(full)
    assert module.calls == [full], module.calls


def test_both_forms_give_the_same_data():
    module = _Module()
    result = _result_with(module)
    relative = result.read_1D('S-Parameters\\S1,1')
    full = result.read_1D(_PREFIX + 'S-Parameters\\S1,1')
    assert (relative == full).all()


def test_other_tree_roots_are_recognised_too():
    module = _Module()
    _result_with(module).read_1D('Tables\\1D Results\\Realized Gain')
    assert module.calls == ['Tables\\1D Results\\Realized Gain']   # 原样，不加前缀


# ============================================================
# 2. 失败诊断
# ============================================================

def test_decode_failure_is_translated_with_actionable_hint():
    module = _Module(bad_paths={_PREFIX + 'farfield (f=290)'})
    with pytest.raises(RuntimeError) as caught:
        _result_with(module).read_1D('1D Results\\farfield (f=290)')
    message = str(caught.value)
    assert 'UnicodeDecodeError' in message                  # 原始原因保留
    assert 'farfield' in message                            # 指出已知情形
    assert 'Tables' in message and 'CSV' in message         # 给出处置办法
    assert isinstance(caught.value.__cause__, UnicodeDecodeError)


def test_missing_path_lists_the_candidates_tried():
    module = _Module()

    # 让两条候选都失败：既不是完整路径、补前缀也不认（模拟路径确实不存在）
    class _AlwaysMissing(_Module):
        def get_result_item(self, path, run_id=0, *args, **kwargs):
            self.calls.append(path)
            raise UserWarning(f"tree path not found: {path!r}.")

    module = _AlwaysMissing()
    with pytest.raises(RuntimeError) as caught:
        _result_with(module).read_1D('S-Parameters\\S9,9')
    message = str(caught.value)
    assert module.calls == [_PREFIX + 'S-Parameters\\S9,9', 'S-Parameters\\S9,9']
    assert '已尝试的树路径' in message
    assert '1D Results\\' in message                        # 提醒前缀规则


def test_describe_failure_helpers_are_pure():
    decode = describe_result_item_failure(
        'a\\b', UnicodeDecodeError('utf-8', b'\xb3', 0, 1, 'x'), ['a\\b'])
    assert 'UnicodeDecodeError' in decode and 'Tables' in decode

    missing = describe_result_item_failure(
        'a\\b', UserWarning("tree path not found: 'a\\b'."), ['a\\b'])
    assert 'tree path not found' in missing
    assert '前缀' in missing                                # 说明 read_1D 会补前缀

    other = describe_result_item_failure('a\\b', OSError('磁盘错误'), ['a\\b'])
    assert 'OSError' in other and '已尝试的树路径' in other
    assert 'Tables' not in other                            # 不硬塞无关建议


# ============================================================
# 3. `list_s_parameters()` 只列**真** S 参数
# ============================================================

#: 实测（2026-09-17，`Leaky\ANT_LEAKY_EPC_GRID.cst`）：这条**收敛监控曲线**同样挂在
#: `S-Parameters` 目录下、路径里也含 `S-Parameters`，但根本不是 S 参数。
_TRAP_PATH = '1D Results\\Convergence\\S-Parameters\\Reflection S-Parameters [1]'


class _TreeModule(_Module):
    """假模块：`get_tree_items()` 直接给出路径列表。"""

    def __init__(self, paths):
        super().__init__()
        self.paths = list(paths)

    def get_tree_items(self, tree_filter=None):
        return list(self.paths)


def test_list_s_parameters_excludes_convergence_lookalikes():
    module = _TreeModule([
        _TRAP_PATH,                                   # ← 不是 S 参数
        '1D Results\\S-Parameters\\S1,1',
        '1D Results\\S-Parameters\\S2,1',
        '1D Results\\Materials\\Silicon (lossy)\\Dispersive\\Eps\'',
        'Tables\\1D Results\\Realized Gain,3D,Max. Value (Solid Angle)',
    ])
    assert _result_with(module).list_s_parameters() == ['S1,1', 'S2,1']


def test_list_s_parameters_requires_the_s_parameters_folder():
    module = _TreeModule([
        '1D Results\\Somewhere else\\S1,1',            # 目录不对
        '1D Results\\S-Parameters\\not_an_s_name',     # 名字不对
        '1D Results\\S-Parameters\\S3,4',              # OK
        '1D Results\\S-Parameters\\S11,22',            # 多端口两位数字也 OK
    ])
    assert _result_with(module).list_s_parameters() == ['S11,22', 'S3,4']


def test_list_s_parameters_is_sorted_and_deduplicated():
    module = _TreeModule([
        '1D Results\\S-Parameters\\S2,1',
        '1D Results\\S-Parameters\\S1,1',
        '1D Results\\S-Parameters\\S2,1',
    ])
    assert _result_with(module).list_s_parameters() == ['S1,1', 'S2,1']


# ============================================================
# 4. 路径写法**全类统一**（2026-09-17 修：三种方法三种约定）
# ============================================================

def test_candidate_paths_order_and_dedup():
    """完整路径只留自己；相对路径先补前缀、再补足其它一级分类。"""
    assert Result._candidate_paths('1D Results\\S-Parameters\\S1,1') == \
        ['1D Results\\S-Parameters\\S1,1']
    assert Result._candidate_paths('Tables\\x') == ['Tables\\x']
    relative = Result._candidate_paths('S-Parameters\\S1,1', '1D Results\\')
    assert relative[0] == '1D Results\\S-Parameters\\S1,1'
    assert relative[-1] == 'S-Parameters\\S1,1'
    # 无前缀时把四个一级分类都试一遍
    for prefix in Result._TREE_PREFIXES:
        assert prefix + 'x' in Result._candidate_paths('x')


class _RunIdModule(_Module):
    """假模块：只认**存在**的完整路径（模拟真实结果树），并记录被问过的路径。"""

    def __init__(self, run_ids=(0, 1, 2), known=None):
        super().__init__()
        self.run_ids = list(run_ids)
        self.known = set(known or ('1D Results\\S-Parameters\\S1,1',
                                   '1D Results\\S-Parameters\\S2,1'))
        self.asked = []

    def get_run_ids(self, path, skip_nonparametric=False):
        self.asked.append((path, skip_nonparametric))
        if path not in self.known:
            raise UserWarning(f"tree path not found: {path!r}.")
        return [r for r in self.run_ids if not (skip_nonparametric and r == 0)]


def test_get_run_ids_accepts_both_path_forms():
    """`get_run_ids` 曾经只接受完整路径 —— 相对写法要与 `read_1D` 一致地可用。"""
    module = _RunIdModule()
    result = _result_with(module)

    assert result.get_run_ids('1D Results\\S-Parameters\\S1,1') == [0, 1, 2]
    assert result.get_run_ids('S-Parameters\\S1,1') == [0, 1, 2]
    assert result.get_run_ids('S-Parameters\\S1,1', skip_nonparametric=True) == [1, 2]
    # 相对写法第一次就命中（补前缀的那条候选）
    assert module.asked[1][0] == '1D Results\\S-Parameters\\S1,1'


def test_get_run_ids_failure_lists_candidates():
    module = _RunIdModule()
    with pytest.raises(RuntimeError) as caught:
        _result_with(module).get_run_ids('S-Parameters\\S9,9')
    assert '已尝试的树路径' in str(caught.value)


def test_get_run_ids_reports_missing_interface():
    """底层接口没有 `get_run_ids` 时要说清是版本不支持，而不是 AttributeError。"""
    module = _Module()                              # 没有 get_run_ids
    with pytest.raises(RuntimeError) as caught:
        _result_with(module).get_run_ids('S-Parameters\\S1,1')
    assert 'get_run_ids' in str(caught.value)


def test_get_result_item_accepts_both_path_forms():
    module = _Module()
    result = _result_with(module)
    full = result.get_result_item('1D Results\\S-Parameters\\S1,1')
    relative = result.get_result_item('S-Parameters\\S1,1')
    assert full.get_xdata() == relative.get_xdata()
    assert module.calls == ['1D Results\\S-Parameters\\S1,1',
                            '1D Results\\S-Parameters\\S1,1']
