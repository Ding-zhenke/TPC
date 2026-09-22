# -*- coding: utf-8 -*-
"""DE 侧远场读取/导出的单元测试（mock，不启动 CST）。

覆盖 2026-09 真机验证后落地的接口：
- FarfieldMixin.read_farfield / get_farfield_metrics / export_farfield_csv
- pattern_export 必须把 step 下发给 FarfieldPlot（历史欠采样根因）
- 离线 Result.export_farfield_csv 明确 NotImplementedError
"""
import csv
import math

import numpy as np
import pytest

from cst_solver.postprocessing.farfield import FarfieldMixin
from cst_solver.import_export.io import IOMixin


# ---------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------

class _FakeFarfieldPlot:
    def __init__(self, model):
        self._model = model
        self.plottype = None
        self.plotmode = None
        self.step = None
        self._peak_phi_deg = 127.0

    def Reset(self):
        self.plottype = None
        self.plotmode = None
        self.step = None

    def Plottype(self, t):
        self.plottype = t

    def SetPlotMode(self, m):
        self.plotmode = m

    def Step(self, s):
        self.step = float(s)

    def Plot(self):
        self._model.plotted.append((self.plottype, self.plotmode, self.step))

    def GetMax(self):
        # 步长越细峰值越接近真值（模拟真机 5°→9.77, 1°→10.509）
        return 10.5092 if self.step is not None and self.step <= 1.0 else 9.7715

    def GetMainLobeVector(self):
        phi = math.radians(self._peak_phi_deg)
        return True, math.cos(phi), math.sin(phi), 0.0


class _FakeAsciiExport:
    """Execute 时把 FarfieldPlot 当前步长对应的合成方向图写到目标文件。"""

    def __init__(self, model):
        self._model = model
        self._file = None

    def Reset(self):
        self._file = None

    def FileName(self, p):
        self._file = p

    def Execute(self):
        fp = self._model.farfield_plot_obj
        step = fp.step if fp.step is not None else 5.0
        theta = np.arange(0.0, 180.0 + step / 2, step)
        phi = np.arange(0.0, 360.0, step)
        peak = math.radians(fp._peak_phi_deg)
        with open(self._file, "w", encoding="utf-8") as fh:
            fh.write("Theta [deg.]  Phi [deg.]  Abs(Grlz)[dBi]\n")
            fh.write("-" * 80 + "\n")
            for p_deg in phi:
                for t_deg in theta:
                    ang = math.atan2(
                        math.sin(math.radians(p_deg) - peak),
                        math.cos(math.radians(p_deg) - peak))
                    g = 10.5092 - 30.0 * (ang / math.pi) ** 2
                    if abs(t_deg - 90.0) > 1e-9:
                        g -= 20.0 * ((t_deg - 90.0) / 90.0) ** 2
                    fh.write(f"{t_deg:8.2f} {p_deg:8.2f} {g:12.4f} "
                             f"-30 0 -30 0 20\n")


class _FakeModel3D:
    def __init__(self):
        self.selected = []
        self.plotted = []
        self.farfield_plot_obj = _FakeFarfieldPlot(self)

    def SelectTreeItem(self, path):
        self.selected.append(path)

    @property
    def FarfieldPlot(self):
        return self.farfield_plot_obj

    @property
    def ASCIIExport(self):
        return _FakeAsciiExport(self)


class _FakeCstFile:
    def __init__(self):
        self.model3d = _FakeModel3D()


class _FarfieldHost(FarfieldMixin, IOMixin):
    def __init__(self):
        self.cst_file = _FakeCstFile()


@pytest.fixture
def host():
    return _FarfieldHost()


# ---------------------------------------------------------------
# read_farfield
# ---------------------------------------------------------------

def test_read_farfield_grid_shape_and_axis(host):
    data = host.read_farfield("farfield (f=314) [1]", step=10.0)
    # theta 0..180 step10 → 19；phi 0..350 step10 → 36
    assert data["theta"].shape == (19,)
    assert data["phi"].shape == (36,)
    assert data["gain"].shape == (19, 36)
    assert host.cst_file.model3d.selected == [
        r"Farfields\farfield (f=314) [1]"]


def test_read_farfield_full_path_not_double_prefixed(host):
    host.read_farfield(r"Farfields\farfield (f=290) [1]", step=30.0)
    assert host.cst_file.model3d.selected == [
        r"Farfields\farfield (f=290) [1]"]


def test_read_farfield_peak_at_expected_direction(host):
    data = host.read_farfield("farfield (f=314) [1]", step=1.0)
    i, j = np.unravel_index(np.argmax(data["gain"]), data["gain"].shape)
    assert data["theta"][i] == pytest.approx(90.0)
    assert data["phi"][j] == pytest.approx(127.0)
    assert data["gain"][i, j] == pytest.approx(10.5092, abs=0.01)


# ---------------------------------------------------------------
# get_farfield_metrics
# ---------------------------------------------------------------

def test_get_farfield_metrics_step1_matches_reference(host):
    m = host.get_farfield_metrics("farfield (f=314) [1]", step=1.0)
    assert m["gain_max"] == pytest.approx(10.5092, abs=1e-3)
    assert m["main_lobe_theta"] == pytest.approx(90.0, abs=1e-9)
    assert m["main_lobe_phi"] == pytest.approx(127.0, abs=1e-9)
    vx, vy, vz = m["main_lobe_vector"]
    assert vx * vx + vy * vy + vz * vz == pytest.approx(1.0, abs=1e-12)


def test_get_farfield_metrics_step5_undersamples(host):
    m = host.get_farfield_metrics("farfield (f=314) [1]", step=5.0)
    # 与真机一致：粗网格系统性偏低 ~0.7 dB
    assert m["gain_max"] == pytest.approx(9.7715, abs=1e-3)


# ---------------------------------------------------------------
# export_farfield_csv
# ---------------------------------------------------------------

def test_export_farfield_csv_long_table(host, tmp_path):
    out = tmp_path / "ff.csv"
    path = host.export_farfield_csv("farfield (f=314) [1]", str(out), step=30.0)
    assert path == str(out.resolve())
    with open(out, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.reader(fh))
    assert rows[0] == [
        "theta_deg", "phi_deg", "gain_dBi", "theta_component_dBi",
        "phi_component_dBi", "axial_ratio_dB"]
    # theta 0..180 step30 → 7；phi 0..330 step30 → 12
    assert len(rows) - 1 == 7 * 12
    first = rows[1]
    assert first[0] == "0" and first[1] == "0"


# ---------------------------------------------------------------
# pattern_export：step 必须下发（历史根因回归）
# ---------------------------------------------------------------

def test_pattern_export_applies_step(host, tmp_path):
    out = tmp_path / "p.txt"
    host.pattern_export("farfield (f=314) [1]", str(out), step=1.0)
    fp = host.cst_file.model3d.farfield_plot_obj
    assert fp.step == 1.0
    assert fp.plottype == "3d"
    assert fp.plotmode == "realized gain"


def test_pattern_export_default_step_is_one_degree(host, tmp_path):
    host.pattern_export("farfield (f=314) [1]", str(tmp_path / "p.txt"))
    assert host.cst_file.model3d.farfield_plot_obj.step == 1.0


# ---------------------------------------------------------------
# 离线 Result.export_farfield_csv：明确不支持
# ---------------------------------------------------------------

def test_offline_result_farfield_export_raises():
    from cst_solver._result_core import Result
    # 不实例化（避免打开工程）：直接在类上调用，先确认它抛 NotImplementedError
    with pytest.raises(NotImplementedError, match="setup.attach"):
        Result.export_farfield_csv(None, "x.csv")
