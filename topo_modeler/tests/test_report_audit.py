# -*- coding: utf-8 -*-
"""
报告引擎与审计落盘测试（阶段 7 §3.2 / §3.3）
===========================================
对应 `topo_modeler/report.py` 与 `topo_modeler/audit.py`。

守住的硬约定
------------
1. **报告必须自包含**：生成的 HTML 里不能有任何 `http(s)://` 外链、`<script>`、`<link>`
   —— 断网、十年后都要能打开，这是「自包含」的定义，不是建议；
2. **审计失败不能拖垮主流程**：磁盘不可写时只记 `last_error`，不抛（`strict=True` 才抛）；
3. **参数存档不覆盖**：每次存档都是带时间戳的新文件。

⚠️ 全部用例都不碰 CST。

运行方式::

    pytest topo_modeler/tests/test_report_audit.py -v
"""

import json
import math
import os
import sys

import pytest

_TPC_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _TPC_ROOT not in sys.path:
    sys.path.insert(0, _TPC_ROOT)

from topo_modeler.audit import AuditLog, default_audit_dir   # noqa: E402
from topo_modeler.report import (                            # noqa: E402
    HtmlReport,
    report_from_s_parameters,
    report_from_s_parameters_csv,
    svg_heatmap,
    svg_line_chart,
    svg_polar,
    svg_timeline,
)


def _assert_self_contained(html_text: str):
    """自包含硬约定：无外链、无 JS、无外链 CSS。"""
    assert 'http://' not in html_text, '报告里出现了 http 外链'
    assert 'https://' not in html_text, '报告里出现了 https 外链'
    assert '<script' not in html_text.lower(), '报告里出现了 <script>'
    assert '<link' not in html_text.lower(), '报告里出现了 <link>'


# ============================================================
# 1. SVG 图元
# ============================================================

def test_line_chart_renders_polyline_per_series():
    svg = svg_line_chart([('S1,1', [1, 2, 3], [-10, -20, -15]),
                          ('S2,1', [1, 2, 3], [-1, -2, -3])],
                         title='t', xlabel='f', ylabel='dB')
    assert svg.startswith('<svg') and svg.rstrip().endswith('</svg>')
    assert svg.count('<polyline') == 2
    assert 'S1,1' in svg and 'S2,1' in svg


def test_line_chart_empty_is_graceful():
    assert '没有数据' in svg_line_chart([])


def test_line_chart_highlight_draws_reference_line():
    svg = svg_line_chart([('s', [1, 2, 3], [0, 1, 2])], highlight=[(2, 'f0')])
    assert 'stroke-dasharray' in svg and 'f0' in svg


def test_heatmap_cell_count_and_labels():
    svg = svg_heatmap([[1, 2], [3, 4]], ['a', 'b'], ['c', 'd'], title='h')
    assert svg.count('<rect') >= 4
    for lab in ('a', 'b', 'c', 'd'):
        assert f'>{lab}<' in svg


def test_heatmap_empty_is_graceful():
    assert '没有数据' in svg_heatmap([], [], [])


def test_polar_marks_peak():
    theta = [i * 30 for i in range(12)]
    vals = [-10.0] * 12
    vals[3] = 0.0
    svg = svg_polar(theta, vals, title='ff', rlabel='dBi')
    assert '<circle' in svg and '峰值' in svg
    assert '90' in svg                       # 峰值在 90°（theta[3]）
    assert svg.count('<text') > 8            # 角度标签


def test_timeline_renders_even_when_all_durations_are_zero():
    """
    回归：早先的实现在「所有步骤都短于计时精度」时返回『没有数据』——
    明明有记录却说没有数据。现在照画，并注明条宽用最小值。
    """
    svg = svg_timeline([{'tool': 'a', 'duration_s': 0.0, 'status': 'ok'},
                        {'tool': 'b', 'duration_s': 0.0, 'status': 'error'}])
    assert '没有数据' not in svg
    assert svg.count('<rect') >= 3           # 背景 + 两根条
    assert '低于 1 ms' in svg


def test_timeline_no_records_is_graceful():
    assert '没有' in svg_timeline([])


# ============================================================
# 2. 报告
# ============================================================

def test_report_is_self_contained_and_renders_all_blocks():
    rep = HtmlReport(title='报告', meta={'模型': 'wg', '拓扑': 'AB'})
    rep.add_s_parameters({'S1,1': ([1, 2], [-10, -20])}, note='附注')
    rep.add_heatmap([[1, 2], [3, 4]], ['x1', 'x2'], ['y1', 'y2'], title='扫描')
    rep.add_polar([0, 90, 180], [-5, 0, -8], title='远场')
    rep.add_table(['a'], [[1], [2]], caption='表')
    rep.add_note('注意', level='warn')
    html = rep.to_html()
    _assert_self_contained(html)
    assert html.startswith('<!DOCTYPE html>')
    for marker in ('S 参数', '扫描', '远场', '表', '注意', 'wg'):
        assert marker in html
    assert html.count('<svg') == 3


def test_report_write_creates_file(tmp_path):
    p = HtmlReport(title='t').add_note('hi').write(str(tmp_path / 'r.html'))
    assert os.path.exists(p)
    with open(p, encoding='utf-8') as fh:
        assert 'hi' in fh.read()


def test_report_escapes_html_in_user_text():
    """标题/元信息里的尖括号必须被转义（否则报告变成注入点）。"""
    rep = HtmlReport(title='<script>alert(1)</script>', meta={'k': '<b>x</b>'})
    html = rep.to_html()
    assert '<script' not in html.lower()
    assert '&lt;script&gt;' in html


def test_report_from_s_parameters_helper():
    rep = report_from_s_parameters({'S1,1': ([1, 2], [-10, -20])}, title='快速')
    _assert_self_contained(rep.to_html())


def test_report_accepts_complex_s_parameter_values():
    """CST 返回的是复数（dB 真值），报告要能直接吃。"""
    mag = 10 ** (-20 / 20)
    rep = HtmlReport(title='c')
    rep.add_s_parameters({'S1,1': [(1.0, complex(mag, 0)), (2.0, complex(mag, 0))]})
    html = rep.to_html()
    assert '-20' in html


def test_report_from_csv_round_trip(tmp_path):
    """阶段 5 的导出 → 阶段 7 的报告，一条链要通。"""
    csv_path = tmp_path / 's.csv'
    csv_path.write_text('freq_GHz,"S1,1","S2,1"\n'
                        '310,-14.973,-2.063\n330,-20.817,-3.939\n',
                        encoding='utf-8-sig')
    rep = report_from_s_parameters_csv(str(csv_path), title='csv 报告', note='n')
    html = rep.to_html()
    _assert_self_contained(html)
    assert 'S1,1' in html and 'S2,1' in html
    assert html.count('<polyline') == 2


def test_report_accepts_stage5_csv_with_bom(tmp_path):
    """
    阶段 5 的 `export_s_parameters_csv` 写的是 utf-8-sig（带 BOM），必须能读；
    并且含逗号的列名（`S1,1`）由 `csv.writer` 自动加引号 —— 这里照样写一份真的。
    """
    import csv as _csv
    csv_path = tmp_path / 'bom.csv'
    with open(csv_path, 'w', encoding='utf-8-sig', newline='') as fh:
        w = _csv.writer(fh)
        w.writerow(['freq_GHz', 'S1,1', 'S2,1'])
        w.writerow([310, -15.0, -2.0])
        w.writerow([330, -20.0, -3.0])
    raw = open(csv_path, encoding='utf-8-sig').read()
    assert '"S1,1"' in raw                      # 确实加了引号
    html = report_from_s_parameters_csv(str(csv_path)).to_html()
    assert 'S1,1' in html and html.count('<polyline') == 2


def test_report_meta_and_subtitle():
    rep = HtmlReport(title='T', subtitle='副标题', meta={'a': 1, 'b': 'x'})
    html = rep.to_html()
    assert '副标题' in html and '<dt>a</dt><dd>1</dd>' in html


# ============================================================
# 3. 审计
# ============================================================

def test_audit_record_writes_jsonl(tmp_path):
    a = AuditLog(str(tmp_path))
    a.record('build_all', status='ok', duration_s=1.25, model='wg')
    lines = open(a.jsonl_path, encoding='utf-8').read().strip().split('\n')
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec['tool'] == 'build_all'
    assert rec['status'] == 'ok'
    assert rec['duration_s'] == 1.25
    assert rec['model'] == 'wg'
    assert 'ts' in rec and 'epoch' in rec


def test_audit_stage_records_ok_and_error(tmp_path):
    a = AuditLog(str(tmp_path))
    with a.stage('step_ok'):
        pass
    with pytest.raises(ValueError):
        with a.stage('step_bad'):
            raise ValueError('boom')
    recs = a.read()
    by_tool = {r['tool']: r for r in recs}
    assert by_tool['step_ok']['status'] == 'ok'
    assert by_tool['step_bad']['status'] == 'error'
    assert 'boom' in by_tool['step_bad']['error']


def test_audit_disabled_writes_nothing(tmp_path):
    a = AuditLog(str(tmp_path), enabled=False)
    a.record('x')
    with a.stage('y'):
        pass
    assert a.archive_parameters({'a': 1}) is None
    assert a.write_production_chain() is None
    assert not os.path.exists(a.jsonl_path)


def test_audit_survives_unserializable_fields(tmp_path):
    """任意对象都要能进 JSON（转 repr），审计不该因为一个字段就失败。"""
    a = AuditLog(str(tmp_path))
    a.record('weird', obj=object(), arr=[[1, 2]], tup=(1, 2))
    rec = json.loads(open(a.jsonl_path, encoding='utf-8').read().strip())
    assert isinstance(rec['obj'], str)
    assert rec['arr'] == [[1, 2]]
    assert rec['tup'] == [1, 2]


def test_audit_archive_does_not_overwrite(tmp_path):
    a = AuditLog(str(tmp_path))
    p1 = a.archive_parameters({'x': 1}, name='cfg')
    p2 = a.archive_parameters({'x': 2}, name='cfg')
    assert p1 and p2 and p1 != p2
    assert json.load(open(p1, encoding='utf-8'))['params'] == {'x': 1}
    assert json.load(open(p2, encoding='utf-8'))['params'] == {'x': 2}


def test_audit_production_chain_contains_steps_and_slowest(tmp_path):
    a = AuditLog(str(tmp_path))
    a.record('fast', duration_s=0.1)
    a.record('slow', duration_s=12.5)
    a.record('bad', status='error', error='demo')
    p = a.write_production_chain()
    text = open(p, encoding='utf-8').read()
    assert '模型生产链' in text
    for name in ('fast', 'slow', 'bad'):
        assert f'`{name}`' in text
    assert '失败步骤' in text and 'demo' in text
    assert '最慢的 10 步' in text
    assert '12.5' in text


def test_audit_read_merges_memory_and_file(tmp_path):
    a = AuditLog(str(tmp_path))
    a.record('one')
    a2 = AuditLog(str(tmp_path))
    a2.record('two')
    tools = [r['tool'] for r in a2.read()]
    assert tools == ['one', 'two']


def test_audit_report_integration(tmp_path):
    """审计记录能直接进报告（`add_audit`）。"""
    a = AuditLog(str(tmp_path / 'logs'))
    with a.stage('build_all'):
        pass
    a.record('solve', status='error', error='demo')
    rep = HtmlReport(title='T')
    rep.add_audit(a)
    html = rep.to_html()
    _assert_self_contained(html)
    assert 'build_all' in html and 'demo' in html


def test_audit_strict_mode_raises_on_bad_path(tmp_path):
    """strict=True 时才允许把写盘失败抛出来。"""
    blocker = tmp_path / 'afile'
    blocker.write_text('x', encoding='utf-8')
    a = AuditLog(str(blocker / 'sub'), strict=True)      # 把「文件」当目录用 ⇒ 必失败
    with pytest.raises(RuntimeError):
        a.record('x')


def test_audit_default_dir_honours_env(monkeypatch):
    monkeypatch.setenv('TPC_AUDIT_DIR', os.path.join('_x', 'audit'))
    assert default_audit_dir().endswith(os.path.join('_x', 'audit'))
    assert os.path.isabs(default_audit_dir())
