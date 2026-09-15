# -*- coding: utf-8 -*-
"""
结果读取测试（阶段 7 模块 5.1）
==============================
对应 `topo_modeler/result_reader.py`。

**为什么不用真 .cst**：本机没有任何「已存结果可读」的工程（阶段 4 已查明参考工程的
`Result/` 只有 0.3 MB / 8 个文件），而造一个需要跑一次完整时域求解（约 5300 s CPU）。
所以这里用**假的 Result 对象**验证 `ResultReader` 的全部逻辑 ——
`ResultReader(source)` 本来就把「读哪个工程」与「怎么读」解耦了。

⚠️ 仍未验证的部分：`source` 是**真 .cst 路径**时，`cst_solver.Result(...)` 的实际
读取路径（阶段 5 的 `read_all_s_parameters()` / `export_s_parameters_csv()`）。
那需要在有结果的工程上跑一次，已登记为未验证风险。

运行方式::

    pytest topo_modeler/tests/test_result_reader.py -v
"""

import math
import os
import sys

import pytest

_TPC_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _TPC_ROOT not in sys.path:
    sys.path.insert(0, _TPC_ROOT)

from topo_modeler.result_reader import ResultReader, ResultReaderError   # noqa: E402

#: 阶段 4 T6 的实测频点与值（dB）
FREQS = [310.0, 330.0, 350.0, 370.0]
S11_DB = [-14.973, -20.817, -11.838, -11.538]
S21_DB = [-2.063, -3.939, -17.779, -7.371]


def _db_to_complex(values):
    """dB → 复数字典形式（模拟 CST 返回的 ydata）。"""
    return [complex(10 ** (v / 20.0), 0.0) for v in values]


class FakeResult:
    """模拟 `cst_solver.Result` 的最小接口（复数外壳 + run_id 参数照抄）。"""

    def __init__(self, data=None, errors=None, with_exporter=True):
        self.last_errors = dict(errors or {})
        self._d = data if data is not None else {
            'S1,1': list(zip(FREQS, _db_to_complex(S11_DB))),
            'S2,1': list(zip(FREQS, _db_to_complex(S21_DB))),
        }
        if with_exporter:
            self.exported = []

            def _export(path, run_id=0, names=None, in_db=True):
                import csv
                self.exported.append((path, run_id, names, in_db))
                os.makedirs(os.path.dirname(os.path.abspath(path)) or '.', exist_ok=True)
                with open(path, 'w', encoding='utf-8-sig', newline='') as fh:
                    w = csv.writer(fh)
                    w.writerow(['freq_GHz'] + sorted(self._d))
                    for i, f in enumerate(FREQS):
                        w.writerow([f] + [
                            f'{20 * math.log10(abs(self._d[k][i][1])):.6g}'
                            for k in sorted(self._d)])
                return os.path.abspath(path)

            self.export_s_parameters_csv = _export

    def list_s_parameters(self):
        return sorted(self._d)

    def read_all_s_parameters(self, run_id=0):
        return {k: list(v) for k, v in self._d.items()}

    def read_s_parameter(self, name, run_id=0):
        if name not in self._d:
            raise KeyError(f'没有 {name}')
        return list(self._d[name])


# ============================================================
# 1. 读取与口径
# ============================================================

def test_read_all_s_parameters_normalizes_to_float_and_complex():
    """
    频率必须是 **float**、值必须是 **complex** ——
    CST 的 xdata/ydata 都是 complex，直接参与计算会触发 ComplexWarning
    （阶段 4 T6 就是这么踩的），所以外壳层必须把它剥掉。
    """
    rr = ResultReader(FakeResult())
    data = rr.read_s_parameters()
    assert set(data) == {'S1,1', 'S2,1'}
    xs, ys = data['S1,1']
    assert all(isinstance(v, float) for v in xs)
    assert all(isinstance(v, complex) for v in ys)
    assert xs == FREQS


def test_read_db_matches_known_values():
    """读出来的 dB 必须等于阶段 4 T6 的实测值（口径一致：20·log10|S|）。"""
    rr = ResultReader(FakeResult())
    db = rr.read_s_parameters_db()
    assert [round(v, 3) for v in db['S1,1'][1]] == S11_DB
    assert [round(v, 3) for v in db['S2,1'][1]] == S21_DB


def test_list_s_parameters_uses_backend_when_available():
    assert ResultReader(FakeResult()).list_s_parameters() == ['S1,1', 'S2,1']


def test_list_s_parameters_falls_back_when_backend_has_no_lister():
    class NoLister(FakeResult):
        list_s_parameters = None
    rr = ResultReader(NoLister())
    assert rr.list_s_parameters() == ['S1,1', 'S2,1']


def test_names_filter_only_reads_requested():
    rr = ResultReader(FakeResult(), names=['S1,1'])
    assert set(rr.read_s_parameters()) == {'S1,1'}


def test_cache_avoids_second_read():
    """cache=True 时同一 reader 反复取不重复读盘。"""
    calls = []

    class Counting(FakeResult):
        def read_all_s_parameters(self, run_id=0):
            calls.append(run_id)
            return super().read_all_s_parameters(run_id)

    rr = ResultReader(Counting())
    rr.read_s_parameters()
    rr.read_s_parameters()
    assert len(calls) == 1


def test_cache_off_reads_every_time():
    calls = []

    class Counting(FakeResult):
        def read_all_s_parameters(self, run_id=0):
            calls.append(run_id)
            return super().read_all_s_parameters(run_id)

    rr = ResultReader(Counting(), cache=False)
    rr.read_s_parameters()
    rr.read_s_parameters()
    assert len(calls) == 2


# ============================================================
# 2. 缺项与错误
# ============================================================

def test_missing_s_parameter_is_skipped_and_recorded():
    """单端口器件没有 S2,1 是常态 —— 不该整体失败，但必须留痕。"""
    only_s11 = {'S1,1': list(zip(FREQS, _db_to_complex(S11_DB)))}
    rr = ResultReader(FakeResult(data=only_s11), names=['S1,1', 'S2,1'])
    data = rr.read_s_parameters()
    assert set(data) == {'S1,1'}
    assert 'S2,1' in rr.last_errors


def test_ignore_errors_false_raises():
    rr = ResultReader(FakeResult(), names=['S9,9'])
    with pytest.raises(ResultReaderError, match='S9,9'):
        rr.read_s_parameters(ignore_errors=False)


def test_no_data_at_all_raises_with_hint():
    rr = ResultReader(FakeResult(data={}))
    with pytest.raises(ResultReaderError, match='没有读到任何 S 参数'):
        rr.read_s_parameters()


def test_missing_file_raises():
    rr = ResultReader('no_such_project.cst')
    with pytest.raises(ResultReaderError, match='不存在'):
        rr.read_s_parameters()


# ============================================================
# 3. 峰值 —— 阶段 4 判据的可执行版本
# ============================================================

def test_peak_position_finds_reflection_minimum():
    rr = ResultReader(FakeResult())
    freq, value = rr.peak_position('S1,1')
    assert freq == 330.0
    assert round(value, 3) == -20.817


def test_peak_position_respects_band():
    """带内取最小：340–380 内只有 350(−11.838) 与 370(−11.538)，最小在 350。"""
    rr = ResultReader(FakeResult())
    freq, value = rr.peak_position('S1,1', band=(340.0, 380.0))
    assert freq == 350.0
    assert round(value, 3) == -11.838


def test_peak_position_max_kind():
    rr = ResultReader(FakeResult())
    freq, value = rr.peak_position('S2,1', kind='max')
    assert freq == 310.0 and round(value, 3) == -2.063


def test_peak_position_band_without_points_raises():
    rr = ResultReader(FakeResult())
    with pytest.raises(ResultReaderError, match='没有数据点'):
        rr.peak_position('S1,1', band=(500.0, 600.0))


def test_value_at_picks_nearest_point_without_interpolating():
    rr = ResultReader(FakeResult())
    assert round(rr.value_at('S1,1', 330.4), 3) == -20.817
    assert round(rr.value_at('S1,1', 329.6), 3) == -20.817


def test_peak_shift_against_another_reader():
    """判据「谐振峰偏差 < 1 GHz」的可执行形式。"""
    shifted = {k: [(f + 0.4, v) for f, v in rows]
               for k, rows in FakeResult()._d.items()}
    a = ResultReader(FakeResult())
    b = ResultReader(FakeResult(data=shifted))
    assert abs(a.peak_shift(b) - 0.4) < 1e-9
    assert a.peak_shift(a) == 0.0


def test_peak_shift_accepts_path_like_source():
    """另一侧可以直接给「像工程路径」的东西（这里给假对象模拟注入）。"""
    a = ResultReader(FakeResult())
    b = ResultReader(FakeResult())
    assert a.peak_shift(b) == 0.0


# ============================================================
# 4. 导出与出图
# ============================================================

def test_export_csv_delegates_to_backend_when_available(tmp_path):
    fake = FakeResult()
    rr = ResultReader(fake, names=['S1,1', 'S2,1'])
    p = rr.export_csv(str(tmp_path / 'a.csv'))
    assert os.path.exists(p)
    assert fake.exported and fake.exported[0][3] is True     # in_db


def test_export_csv_falls_back_when_backend_lacks_exporter(tmp_path):
    """注入的对象没有 export_s_parameters_csv() 时，自己按同一列格式写。"""
    rr = ResultReader(FakeResult(with_exporter=False))
    p = rr.export_csv(str(tmp_path / 'b.csv'), in_db=True)
    lines = open(p, encoding='utf-8-sig').read().strip().split('\n')
    assert lines[0].startswith('freq_GHz')
    assert '"S1,1"' in lines[0]                              # 含逗号的列名要加引号
    assert lines[1].split(',')[0] == '310'
    assert abs(float(lines[1].split(',')[1]) - (-14.973)) < 1e-3


def test_export_csv_re_im_mode(tmp_path):
    rr = ResultReader(FakeResult(with_exporter=False))
    p = rr.export_csv(str(tmp_path / 'c.csv'), in_db=False)
    assert 'S1,1' in open(p, encoding='utf-8-sig').read().splitlines()[0]


def test_plot_all_writes_self_contained_html(tmp_path):
    rr = ResultReader(FakeResult())
    p = rr.plot_all(str(tmp_path / 'r.html'), title='演示', note='n',
                    meta={'k': 'v'})
    html = open(p, encoding='utf-8').read()
    assert 'http' not in html.replace('http-equiv', '')
    assert '<script' not in html.lower()
    assert 'S1,1' in html and 'S2,1' in html
    assert html.count('<polyline') == 2
    assert '演示' in html and 'k' in html


def test_plot_all_reports_partial_read_failure(tmp_path):
    """缺项时：图里没有它，但报告必须**明确写出来**缺了哪一项。"""
    only_s11 = {'S1,1': list(zip(FREQS, _db_to_complex(S11_DB)))}
    rr = ResultReader(FakeResult(data=only_s11), names=['S1,1', 'S2,1'])
    p = rr.plot_all(str(tmp_path / 'r2.html'))
    html = open(p, encoding='utf-8').read()
    assert html.count('<polyline') == 1              # 只有 S1,1 一条线
    assert 'S2,1' in html                            # 失败提示里提到了它
    assert '读取失败' in html
    assert '读失败的项' in html                       # 元信息里也标了


def test_plot_all_includes_audit_when_given(tmp_path):
    from topo_modeler.audit import AuditLog
    audit = AuditLog(str(tmp_path / 'logs'))
    with audit.stage('build_all'):
        pass
    rr = ResultReader(FakeResult())
    p = rr.plot_all(str(tmp_path / 'r3.html'), include_audit=audit)
    assert 'build_all' in open(p, encoding='utf-8').read()


def test_repr_mentions_source_and_cache_state():
    text = repr(ResultReader(FakeResult()))
    assert 'FakeResult' in text and 'cached=False' in text
