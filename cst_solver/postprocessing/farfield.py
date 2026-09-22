# -*- coding: utf-8 -*-
"""
CST 远场后处理 Mixin 模块
==========================
封装 FarfieldPlot、FarfieldCalculator 等远场分析功能

@author: PC
"""

import csv
import os
import tempfile

import numpy as np

from cst_solver._guards import get_guard_state


class FarfieldMixin:
    """
    CST 远场后处理 Mixin
    提供远场方向图绘制、远场计算等功能
    """

    @property
    def farfield_plot(self):
        """获取 FarfieldPlot 对象"""
        return self.cst_file.model3d.FarfieldPlot

    def set_farfield_plot(self, plottype='3d', plotmode='realized gain',
                          frequency=None, require_gain=False):
        """
        设置远场方向图绘制参数

        ⚠️ 守卫层（陷阱 T8）：``plotmode`` 会做白名单校验；
        ``'efield'`` 画的是 **Abs(E)**，不能当增益证据；
        要用作增益结论请传 ``require_gain=True`` 强制只接受
        ``'directivity'`` / ``'gain'`` / ``'realized gain'``。

        :param plottype: str, 'polar'/'cartesian'/'2d'/'2dortho'/'3d'
        :param plotmode: str, 绘制模式
        :param frequency: float 可选, 频率
        :param require_gain: bool, True 表示这次绘图要当增益证据用
        """
        get_guard_state(self).check_farfield_mode(
            plotmode, require_gain=require_gain, where='set_farfield_plot()')
        fp = self.farfield_plot
        fp.Reset()
        fp.Plottype(plottype)
        fp.SetPlotMode(plotmode)
        if frequency:
            fp.Frequency(frequency)
        fp.Plot()

    def compute_farfield_array(self, array_type='rectangular',
                               element_count=(2, 2),
                               spacing=(0.5, 0.5)):
        """
        计算阵列天线的远场方向图

        :param array_type: str, 阵列类型 'rectangular'/'circular'
        :param element_count: tuple, 阵元数量 (nx, ny)
        :param spacing: tuple, 阵元间距 (dx, dy)，单位波长
        """
        f1 = f"""With FarfieldArray
     .Reset
     .ArrayType "{array_type}"
     .ElementCountX "{element_count[0]}"
     .ElementCountY "{element_count[1]}"
     .SpacingX "{spacing[0]}"
     .SpacingY "{spacing[1]}"
     .Execute
End With"""
        self.cst_file.model3d.add_to_history("FarfieldArray", f1)

    # ============================================================
    # 远场方向图读取与物理指标（DE 侧，真机验证 2026-09）
    # ============================================================

    def _prepare_farfield_plot(self, tree_item, plottype='3d',
                               plotmode='realized gain', step=1.0):
        """选中远场监视器并配置 FarfieldPlot，返回该对象。

        :param tree_item: str，'farfield (f=314) [1]' 或 'Farfields\\...'
        :param step: float，角度采样步长（度），默认 1°（避免 5° 欠采样）
        """
        get_guard_state(self).check_farfield_mode(
            plotmode,
            require_gain=plotmode in ('gain', 'realized gain', 'directivity'),
            where='read_farfield()')
        full_item = (tree_item if tree_item.startswith('Farfields')
                     else 'Farfields\\' + tree_item)
        model = self.cst_file.model3d
        model.SelectTreeItem(full_item)
        fp = model.FarfieldPlot
        fp.Reset()
        fp.Plottype(plottype)
        fp.SetPlotMode(plotmode)
        if step is not None and float(step) > 0:
            fp.Step(float(step))
        fp.Plot()
        return fp

    @staticmethod
    def _parse_ascii_export(path):
        """解析 FarfieldPlot ASCIIExport 输出为结构化数组。

        导出列固定为：Theta, Phi, Abs(Grlz/Gain/Directivity)[dBi],
        Abs(Theta)[dBi], Phase(Theta)[deg],
        Abs(Phi)[dBi], Phase(Phi)[deg], Ax.Ratio[dB]。
        行序为 φ 固定、θ 内扫（φ 外循环）。
        """
        rows = []
        with open(path, errors='replace') as fh:
            for line in fh:
                parts = line.split()
                if len(parts) >= 8:
                    try:
                        rows.append([float(x) for x in parts[:8]])
                    except ValueError:
                        continue
        if not rows:
            raise ValueError(f"远场导出文件里没有解析出数据：{path}")
        arr = np.asarray(rows)
        theta = np.unique(arr[:, 0])
        phi = np.unique(arr[:, 1])
        nphi, ntheta = len(phi), len(theta)
        if arr.shape[0] != nphi * ntheta:
            # 非规整网格时仍返回一维表，shape 留 None
            return {'theta_flat': arr[:, 0], 'phi_flat': arr[:, 1],
                    'gain_flat': arr[:, 2],
                    'theta_cut_flat': arr[:, 3], 'phase_theta_flat': arr[:, 4],
                    'phi_cut_flat': arr[:, 5], 'phase_phi_flat': arr[:, 6],
                    'axial_ratio_flat': arr[:, 7],
                    'theta': theta, 'phi': phi, 'gain': None}
        # 行序 φ外θ内 → 重排成 (nθ, nφ)
        gain = arr[:, 2].reshape(nphi, ntheta).T
        theta_cut = arr[:, 3].reshape(nphi, ntheta).T
        phi_cut = arr[:, 5].reshape(nphi, ntheta).T
        axial = arr[:, 7].reshape(nphi, ntheta).T
        return {'theta': theta, 'phi': phi, 'gain': gain,
                'theta_component': theta_cut, 'phi_component': phi_cut,
                'axial_ratio': axial, 'table': arr}

    def read_farfield(self, tree_item, plotmode='realized gain',
                      step=1.0, temp_file=None):
        """读取一个远场监视器的完整角度口径（经 DE 的 ASCIIExport）。

        这是远场数据的**权威口径**：``2D/3D Results`` 下没有远场云图、
        ``.dat`` 原始扫描口径稀疏（5° 网格下 φ 方向锯齿伪影），
        朴素反推不可靠；经 FarfieldPlot/ASCIIExport 的值与 CST Tables 一致
        （2026-09 真机验证）。

        :param tree_item: str，如 ``'farfield (f=314) [1]'``
        :param plotmode: str，默认 ``'realized gain'``
        :param step: float，角度步长（度），默认 1.0
        :param temp_file: str 可选，ASCII 导出中转文件路径；缺省用临时文件
        :return: dict，键：
            - ``theta``/``phi``：np.ndarray 角度轴
            - ``gain``：(nθ, nφ) 增益（dBi），按 plotmode
            - ``theta_component``/``phi_component``：分量幅度（dBi）
            - ``axial_ratio``：轴比（dB）
            - ``table``：原始 8 列导出表
        """
        self._prepare_farfield_plot(tree_item, plottype='3d',
                                    plotmode=plotmode, step=step)
        cleanup = False
        if temp_file is None:
            fd, temp_file = tempfile.mkstemp(prefix='cst_farfield_', suffix='.txt')
            os.close(fd)
            cleanup = True
        try:
            ae = self.cst_file.model3d.ASCIIExport
            ae.Reset()
            ae.FileName(temp_file)
            ae.Execute()
            return self._parse_ascii_export(temp_file)
        finally:
            if cleanup:
                try:
                    os.remove(temp_file)
                except OSError:
                    pass

    def get_farfield_metrics(self, tree_item, plotmode='realized gain',
                             step=1.0):
        """取远场物理指标（CST 权威计算值，经 FarfieldPlot）。

        :param tree_item: str，如 ``'farfield (f=314) [1]'``
        :param plotmode: str，默认 ``'realized gain'``
        :param step: float，角度步长（度），默认 1.0（主瓣方向对步长敏感）
        :return: dict，键：
            - ``gain_max``：立体角最大增益（dBi）
            - ``main_lobe_vector``：归一化 (vx, vy, vz)
            - ``main_lobe_theta``/``main_lobe_phi``：球角（度）
        """
        fp = self._prepare_farfield_plot(tree_item, plottype='3d',
                                         plotmode=plotmode, step=step)
        gain_max = float(fp.GetMax())
        _ok, vx, vy, vz = fp.GetMainLobeVector()
        norm = float(np.sqrt(vx * vx + vy * vy + vz * vz)) or 1.0
        vx, vy, vz = vx / norm, vy / norm, vz / norm
        main_theta = float(np.rad2deg(np.arccos(np.clip(vz, -1.0, 1.0))))
        main_phi = float(np.rad2deg(np.arctan2(vy, vx)) % 360.0)
        return {'gain_max': gain_max,
                'main_lobe_vector': (vx, vy, vz),
                'main_lobe_theta': main_theta,
                'main_lobe_phi': main_phi}

    def export_farfield_csv(self, tree_item, save_path,
                            plotmode='realized gain', step=1.0,
                            delimiter=',', encoding='utf-8-sig'):
        """导出远场完整角度口径到 CSV（θ/φ 长表，经 DE）。

        输出列：``theta_deg, phi_deg, gain_dBi, theta_component_dBi,
        phi_component_dBi, axial_ratio_dB``。
        增益与主瓣方向与 CST Tables 一致（2026-09 真机验证，
        314 GHz：max 10.51 dBi @ θ90/φ127，参考 10.509）。

        要在不打开 DE 的情况下离线读取，请使用 :class:`cst_solver.Result`
        的 S 参数/1D 接口；离线没有可靠的远场增益导出路径。

        :param tree_item: str，如 ``'farfield (f=314) [1]'``
        :param save_path: str，输出 CSV
        :param plotmode: str，默认 ``'realized gain'``
        :param step: float，角度步长（度），默认 1.0
        :return: str，写出的 CSV 绝对路径
        """
        data = self.read_farfield(tree_item, plotmode=plotmode, step=step)
        save_path = os.path.abspath(save_path)
        with open(save_path, 'w', newline='', encoding=encoding) as fh:
            writer = csv.writer(fh, delimiter=delimiter)
            writer.writerow(['theta_deg', 'phi_deg', 'gain_dBi',
                             'theta_component_dBi', 'phi_component_dBi',
                             'axial_ratio_dB'])
            tbl = data['table']
            for row in tbl:
                writer.writerow(['%.10g' % row[0], '%.10g' % row[1],
                                 '%.10g' % row[2], '%.10g' % row[3],
                                 '%.10g' % row[5], '%.10g' % row[7]])
        return save_path
