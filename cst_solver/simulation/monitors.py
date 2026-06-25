# -*- coding: utf-8 -*-
"""
CST 监视器 Mixin 模块
=====================
封装 Monitor、Probe 等场/信号监视器的创建

@author: PC
"""


class MonitorMixin:
    """CST 监视器 Mixin，提供场监视器、二维监视器、探针创建功能。"""

    # ---- 场/远场监视器 ----

    _FIELD_CONFIG = {
        'E':       {'type': 'Efield',   'name_fmt': 'e-field (f={})'},
        'H':       {'type': 'Hfield',   'name_fmt': 'h-field (f={})'},
        'Farfield': {'type': 'Farfield', 'name_fmt': 'farfield (f={})'},
    }

    def define_monitor(self, name, freq):
        """创建场监视器（兼容器旧代码）"""
        cfg = self._FIELD_CONFIG[name]
        extra_lines = ''
        if name == 'Farfield':
            extra_lines = '''
        .SetSubvolumeOffset "10", "10", "10", "10", "10", "10"
        .SetSubvolumeInflateWithOffset "False"
        .SetSubvolumeOffsetType "FractionOfWavelength"
        .EnableNearfieldCalculation "True"'''

        for i in freq:
            vba = f"""With Monitor 
        .Reset 
        .Name "{cfg['name_fmt'].format(i)}" 
        .Domain "Frequency" 
        .FieldType "{cfg['type']}" 
        .MonitorValue "{i}" 
        .UseSubvolume "False" 
        .Coordinates "Structure" 
        .SetSubvolume "0", "0", "0", "0", "0", "0" 
        .SetSubvolumeOffset "0.0", "0.0", "0.0", "0.0", "0.0", "0.0" 
        .SetSubvolumeInflateWithOffset "False"{extra_lines}
        .Create 
    End With"""
            self.cst_file.model3d.add_to_history(
                f"Define {name} Monitor (f={i}) ", vba)

    def create_field_monitor(self, monitor_type, frequencies):
        """创建场监视器（蛇形命名，同 define_monitor）"""
        self.define_monitor(monitor_type, frequencies)

    # ---- 二维监视器 ----

    def _get_model_bbox(self):
        """尝试获取模型外边界 [xmin,xmax,ymin,ymax,zmin,zmax]。
        若无法通过 COM 获取，返回 None 表示不限制子体积。
        """
        try:
            bb = self.cst_file.modeler.GetBoundingBox()
            return list(bb)
        except AttributeError:
            return None

    def monitor2d(self, name, frequencies,
                  plane_normal='z', plane_position=0):
        """
        创建二维监视器（支持单频/多频，可选切平面）

        :param name: str, 监视器名称，自动推断 field_type:
                     'E' → Efield, 'H' → Hfield, 其他 → Efield
        :param frequencies: float | list, 单个频点或频点列表
        :param plane_normal: str | None, 切平面法向 'x'/'y'/'z'，None/False 时不启用
        :param plane_position: float | None, 切平面位置（plane_normal 默认获取0）
        """
        freq_list = [frequencies] if isinstance(frequencies, (int, float)) else list(frequencies)
        # 从 name 推断 field_type
        cst_field = {'E': 'Efield', 'H': 'Hfield', 'Both': 'Both'}.get(name.upper(), 'Efield')
        use_plane = bool(plane_normal)


        for freq in freq_list:
            lines = [
                "With Monitor",
                "  .Reset",
                f'  .Name "{name} (f={freq})"',
                '  .Domain "Frequency"',
                f'  .FieldType "{cst_field}"',
                f'  .MonitorValue "{freq}"',
            ]

            if use_plane:
                lines += [
                    '  .UseSubvolume "True"',
                    '  .Coordinates "Structure"',
                    '  .SetSubvolumeOffset "0.0", "0.0", "0.0", "0.0", "0.0", "0.0"',
                    '  .SetSubvolumeInflateWithOffset "False"',
                ]
            else:
                lines.append('  .UseSubvolume "False"')

            if use_plane:
                pos = plane_position if plane_position is not None else 0
                lines += [
                    f'  .PlaneNormal "{plane_normal.lower()}"',
                    f'  .PlanePosition "{pos}"',
                ]

            lines += ['.Create', 'End With']
            self.cst_file.model3d.add_to_history(
                f"2D Monitor: {name} (f={freq})", '\n'.join(lines))

    # ---- 探针 ----

    def create_probe(self, name, position, frequency=None, field_type='E'):
        """创建探针监视器"""
        freq_line = f'\n            .MonitorValue "{frequency}"' if frequency else ''
        vba = f"""With Probe
     .Reset
     .Name "{name}"
     .FieldType "{field_type}"
     .Xposition "{position[0]}"
     .Yposition "{position[1]}"
     .Zposition "{position[2]}"
     {freq_line}
     .Create
End With"""
        self.cst_file.model3d.add_to_history(f"Probe: {name}", vba)
