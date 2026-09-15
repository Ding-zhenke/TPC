# -*- coding: utf-8 -*-
r"""
参数扫描测试（阶段 7 模块 5.3）
==============================
对应 `topo_modeler/scanner.py`。

**怎么在不开 CST 的情况下验扫描**：`ParameterScan` 的执行器是注入的，
所以这里用**桩 runner** —— 枚举、唯一命名、聚合、热力图行列对齐、CSV 行数
这些「扫描本身的逻辑」全都能离线验。真跑 CST 只是换一个 runner。

运行方式::

    pytest topo_modeler/tests/test_scanner.py -v
"""

import csv
import math
import os
import sys

import pytest

_TPC_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _TPC_ROOT not in sys.path:
    sys.path.insert(0, _TPC_ROOT)

from topo_modeler.config import ConfigError, example_config   # noqa: E402
from topo_modeler.scanner import (                            # noqa: E402
    ParameterScan,
    ScanError,
    band_min_metric,
    peak_metric,
    value_metric,
)


def _base(model_type='straight_waveguide', **geometry):
    cfg = example_config(model_type)
    cfg.setdefault('geometry', {}).update(geometry)
    return cfg


def _simple_runner(scale=1.0):
    """桩执行器：直接返回指标字典（不需要 CST，也不需要结果文件）。"""
    def _run(point):
        return {'S21@330': -3.0 * point.params.get('length', 1) * scale,
                '峰位': 300.0 + point.params.get('length', 0)}
    return _run


# ============================================================
# 1. 枚举与命名（纯逻辑）
# ============================================================

def test_combinations_is_cartesian_product():
    scan = ParameterScan(_base(), {'length': [16, 18, 20], 'width': [10, 14]})
    combos = scan.combinations()
    assert len(combos) == 6 == scan.n_combinations
    seen = {(c[0]['length'], c[0]['width']) for c in combos}
    assert seen == {(l, w) for l in (16, 18, 20) for w in (10, 14)}


def test_combinations_writes_params_into_config_and_validates():
    scan = ParameterScan(_base(), {'length': [16, 20]})
    for values, cfg in scan.combinations():
        assert cfg['geometry']['length'] == values['length']


def test_invalid_axis_value_is_rejected_by_config_validation():
    """轴取值非法时，在**枚举阶段**就报错（而不是等跑完 CST）。"""
    scan = ParameterScan(_base(), {'topology': ['AB', 'ab']})
    with pytest.raises(ConfigError, match='合法取值'):
        scan.combinations()


def test_names_are_unique_and_reproducible():
    scan = ParameterScan(_base(), {'length': [16, 18], 'width': [10, 14]})
    names = [p.name for p in scan.plan()]
    assert len(names) == len(set(names)) == 4
    again = ParameterScan(_base(), {'length': [16, 18], 'width': [10, 14]})
    assert [p.name for p in again.plan()] == names


def test_name_contains_param_values():
    scan = ParameterScan(_base(), {'length': [18]}, name='wg')
    point = scan.plan()[0]
    assert point.name.startswith('wg_')
    assert 'length18' in point.name
    assert point.cst_path.endswith(point.name + '.cst')


def test_plan_does_not_execute_anything():
    calls = []
    scan = ParameterScan(_base(), {'length': [16, 18]},
                         runner=lambda p: calls.append(p.name))
    scan.plan()
    assert calls == []
    assert all(p.status == 'pending' for p in scan.points)


# ============================================================
# 2. 非法输入
# ============================================================

def test_empty_params_rejected():
    with pytest.raises(ScanError, match='不能为空'):
        ParameterScan(_base(), {})


def test_empty_axis_rejected():
    with pytest.raises(ScanError, match='取值序列为空'):
        ParameterScan(_base(), {'length': []})


def test_duplicate_axis_values_rejected():
    with pytest.raises(ScanError, match='重复'):
        ParameterScan(_base(), {'length': [16, 16]})


def test_run_without_runner_raises_with_hint():
    scan = ParameterScan(_base(), {'length': [16]})
    with pytest.raises(ScanError, match='需要一个执行器'):
        scan.run()


# ============================================================
# 3. 执行与容错
# ============================================================

def test_run_records_metrics_and_status(tmp_path):
    scan = ParameterScan(_base(), {'length': [16, 18]},
                         runner=_simple_runner(), workdir=str(tmp_path))
    scan.run()
    assert [p.status for p in scan.points] == ['ok', 'ok']
    assert scan.points[0].metrics['S21@330'] == -48.0
    assert all(p.duration_s >= 0 for p in scan.points)


def test_one_failure_does_not_stop_the_scan(tmp_path):
    def flaky(point):
        if point.params['length'] == 18:
            raise RuntimeError('boom')
        return {'m': 1.0}

    scan = ParameterScan(_base(), {'length': [16, 18, 20]},
                         runner=flaky, workdir=str(tmp_path))
    scan.run()
    assert [p.status for p in scan.points] == ['ok', 'error', 'ok']
    assert len(scan.failed) == 1 and len(scan.succeeded) == 2
    assert 'boom' in scan.failed[0].error
    assert 'boom' in scan.last_errors[scan.failed[0].name]


def test_continue_on_error_false_raises(tmp_path):
    def always_fail(point):
        raise RuntimeError('nope')

    scan = ParameterScan(_base(), {'length': [16, 18]}, runner=always_fail,
                         workdir=str(tmp_path))
    with pytest.raises(ScanError, match='continue_on_error=False'):
        scan.run(continue_on_error=False)


def test_metric_failure_is_recorded_not_fatal(tmp_path):
    """某个指标算不出来（比如带内没数据）不该让整个点失败。"""
    def runner(point):
        return _FakeReader()                  # 返回 reader ⇒ metric_specs 才会被执行

    scan = ParameterScan(_base(), {'length': [16]}, runner=runner,
                         workdir=str(tmp_path),
                         metric_specs={'好指标': value_metric('S2,1', 330.0),
                                       '坏指标': lambda r: 1 / 0})
    scan.run()
    assert scan.points[0].status == 'ok'
    assert scan.points[0].metrics['好指标'] == -4.0
    assert '坏指标' not in scan.points[0].metrics
    assert any('坏指标' in k for k in scan.last_errors)


def test_dict_payload_skips_metric_specs_and_says_so(tmp_path):
    """
    runner 返回**字典**时 `metric_specs` 无从执行（没有 reader）——
    这是合法的用法（直接把指标算好交回来），但必须**留下痕迹**，
    否则「设了指标却一直没有值」会查不出来。
    """
    scan = ParameterScan(_base(), {'length': [16]}, runner=_simple_runner(),
                         workdir=str(tmp_path),
                         metric_specs={'永远不会算': value_metric('S2,1', 330.0)})
    scan.run()
    assert '永远不会算' not in scan.points[0].metrics
    assert '_contract' in scan.last_errors
    assert 'metric_specs' in scan.last_errors['_contract']


def test_audit_records_every_point(tmp_path):
    from topo_modeler.audit import AuditLog
    audit = AuditLog(str(tmp_path / 'logs'))
    scan = ParameterScan(_base(), {'length': [16, 18]},
                         runner=_simple_runner(), workdir=str(tmp_path),
                         audit=audit)
    scan.run()
    records = [r for r in audit.read() if r['tool'] == 'scan_point']
    assert len(records) == 2
    assert all(r['status'] == 'ok' for r in records)
    assert any(r['metrics'] for r in records)


# ============================================================
# 4. 指标工厂
# ============================================================

class _FakeReader:
    def __init__(self):
        self._d = {'S1,1': ([310.0, 330.0, 350.0], [-15.0, -21.0, -12.0]),
                   'S2,1': ([310.0, 330.0, 350.0], [-2.0, -4.0, -18.0])}

    def value_at(self, name, freq, in_db=True):
        xs, ys = self._d[name]
        i = min(range(len(xs)), key=lambda k: abs(xs[k] - freq))
        return ys[i]

    def peak_position(self, name, band=None, kind='min'):
        xs, ys = self._d[name]
        pick = min if kind == 'min' else max
        return pick(zip(xs, ys), key=lambda p: p[1])

    def read_s_parameters_db(self, names=None):
        return {n: self._d[n] for n in (names or self._d)}


def test_value_metric():
    m = value_metric('S2,1', 330.0)
    assert m(_FakeReader()) == -4.0
    assert 'S2,1' in m.__name__


def test_peak_metric_returns_frequency():
    assert peak_metric('S1,1')(_FakeReader()) == 330.0
    assert peak_metric('S2,1', kind='max')(_FakeReader()) == 310.0


def test_band_min_metric():
    assert band_min_metric('S1,1', (300.0, 340.0))(_FakeReader()) == -21.0


def test_band_min_metric_without_points_raises():
    with pytest.raises(ScanError, match='没有数据点'):
        band_min_metric('S1,1', (500.0, 600.0))(_FakeReader())


# ============================================================
# 5. 聚合与热力图（判据：行列标签必须就是扫描轴）
# ============================================================

def _scan_2d(tmp_path):
    return ParameterScan(_base(), {'length': [16, 18, 20], 'width': [10, 14]},
                         runner=_simple_runner(), workdir=str(tmp_path)).run()


def test_metric_matrix_shape_matches_axes(tmp_path):
    scan = _scan_2d(tmp_path)
    matrix, xl, yl = scan.metric_matrix('S21@330', 'length', 'width')
    assert xl == [16, 18, 20]
    assert yl == [10, 14]
    assert len(matrix) == 2 and len(matrix[0]) == 3
    # matrix[i][j] 对应 (yl[i], xl[j])
    assert matrix[0][0] == -48.0          # width=10, length=16
    assert matrix[1][2] == -60.0          # width=14, length=20


def test_metric_matrix_fills_nan_for_failed_points(tmp_path):
    def flaky(p):
        if p.params['length'] == 18:
            raise RuntimeError('boom')
        return {'m': 1.0}

    scan = ParameterScan(_base(), {'length': [16, 18, 20], 'width': [10]},
                         runner=flaky, workdir=str(tmp_path)).run()
    matrix, xl, yl = scan.metric_matrix('m', 'length', 'width')
    assert math.isnan(matrix[0][1])
    assert matrix[0][0] == 1.0 and matrix[0][2] == 1.0


def test_metric_matrix_rejects_unknown_axis(tmp_path):
    scan = _scan_2d(tmp_path)
    with pytest.raises(ScanError, match='不在扫描参数里'):
        scan.metric_matrix('S21@330', 'nope', 'width')


def test_series_for_groups_by_other_axes(tmp_path):
    scan = _scan_2d(tmp_path)
    groups = scan.series_for('S21@330', 'length')
    assert set(groups) == {(10,), (14,)}          # 另一轴 width 的两个取值
    xs, ys = groups[(10,)]
    assert xs == [16, 18, 20]
    assert ys == [-48.0, -54.0, -60.0]


# ============================================================
# 6. 导出与出图
# ============================================================

def test_export_csv_row_count_equals_combinations(tmp_path):
    """判据改写后的形式之一：**CSV 行数 == 组合数**。"""
    scan = _scan_2d(tmp_path)
    p = scan.export_csv(str(tmp_path / 'scan.csv'))
    rows = list(csv.reader(open(p, encoding='utf-8-sig')))
    assert len(rows) - 1 == scan.n_combinations == 6
    header = rows[0]
    assert header[:4] == ['index', 'name', 'status', 'cst_path']
    assert 'length' in header and 'width' in header and 'S21@330' in header


def test_export_csv_includes_failures(tmp_path):
    def flaky(p):
        if p.params['length'] == 18:
            raise RuntimeError('boom')
        return {'m': 1.0}

    scan = ParameterScan(_base(), {'length': [16, 18]}, runner=flaky,
                         workdir=str(tmp_path)).run()
    p = scan.export_csv(str(tmp_path / 's.csv'))
    rows = list(csv.reader(open(p, encoding='utf-8-sig')))
    assert len(rows) == 3
    assert any('error' in r for r in rows[1:])


def test_plot_heatmap_labels_equal_axis_values(tmp_path):
    """判据改写后的形式之一：**热力图行列标签就是扫描轴取值**。"""
    scan = _scan_2d(tmp_path)
    p = scan.plot_heatmap(str(tmp_path / 'h.html'))
    html = open(p, encoding='utf-8').read()
    for value in ('16', '18', '20', '10', '14'):
        assert f'>{value}<' in html
    assert '<svg' in html and 'http' not in html.replace('http-equiv', '')


def test_plot_heatmap_needs_two_axes(tmp_path):
    scan = ParameterScan(_base(), {'length': [16, 18]},
                         runner=_simple_runner(), workdir=str(tmp_path)).run()
    with pytest.raises(ScanError, match='两个参数轴'):
        scan.plot_heatmap(str(tmp_path / 'h.html'))


def test_plot_curve_works_for_one_axis(tmp_path):
    scan = ParameterScan(_base(), {'length': [16, 18, 20]},
                         runner=_simple_runner(), workdir=str(tmp_path)).run()
    p = scan.plot_curve(str(tmp_path / 'c.html'))
    html = open(p, encoding='utf-8').read()
    assert '<polyline' in html and 'S21@330' in html


def test_report_contains_points_table_and_failures(tmp_path):
    def flaky(p):
        if p.params['length'] == 18:
            raise RuntimeError('boom')
        return {'m': 1.0}

    scan = ParameterScan(_base(), {'length': [16, 18]}, runner=flaky,
                         workdir=str(tmp_path)).run()
    p = scan.report(str(tmp_path / 'r.html'))
    html = open(p, encoding='utf-8').read()
    assert '扫描点' in html and 'boom' in html
    assert 'http' not in html.replace('http-equiv', '')


def test_repr_is_informative(tmp_path):
    scan = _scan_2d(tmp_path)
    text = repr(scan)
    assert '6 组合' in text and 'length' in text
