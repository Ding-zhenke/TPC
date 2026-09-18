# -*- coding: utf-8 -*-
r"""
报告导出（P3）：产物路径必须**唯一**、必须落在工作目录内
=========================================================

2026-09-17 用**真实曲线**跑 MCP 报告路径时发现：文件名是
``sparams-<时间戳>.csv`` / ``report-<时间戳>.html``，时间戳只到**秒** ——
同一秒内生成两份报告，第二份会**静默覆盖**第一份，而两次调用返回的产物路径
还是一模一样（调用方以为两份都在）。长驻的 MCP 服务里连续出报告就是这么丢数据的。

本文件钉住修好后的行为：

* 同一秒内的多份报告 → 路径互不相同，且**都真的存在**；
* 同一份报告的 CSV 与 HTML 共享同一个后缀（仍然配对）；
* 后缀用尽时退化成随机 token，而不是覆盖；
* 产物目录必须落在服务工作目录内（`workdir_escape`）。
"""

import os
import sys
from datetime import datetime
from unittest.mock import patch

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, '..', 'src'))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from cst_mcp import reporting as rep            # noqa: E402
from cst_mcp.errors import ToolError            # noqa: E402

_ANALYSIS = {
    'metric': 'S2,1',
    'criterion': {'threshold_db': -10.0, 'mode': 'below'},
    'n_bands': 1,
    'total_bandwidth_ghz': 5.0,
    'bands': [],
    'conventions': {},
}
_SERIES = {'freqs': [300.0, 301.0, 302.0],
           'columns': {'S2,1': [-5.0, -20.0, -6.0]}}


def _frozen_datetime():
    """固定到某一秒的 `datetime` 替身（时间戳冲突必须可复现，不能靠碰运气）。"""
    fake = type('FakeDatetime', (), {})
    fake.now = staticmethod(lambda *args, **kwargs: datetime(2026, 9, 17, 22, 58, 49))
    return fake


def _export(workdir, out_dir, title='报告'):
    return rep.export_report(analysis=_ANALYSIS, workdir=workdir, out_dir=out_dir,
                             series=_SERIES, title=title)


def test_same_second_reports_do_not_overwrite_each_other(tmp_path):
    out_dir = tmp_path / 'reports'
    with patch.object(rep, 'datetime', _frozen_datetime()):
        results = [_export(str(tmp_path), str(out_dir), title=f'报告{i}')
                   for i in range(3)]

    paths = [[artifact['path'] for artifact in result['artifacts']]
             for result in results]
    flat = [path for group in paths for path in group]
    assert len(set(flat)) == len(flat), f'产物路径撞车：{flat}'
    assert all(os.path.isfile(path) for path in flat), '有产物只是"报了路径"却没落盘'
    assert [os.path.basename(p) for p in paths[0]] == [
        'sparams-20260917-225849.csv', 'report-20260917-225849.html']
    assert [os.path.basename(p) for p in paths[1]] == [
        'sparams-20260917-225849-2.csv', 'report-20260917-225849-2.html']


def test_csv_and_html_share_the_same_suffix(tmp_path):
    out_dir = tmp_path / 'reports'
    with patch.object(rep, 'datetime', _frozen_datetime()):
        _export(str(tmp_path), str(out_dir))               # 占掉第一个名字
        result = _export(str(tmp_path), str(out_dir))

    names = sorted(os.path.basename(a['path']) for a in result['artifacts'])
    assert names == ['report-20260917-225849-2.html', 'sparams-20260917-225849-2.csv']


def test_unique_stamp_falls_back_to_a_token_when_exhausted(tmp_path):
    """后缀用尽时不能覆盖已有文件，退化成随机 token。"""
    out_dir = tmp_path / 'reports'
    out_dir.mkdir()
    for index in range(3):
        suffix = '' if index == 0 else f'-{index + 1}'
        (out_dir / f'report-20260917-225849{suffix}.html').write_text('x',
                                                                     encoding='utf-8')
    suffix = rep._unique_stamp(str(out_dir), '20260917-225849',
                               [('report', 'html')], limit=3)
    assert suffix.startswith('-') and len(suffix) > 2
    assert not (out_dir / f'report-20260917-225849{suffix}.html').exists()


def test_out_dir_outside_workdir_is_refused(tmp_path):
    """产物必须落在服务工作目录内（P2 的工作目录约束在 MCP 层同样生效）。"""
    workdir = tmp_path / 'work'
    workdir.mkdir()
    outside = tmp_path / 'outside'
    with pytest.raises(Exception) as caught:
        _export(str(workdir), str(outside))
    assert getattr(caught.value, 'code', None) == 'workdir_escape'


def test_generated_html_is_self_contained(tmp_path):
    out_dir = tmp_path / 'reports'
    result = _export(str(tmp_path), str(out_dir))
    html_path = [a['path'] for a in result['artifacts'] if a['kind'] == 'html'][0]
    text = open(html_path, encoding='utf-8', errors='replace').read()
    assert 'S2,1' in text                      # 指标名进报告
    assert 'http://' not in text and 'https://' not in text   # 零 CDN
