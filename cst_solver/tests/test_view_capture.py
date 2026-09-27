# -*- coding: utf-8 -*-
"""
3D 视图控制（Reset View）与截图封装的离线单测
================================================

覆盖 ``cst_solver.postprocessing.plot.PlotMixin`` 新增的即时 GUI 命令：

* reset_view / zoom_to_structure        —— Plot.ZoomToStructure（Reset View / Space）
* reset_view_to_selection               —— Plot.ZoomToSelectedStructure
* reset_zoom                            —— Plot.ResetZoom
* zoom_to_region                        —— Plot.ZoomToRegion(6 坐标)
* capture_3d_view / export_3d_image     —— Plot.ExportImage

这些命令**不进入建模历史树**（不走 add_to_history），测试用假的
``model3d.Plot`` 记录调用，并断言没有任何 ``add_to_history`` 下发。
"""

import os

import pytest

from cst_solver.postprocessing.plot import PlotMixin


class _FakePlot:
    """假的官方 Plot 动态 COM 对象，记录视图/截图方法的调用参数。"""

    def __init__(self, model):
        self._model = model

    def ZoomToStructure(self):
        self._model.calls.append(('ZoomToStructure',))

    def ZoomToSelectedStructure(self):
        self._model.calls.append(('ZoomToSelectedStructure',))

    def ResetZoom(self):
        self._model.calls.append(('ResetZoom',))

    def ZoomToRegion(self, xmin, ymin, zmin, xmax, ymax, zmax):
        self._model.calls.append(
            ('ZoomToRegion', (xmin, ymin, zmin, xmax, ymax, zmax)))

    def ExportImage(self, name, width, height):
        self._model.calls.append(('ExportImage', (name, width, height)))


class _FakeModel3D:
    def __init__(self):
        self.calls = []
        self.history = []
        self._plot = _FakePlot(self)

    @property
    def Plot(self):
        return self._plot

    def add_to_history(self, label, vba):
        # 新增的视图/截图命令绝不能进历史树；一旦进了就用例失败。
        self.history.append((label, vba))
        self.calls.append(('add_to_history', label))


class _FakeCstFile:
    def __init__(self):
        self.model3d = _FakeModel3D()


class _Host(PlotMixin):
    def __init__(self):
        self.cst_file = _FakeCstFile()


@pytest.fixture
def host():
    return _Host()


# ---------------------------------------------------------------
# Reset View 系列
# ---------------------------------------------------------------

def test_reset_view_calls_zoom_to_structure(host):
    host.reset_view()
    assert host.cst_file.model3d.calls == [('ZoomToStructure',)]


def test_zoom_to_structure_is_alias(host):
    host.zoom_to_structure()
    assert host.cst_file.model3d.calls == [('ZoomToStructure',)]


def test_reset_view_to_selection(host):
    host.reset_view_to_selection()
    assert host.cst_file.model3d.calls == [('ZoomToSelectedStructure',)]


def test_reset_zoom(host):
    host.reset_zoom()
    assert host.cst_file.model3d.calls == [('ResetZoom',)]


def test_zoom_to_region_passes_six_coords(host):
    host.zoom_to_region(-1, -2, -3, 4, 5, 6)
    assert host.cst_file.model3d.calls == [
        ('ZoomToRegion', (-1, -2, -3, 4, 5, 6))]


def test_zoom_to_region_accepts_expression_strings(host):
    host.zoom_to_region('-a/2', '0', '-h', 'a/2', 'bmax', 'h')
    (name, coords) = host.cst_file.model3d.calls[0]
    assert name == 'ZoomToRegion'
    assert coords == ('-a/2', '0', '-h', 'a/2', 'bmax', 'h')


@pytest.mark.parametrize('method_name', [
    'reset_view', 'zoom_to_structure', 'reset_view_to_selection',
    'reset_zoom', 'zoom_to_region'])
def test_view_commands_never_enter_history(host, method_name):
    if method_name == 'zoom_to_region':
        host.zoom_to_region(0, 0, 0, 1, 1, 1)
    else:
        getattr(host, method_name)()
    assert host.cst_file.model3d.history == []


# ---------------------------------------------------------------
# 截图 capture_3d_view
# ---------------------------------------------------------------

def test_capture_returns_absolute_path(host, tmp_path):
    out = tmp_path / 'view.png'
    returned = host.capture_3d_view(str(out), 800, 600)
    assert returned == os.path.abspath(str(out))
    assert host.cst_file.model3d.calls == [
        ('ExportImage', (os.path.abspath(str(out)), 800, 600))]


def test_capture_default_zero_size_uses_window(host, tmp_path):
    out = tmp_path / 'view.bmp'
    host.capture_3d_view(str(out))
    assert host.cst_file.model3d.calls == [
        ('ExportImage', (os.path.abspath(str(out)), 0, 0))]


@pytest.mark.parametrize('ext', ['.png', '.bmp', '.jpg', '.jpeg'])
def test_capture_accepts_supported_extensions(host, tmp_path, ext):
    out = tmp_path / f'view{ext}'
    host.capture_3d_view(str(out), 100, 100)
    assert host.cst_file.model3d.calls[0][0] == 'ExportImage'


def test_capture_uppercase_extension_normalized(host, tmp_path):
    out = tmp_path / 'VIEW.PNG'
    host.capture_3d_view(str(out), 100, 100)
    assert host.cst_file.model3d.calls[0][0] == 'ExportImage'


def test_capture_creates_missing_parent_dir(host, tmp_path):
    out = tmp_path / 'nested' / 'deep' / 'view.png'
    host.capture_3d_view(str(out), 100, 100)
    assert out.parent.is_dir()


def test_export_3d_image_is_alias(host, tmp_path):
    out = tmp_path / 'view.png'
    returned = host.export_3d_image(str(out), 640, 480)
    assert returned == os.path.abspath(str(out))
    assert host.cst_file.model3d.calls == [
        ('ExportImage', (os.path.abspath(str(out)), 640, 480))]


def test_capture_does_not_enter_history(host, tmp_path):
    host.capture_3d_view(str(tmp_path / 'view.png'), 100, 100)
    assert host.cst_file.model3d.history == []


# ---------------------------------------------------------------
# 截图参数校验（早失败，不发 VBA）
# ---------------------------------------------------------------

@pytest.mark.parametrize('bad_path', ['', '   '])
def test_capture_rejects_empty_path(host, bad_path):
    with pytest.raises(TypeError):
        host.capture_3d_view(bad_path)


def test_capture_rejects_non_string_path(host):
    with pytest.raises(TypeError):
        host.capture_3d_view(123)


@pytest.mark.parametrize('bad_ext', ['.gif', '.tif', '.tiff', '.pdf', '.exe'])
def test_capture_rejects_unsupported_extension(host, tmp_path, bad_ext):
    out = tmp_path / f'view{bad_ext}'
    with pytest.raises(ValueError):
        host.capture_3d_view(str(out))


def test_capture_rejects_no_extension(host, tmp_path):
    with pytest.raises(ValueError):
        host.capture_3d_view(str(tmp_path / 'view'))


@pytest.mark.parametrize('width, height', [(-1, 100), (100, -1), (-5, -5)])
def test_capture_rejects_negative_size(host, tmp_path, width, height):
    with pytest.raises(ValueError):
        host.capture_3d_view(str(tmp_path / 'view.png'), width, height)


def test_capture_rejects_only_one_nonzero_dimension(host, tmp_path):
    with pytest.raises(ValueError):
        host.capture_3d_view(str(tmp_path / 'view.png'), 800, 0)
    with pytest.raises(ValueError):
        host.capture_3d_view(str(tmp_path / 'view.png'), 0, 600)


@pytest.mark.parametrize('width, height', [(800.0, 600), ('800', 600),
                                          (True, 600)])
def test_capture_rejects_non_integer_size(host, tmp_path, width, height):
    with pytest.raises(TypeError):
        host.capture_3d_view(str(tmp_path / 'view.png'), width, height)


def test_validation_failure_does_not_call_plot(host, tmp_path):
    with pytest.raises(ValueError):
        host.capture_3d_view(str(tmp_path / 'view.gif'), 100, 100)
    # 校验失败时一条命令都不应下发
    assert host.cst_file.model3d.calls == []
