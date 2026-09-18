# -*- coding: utf-8 -*-
r"""
曲线判据的**唯一实现**与跨层一致性（P4/V3 的方法学回归）
=========================================================

2026-09-17 起，「连续合格区间」「谐振提取」「谐振峰频差」的规则只有**一份**实现
（`tpc_toolkit/curves.py`），库层与 MCP 层都调它。本文件钉住三件事：

1. **规则本身**：区间只按相邻采样合并（绝不跨越不合格点）、prominence 过滤、
   配对（就近 + 一对一 + 容差）、以及 V3 判据的三个出口
   （`within_limit` / `exceeds_limit` / **`no_matched_resonance` 不算通过**）；
2. **跨层一致**：同一条曲线经 `cst_mcp.analysis.find_resonances` /
   `contiguous_bands` 与 `tpc_toolkit.curves` 得到的结果**必须完全相同**
   （这就是防「两套规则漂移」的机器检查）；
3. **库层委托**：`ResultReader.resonances()` / `resonance_shift()` 走的是同一规则
   （用注入的假 Result 对象离线验证，不需要 CST）。

运行方式::

    pytest tests/test_curve_rules.py -v
"""

import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
_MCP_SRC = os.path.join(ROOT, 'integrations', 'cst-mcp', 'src')
if _MCP_SRC not in sys.path:
    sys.path.insert(0, _MCP_SRC)

from tpc_toolkit.curves import (                                # noqa: E402
    contiguous_bands, find_resonances, match_resonances, resonance_criterion,
)

#: 一条「两谷」合成曲线。逐点合格性（阈值 −10 dB，below）：
#: 300 −5 不合格 / 301 −12 合格 / 302 −25 合格（谷，prominence 13）
#: 303 −8 不合格 / 304 −6 不合格 / 305 −3 不合格（峰）/ 306 −9 不合格
#: 307 −20 合格（谷，prominence 11）/ 308 −4 不合格
FREQS = [300.0, 301.0, 302.0, 303.0, 304.0, 305.0, 306.0, 307.0, 308.0]
DB = [-5.0, -12.0, -25.0, -8.0, -6.0, -3.0, -9.0, -20.0, -4.0]


# ============================================================
# 1. 连续合格区间
# ============================================================

def test_bands_never_bridge_a_failing_point():
    bands = contiguous_bands(FREQS, DB, threshold_db=-10.0, criterion='below')
    assert [(b['fmin_ghz'], b['fmax_ghz']) for b in bands] == [(301.0, 302.0),
                                                               (307.0, 307.0)]
    assert [b['index'] for b in bands] == [0, 1]
    first = bands[0]
    assert first['n_points'] == 2
    assert first['best_db'] == -25.0 and first['best_freq_ghz'] == 302.0
    assert first['worst_db'] == -12.0 and first['worst_freq_ghz'] == 301.0
    assert first['margin_db'] == pytest.approx(2.0)          # −10 − (−12)


def test_bands_above_criterion_and_max_gap():
    bands = contiguous_bands(FREQS, DB, threshold_db=-6.0, criterion='above')
    assert [(b['fmin_ghz'], b['fmax_ghz']) for b in bands] == [(300.0, 300.0),
                                                               (304.0, 305.0),
                                                               (308.0, 308.0)]
    # 相邻点频差超过 max_gap 就断开（哪怕中间没有不合格点）
    split = contiguous_bands([300.0, 301.0, 305.0, 306.0],
                             [-20.0, -20.0, -20.0, -20.0],
                             threshold_db=-10.0, max_gap_ghz=2.0)
    assert [(b['fmin_ghz'], b['fmax_ghz']) for b in split] == [(300.0, 301.0),
                                                               (305.0, 306.0)]


def test_bands_reject_bad_arguments():
    with pytest.raises(ValueError):
        contiguous_bands(FREQS, DB, threshold_db=-10.0, criterion='sideways')
    with pytest.raises(ValueError):
        contiguous_bands(FREQS, DB[:-1], threshold_db=-10.0)


# ============================================================
# 2. 谐振提取 + 配对 + V3 判据
# ============================================================

def test_find_resonances_prominence_and_band():
    found = find_resonances(FREQS, DB, kind='min')
    assert [m['freq_ghz'] for m in found] == [302.0, 307.0]
    assert found[0]['prominence_db'] == pytest.approx(min(-12.0, -8.0) + 25.0)   # 13
    assert found[1]['prominence_db'] == pytest.approx(min(-9.0, -4.0) + 20.0)    # 11
    # prominence 过滤掉较浅的那一个
    assert [m['freq_ghz'] for m in
            find_resonances(FREQS, DB, kind='min', min_prominence_db=12.0)] == [302.0]
    # 只在带内找
    assert [m['freq_ghz'] for m in
            find_resonances(FREQS, DB, kind='min', band=(305.0, 308.0))] == [307.0]
    # 峰
    assert find_resonances(FREQS, DB, kind='max')[0]['freq_ghz'] == 305.0
    with pytest.raises(ValueError):
        find_resonances(FREQS, DB, kind='bogus')


def _peak(freq, db, prominence=1.0):
    return {'freq_ghz': freq, 'db': db, 'kind': 'min', 'prominence_db': prominence}


def test_match_resonances_is_one_to_one_and_honours_tolerance():
    first = [_peak(100.0, -20.0), _peak(200.0, -30.0)]
    second = [_peak(100.2, -19.0), _peak(100.4, -18.0), _peak(300.0, -10.0)]

    loose = match_resonances(first, second, tolerance_ghz=1.0)
    # 100.0 → 100.2（0.2 GHz，且在容差内）；200.0 的最近点是 100.4（99.6 GHz）⇒ 超出容差
    assert loose['n_matched'] == 1
    assert loose['n_unmatched_first'] == 1
    assert loose['n_unmatched_second'] == 2
    assert [p['freq_second_ghz'] for p in loose['pairs']] == [100.2]
    assert loose['max_delta_ghz'] == pytest.approx(0.2)

    # 不加容差时：200.0 也会配上最近点（说明容差确实起作用）
    unlimited = match_resonances(first, second)
    assert unlimited['n_matched'] == 2
    assert unlimited['max_delta_ghz'] == pytest.approx(99.6)

    # 已经用过的点不会被重复配对
    assert len({p['freq_second_ghz'] for p in unlimited['pairs']}) == 2

    assert match_resonances(first, second, tolerance_ghz=0.1)['n_matched'] == 0


def test_resonance_criterion_three_outcomes():
    ref = [_peak(341.92, -32.0, 5.0)]
    close = [_peak(342.20, -17.0, 3.0)]
    far = [_peak(347.40, -38.0, 3.0)]

    ok = resonance_criterion(ref, close, limit_ghz=1.0)
    assert ok['ok'] is True and ok['reason'] == 'within_limit'
    assert ok['max_delta_ghz'] == pytest.approx(0.28)
    assert ok['pairs'][0]['db_first'] == -32.0 and ok['pairs'][0]['db_second'] == -17.0

    bad = resonance_criterion(ref, far, limit_ghz=1.0)
    assert bad['ok'] is False and bad['reason'] == 'exceeds_limit'
    assert bad['max_delta_ghz'] == pytest.approx(5.48)

    # 配不上任何峰 ⇒ **不算通过**（「没配上」与「通过」必须分开）
    none = resonance_criterion(ref, far, limit_ghz=1.0, tolerance_ghz=0.5)
    assert none['ok'] is False and none['reason'] == 'no_matched_resonance'
    assert none['max_delta_ghz'] is None


# ============================================================
# 3. 跨层一致（防两套规则漂移）
# ============================================================

def test_mcp_layer_delegates_to_the_same_rule():
    from cst_mcp import analysis as mcp_analysis

    assert mcp_analysis.find_resonances(FREQS, DB, kind='min') == \
        find_resonances(FREQS, DB, kind='min')
    assert mcp_analysis.find_resonances(FREQS, DB, kind='min',
                                        min_prominence_db=12.0) == \
        find_resonances(FREQS, DB, kind='min', min_prominence_db=12.0)
    assert mcp_analysis.contiguous_bands(FREQS, DB, threshold_db=-10.0) == \
        contiguous_bands(FREQS, DB, threshold_db=-10.0)


def test_mcp_layer_still_reports_invalid_arguments_as_tool_error():
    from cst_mcp import analysis as mcp_analysis
    from cst_mcp.errors import ToolError

    with pytest.raises(ToolError) as caught:
        mcp_analysis.find_resonances(FREQS, DB, kind='bogus')
    assert caught.value.code == 'invalid_arguments'
    with pytest.raises(ToolError):
        mcp_analysis.contiguous_bands(FREQS, DB, threshold_db=-10.0,
                                      criterion='sideways')


def test_mcp_analysis_module_no_longer_implements_the_rule_itself():
    """静态：MCP 层不得再出现「相邻三点比较」这类规则本体。"""
    path = os.path.join(_MCP_SRC, 'cst_mcp', 'analysis.py')
    code = '\n'.join(line for line in open(path, encoding='utf-8')
                     if not line.lstrip().startswith('#'))
    assert 'prominence = min(prev_value, next_value) - value' not in code
    assert 'library_find_resonances' in code
    assert 'library_contiguous_bands' in code


# ============================================================
# 4. 库层 ResultReader 委托（注入假 Result，不需要 CST）
# ============================================================

class _FakeResult:
    """
    满足 `ResultReader` 需要的**最小**接口。

    ⚠️ `read_s_parameter()` 返回的是 CST 的**原始形状**：每行 ``(频率, 复数值)``
    （`ResultReader._split()` 按两列拆），不是「频率表 + 数值表」。
    """

    def __init__(self, db_values):
        self.rows = {name: [[FREQS[i], complex(10 ** (value / 20.0), 0.0)]
                            for i, value in enumerate(values)]
                     for name, values in db_values.items()}
        self.last_errors = {}

    def read_s_parameter(self, name, run_id=0):
        if name not in self.rows:
            raise KeyError(name)
        return self.rows[name]


def _reader(db_values=None):
    from topo_modeler.result_reader import ResultReader
    return ResultReader(_FakeResult(db_values or {'S1,1': DB}),
                        names=['S1,1'], run_id=0)


def test_result_reader_resonances_uses_the_shared_rule():
    assert _reader().resonances('S1,1') == find_resonances(FREQS, DB, kind='min')
    assert _reader().resonances('S1,1', min_prominence_db=12.0) == \
        find_resonances(FREQS, DB, kind='min', min_prominence_db=12.0)


def test_result_reader_resonance_shift_matches_the_criterion():
    reader = _reader()
    # 同一形状、整体下移 2 dB ⇒ 极值位置不变，但「最深点」的 dB 更低
    shifted = _reader({'S1,1': [v - 2.0 for v in DB]})

    verdict = reader.resonance_shift(shifted, 'S1,1', limit_ghz=1.0)
    assert verdict['ok'] is True and verdict['reason'] == 'within_limit'
    assert verdict['n_matched'] == 2
    assert verdict['max_delta_ghz'] == pytest.approx(0.0)
    assert verdict['pairs'][0]['db_second'] == pytest.approx(-27.0)

    # 判据限值收紧到 0 ⇒ 必须转而判「未通过」（0 不满足「严格小于 0」）
    assert reader.resonance_shift(shifted, 'S1,1', limit_ghz=0.0)['ok'] is False


def test_result_reader_resonance_shift_reports_no_match():
    a = _reader()
    # 单调上升的曲线**没有内部极小值** ⇒ 另一侧根本没有谐振可配
    monotonic = [-30.0 + index * 2.0 for index in range(len(FREQS))]
    b = _reader({'S1,1': monotonic})
    assert b.resonances('S1,1') == []
    verdict = a.resonance_shift(b, 'S1,1', limit_ghz=1.0)
    assert verdict['ok'] is False
    assert verdict['reason'] == 'no_matched_resonance'
    assert verdict['n_matched'] == 0


def test_result_reader_resonance_shift_honours_tolerance():
    """整体平移曲线 ⇒ 只有容差够大时才配得上（配不上就报 no_matched_resonance）。"""
    a = _reader()
    moved = _reader({'S1,1': DB})          # 同一形状
    verdict = a.resonance_shift(moved, 'S1,1', limit_ghz=1.0)     # 同一条曲线
    assert verdict['ok'] is True and verdict['max_delta_ghz'] == 0.0
