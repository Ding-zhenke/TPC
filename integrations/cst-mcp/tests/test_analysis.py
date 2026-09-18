# -*- coding: utf-8 -*-
"""
S 参数分析测试（P3）
====================

守住计划里那条**最容易写错**的要求：

    不能将离散合格区间并成一个带宽。

以及三条口径：dB = 20·log10|S|、零值 −300 dB、谐振按相邻三点极值定义。
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from cst_mcp.analysis import (          # noqa: E402
    analyze_series,
    contiguous_bands,
    conventions,
    find_resonances,
    read_series_csv,
    to_db,
)
from cst_mcp.errors import ToolError    # noqa: E402

#: 一条**故意分成两段**的曲线：300–318 与 342–380 合格，中间一个大坑
FREQS = [300.0 + i for i in range(81)]
S21 = [-1.0 if (f <= 318 or f >= 342) else -20.0 for f in FREQS]


# ============================================================
# 口径
# ============================================================

def test_db_convention_matches_lower_layers():
    """dB 口径必须与底层唯一实现一致（零值 −300 dB）。"""
    from cst_solver._result_core import _to_db
    conv = conventions()
    assert conv['s_db'] == '20*log10(abs(S))'
    assert conv['zero_magnitude_db'] == -300.0
    assert float(_to_db(0.0)) == conv['zero_magnitude_db']
    assert to_db([0.0])[0] == -300.0
    assert to_db([0.1])[0] == pytest.approx(-20.0)
    assert to_db([complex(0.5, 0.0)])[0] == pytest.approx(-6.0206, abs=1e-3)
    assert to_db([None])[0] != to_db([None])[0]          # NaN 保持 NaN


# ============================================================
# 连续区间：绝不合并离散区间
# ============================================================

def test_disjoint_passbands_are_never_merged():
    bands = contiguous_bands(FREQS, S21, threshold_db=-3.0, criterion='above')
    assert len(bands) == 2
    assert (bands[0]['fmin_ghz'], bands[0]['fmax_ghz']) == (300.0, 318.0)
    assert (bands[1]['fmin_ghz'], bands[1]['fmax_ghz']) == (342.0, 380.0)
    assert bands[0]['bandwidth_ghz'] == 18.0
    assert bands[1]['bandwidth_ghz'] == 38.0
    assert bands[0]['index'] == 0 and bands[1]['index'] == 1


def test_single_failing_sample_splits_a_band():
    values = [-1.0] * 5 + [-30.0] + [-1.0] * 5
    freqs = [300.0 + i for i in range(11)]
    bands = contiguous_bands(freqs, values, threshold_db=-3.0, criterion='above')
    assert len(bands) == 2
    assert bands[0]['n_points'] == 5 and bands[1]['n_points'] == 5


def test_below_criterion_for_return_loss():
    """criterion='below' 用于回波损耗：越小越好。"""
    values = [-20.0, -25.0, -8.0, -22.0]
    freqs = [300.0, 301.0, 302.0, 303.0]
    bands = contiguous_bands(freqs, values, threshold_db=-10.0, criterion='below')
    assert len(bands) == 2
    assert bands[0]['best_db'] == -25.0          # 最有利 = 最小
    assert bands[0]['worst_db'] == -20.0
    assert bands[0]['margin_db'] == 10.0         # 阈值 -10 相对最差点 -20 的余量


def test_max_gap_splits_even_when_samples_are_adjacent():
    """相邻采样但频差过大时也要断开（拼接扫频场景）。"""
    freqs = [300.0, 301.0, 400.0, 401.0]
    values = [-1.0, -1.0, -1.0, -1.0]
    merged = contiguous_bands(freqs, values, threshold_db=-3.0, criterion='above')
    assert len(merged) == 1                       # 默认只看采样相邻性
    split = contiguous_bands(freqs, values, threshold_db=-3.0,
                             criterion='above', max_gap_ghz=10.0)
    assert len(split) == 2


def test_invalid_criterion_is_rejected():
    with pytest.raises(ToolError) as excinfo:
        contiguous_bands(FREQS, S21, threshold_db=-3.0, criterion='sideways')
    assert excinfo.value.code == 'invalid_arguments'


# ============================================================
# 谐振定义
# ============================================================

def test_resonance_is_local_minimum_of_adjacent_samples():
    freqs = [1.0, 2.0, 3.0, 4.0, 5.0]
    values = [-5.0, -8.0, -20.0, -8.0, -5.0]
    found = find_resonances(freqs, values, kind='min')
    assert len(found) == 1
    assert found[0]['freq_ghz'] == 3.0
    assert found[0]['db'] == -20.0
    assert found[0]['prominence_db'] == 12.0      # 相对两侧较不利一方（-8）


def test_resonance_prominence_filter():
    freqs = [1.0, 2.0, 3.0]
    values = [-5.0, -5.2, -5.0]
    assert find_resonances(freqs, values, kind='min') != []
    assert find_resonances(freqs, values, kind='min',
                           min_prominence_db=1.0) == []


# ============================================================
# analyze_series 结构
# ============================================================

def test_analyze_series_reports_units_band_and_source():
    result = analyze_series(FREQS, S21, metric='S2,1', threshold_db=-3.0,
                            criterion='above',
                            data_source={'kind': 'csv', 'path': 'x.csv'},
                            series_reference={'path': 'x.csv'})
    assert result['metric'] == 'S2,1'
    assert result['n_bands'] == 2
    assert result['total_bandwidth_ghz'] == pytest.approx(56.0)
    assert '不是**一段连续带宽' in result['total_bandwidth_definition']
    assert result['conventions']['frequency_unit'] == 'GHz'
    assert result['criterion']['threshold_db'] == -3.0
    assert result['data_source'] == {'kind': 'csv', 'path': 'x.csv'}
    assert result['series_reference'] == {'path': 'x.csv'}    # 原样带回
    assert result['analysis_band_ghz'] == [300.0, 380.0]


def test_analyze_series_band_filter_and_empty_band():
    result = analyze_series(FREQS, S21, metric='S2,1', threshold_db=-3.0,
                            criterion='above', band=(300.0, 310.0))
    assert result['n_bands'] == 1
    assert result['requested_band_ghz'] == [300.0, 310.0]
    with pytest.raises(ToolError) as excinfo:
        analyze_series(FREQS, S21, metric='S2,1', threshold_db=-3.0,
                       band=(500.0, 600.0))
    assert excinfo.value.code == 'analysis_failed'


# ============================================================
# CSV 读取
# ============================================================

def test_read_csv_with_db_columns(tmp_path):
    path = tmp_path / 's.csv'
    path.write_text('freq_GHz,S1,1,S2,1\n300,-10.5,-1.2\n301,-11.0,-1.3\n',
                    encoding='utf-8')
    series = read_series_csv(str(path))
    assert series['freqs'] == [300.0, 301.0]
    assert series['columns']['S1,1'] == [-10.5, -11.0]
    assert series['column_units']['S1,1'] == 'dB'


def test_read_csv_converts_linear_columns(tmp_path):
    path = tmp_path / 's.csv'
    path.write_text('freq_GHz,S2,1\n300,0.1\n301,1.0\n', encoding='utf-8')
    series = read_series_csv(str(path))
    assert series['columns']['S2,1'][0] == pytest.approx(-20.0)
    assert series['columns']['S2,1'][1] == pytest.approx(0.0)
    assert series['column_units']['S2,1'] == 'linear→dB'


def test_read_csv_missing_file(tmp_path):
    with pytest.raises(ToolError) as excinfo:
        read_series_csv(str(tmp_path / 'ghost.csv'))
    assert excinfo.value.code == 'not_found'


def test_read_csv_accepts_quoted_s_parameter_names(tmp_path):
    """标准 CSV 会把含逗号的字段加引号（仓库自己导出的就是这个形态）。"""
    path = tmp_path / 'quoted.csv'
    path.write_text('freq_GHz,"S1,1","S2,1"\n300,-10.0,-1.0\n301,-11.0,-1.5\n',
                    encoding='utf-8')
    series = read_series_csv(str(path))
    assert set(series['columns']) == {'S1,1', 'S2,1'}
    assert series['columns']['S2,1'] == [-1.0, -1.5]


def test_split_s_parameter_header_is_rejoined(tmp_path):
    """手写 CSV 不加引号时，``S2,1`` 会被切成两列 —— 必须拼回去。"""
    from cst_mcp.analysis import _merge_split_s_parameter_names
    assert _merge_split_s_parameter_names(['S1', '1', 'S2', '1']) == ['S1,1', 'S2,1']
    assert _merge_split_s_parameter_names(['S21', 'S11']) == ['S21', 'S11']
    assert _merge_split_s_parameter_names(['gain', '1']) == ['gain', '1']
