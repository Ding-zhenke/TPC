# -*- coding: utf-8 -*-
"""中文字体选择、局部样式恢复及缺字失败行为。"""

import io
import subprocess
import sys
import warnings

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
import pytest

from mesh_grid import plotting


def test_missing_font_is_explicit_and_does_not_change_style(monkeypatch):
    monkeypatch.delenv('TPC_CJK_FONT', raising=False)
    monkeypatch.setattr(plotting, '_covers', lambda path, text: False)
    before = dict(matplotlib.rcParams)
    with pytest.warns(UserWarning, match='TPC_CJK_FONT'):
        assert plotting.configure_chinese_font() is None
    assert dict(matplotlib.rcParams) == before
    with pytest.raises(RuntimeError, match='TPC_CJK_FONT'):
        plotting.configure_chinese_font(strict=True)


def test_font_path_must_exist(tmp_path):
    with pytest.raises(FileNotFoundError):
        plotting.configure_chinese_font(font_path=tmp_path / 'missing.ttf')


def test_latin_font_rejected_for_chinese():
    path = font_manager.findfont('DejaVu Sans')
    with pytest.raises(ValueError, match='中文'):
        plotting.configure_chinese_font(font_path=path)


def test_local_context_restores_style_even_on_error(monkeypatch):
    monkeypatch.delenv('TPC_CJK_FONT', raising=False)
    monkeypatch.setattr(plotting, '_covers', lambda path, text: True)
    before = dict(matplotlib.rcParams)
    with pytest.raises(ValueError, match='test error'):
        with plotting.chinese_plot_style(strict=True) as family:
            assert family
            assert matplotlib.rcParams['axes.unicode_minus'] is False
            assert matplotlib.rcParams['svg.fonttype'] == 'path'
            assert matplotlib.rcParams['pdf.fonttype'] == 42
            raise ValueError('test error')
    assert dict(matplotlib.rcParams) == before


def test_explicit_font_wins_over_environment(monkeypatch, tmp_path):
    # 验证优先级，不把此模拟当中文渲染证据。
    path = font_manager.findfont('DejaVu Sans')
    monkeypatch.setenv('TPC_CJK_FONT', str(tmp_path / 'not-found.ttf'))
    monkeypatch.setattr(plotting, '_covers', lambda path, text: True)
    with plotting.chinese_plot_style(font_path=path) as family:
        assert family == 'DejaVu Sans'


def test_importing_algorithms_does_not_override_fonts():
    code = '''
import matplotlib
matplotlib.use('Agg')
matplotlib.rcParams['font.family'] = ['DejaVu Sans']
before = dict(matplotlib.rcParams)
from mesh_grid import plotting
from mesh_grid.tri_grid import core
from tpc_toolkit import effective_medium
assert dict(matplotlib.rcParams) == before
'''
    run = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True)
    assert run.returncode == 0, run.stderr


def test_real_chinese_render_when_font_is_available(monkeypatch):
    monkeypatch.delenv('TPC_CJK_FONT', raising=False)
    try:
        with plotting.chinese_plot_style(text='中文字体检查频率透射系数曲线', strict=True):
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter('always')
                fig, ax = plt.subplots()
                try:
                    ax.plot([300, 320, 340], [-2, -3, -1], label='曲线')
                    ax.set(title='中文字体检查', xlabel='频率 (GHz)', ylabel='透射系数 (dB)')
                    ax.legend()
                    for fmt in ('png', 'pdf', 'svg'):
                        output = io.BytesIO()
                        fig.savefig(output, format=fmt)
                        assert output.tell() > 1000
                finally:
                    plt.close(fig)
                assert not [w for w in caught if 'Glyph' in str(w.message)]
    except RuntimeError as exc:
        if '未找到覆盖中文' in str(exc):
            pytest.skip('本机没有中文字体；选择和失败行为已由独立用例覆盖')
        raise
