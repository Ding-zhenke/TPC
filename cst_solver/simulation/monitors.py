# -*- coding: utf-8 -*-
"""
CST 监视器 Mixin 模块
=====================
封装 Monitor、Probe、TimeMonitor 等场/信号监视器的创建

@author: PC
"""


class MonitorMixin:
    """
    CST 监视器 Mixin
    提供电场、磁场、远场、探针、时域监视器等创建功能
    """

    def define_monitor(self, name, freq):
        """
        创建场监视器
        保留原函数名以兼容旧代码

        :param name: str, 监视器类型 'E'-电场 'H'-磁场 'Farfield'-远场
        :param freq: list, 需要采集场分布的频率点集合
        """
        if name == 'E':
            for i in freq:
                f1 = f"""With Monitor 
        .Reset 
        .Name "e-field (f={i})" 
        .Domain "Frequency" 
        .FieldType "Efield" 
        .MonitorValue "{i}" 
        .UseSubvolume "False" 
        .Coordinates "Structure" 
        .SetSubvolume "0", "0", "0", "0", "0", "0" 
        .SetSubvolumeOffset "0.0", "0.0", "0.0", "0.0", "0.0", "0.0" 
        .SetSubvolumeInflateWithOffset "False" 
        .Create 
    End With"""
                self.cst_file.model3d.add_to_history(
                    f"Define {name} Monitor (f={i}) ", f1)
        elif name == 'H':
            for i in freq:
                f1 = f"""With Monitor 
        .Reset 
        .Name "h-field (f={i})" 
        .Domain "Frequency" 
        .FieldType "Hfield" 
        .MonitorValue "{i}" 
        .UseSubvolume "False" 
        .Coordinates "Structure" 
        .SetSubvolume "0", "0", "0", "0", "0", "0" 
        .SetSubvolumeOffset "0.0", "0.0", "0.0", "0.0", "0.0", "0.0" 
        .SetSubvolumeInflateWithOffset "False" 
        .Create 
    End With"""
                self.cst_file.model3d.add_to_history(
                    f"Define {name} Monitor (f={i}) ", f1)
        elif name == 'Farfield':
            for i in freq:
                f1 = f"""With Monitor 
        .Reset 
        .Name "farfield (f={i})" 
        .Domain "Frequency" 
        .FieldType "Farfield" 
        .MonitorValue "{i}" 
        .UseSubvolume "False" 
        .Coordinates "Structure" 
        .SetSubvolume "0", "0", "0", "0", "0", "0" 
        .SetSubvolumeOffset "10", "10", "10", "10", "10", "10" 
        .SetSubvolumeInflateWithOffset "False" 
        .SetSubvolumeOffsetType "FractionOfWavelength" 
        .EnableNearfieldCalculation "True" 
        .Create 
    End With"""
                self.cst_file.model3d.add_to_history(
                    f"Define {name} Monitor (f={i}) ", f1)

    def create_field_monitor(self, monitor_type, frequencies):
        """
        创建场监视器（蛇形命名）
        等同于 define_monitor()

        :param monitor_type: str, 'E'/'H'/'Farfield'
        :param frequencies: list, 频率点列表
        """
        self.define_monitor(monitor_type, frequencies)

    def create_probe(self, name, position, frequency=None, field_type='E'):
        """
        创建探针监视器

        :param name: str, 探针名称
        :param position: list, 探针位置 [X, Y, Z]
        :param frequency: float 可选, 监视频率
        :param field_type: str, 'E'/'H'/'Both'
        """
        freq_line = ""
        if frequency:
            freq_line = f'\n            .MonitorValue "{frequency}"'
        f1 = f"""With Probe
     .Reset
     .Name "{name}"
     .FieldType "{field_type}"
     .Xposition "{position[0]}"
     .Yposition "{position[1]}"
     .Zposition "{position[2]}"
     {freq_line}
     .Create
End With"""
        self.cst_file.model3d.add_to_history(f"Probe: {name}", f1)
