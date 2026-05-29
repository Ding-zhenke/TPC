# -*- coding: utf-8 -*-
"""
CST 单位设置 Mixin 模块
=======================
封装 CST Units 对象的单位设置功能（频率、长度、时间等）

@author: PC
"""


class UnitsMixin:
    """
    CST 单位设置 Mixin
    提供全局单位（频率、长度、时间、温度等）的设置
    """

    def set_units(self, frequency='GHz', length='mm',
                  temperature='Celsius', time='ns',
                  voltage='V', current='A', resistance='Ohm',
                  inductance='nH', capacitance='pF'):
        """
        设置 CST 工程中的全局单位

        :param frequency: str, 频率单位，如 'GHz', 'MHz', 'Hz'
        :param length: str, 长度单位，如 'mm', 'cm', 'm', 'um', 'nm'
        :param temperature: str, 温度单位，如 'Celsius', 'Kelvin'
        :param time: str, 时间单位，如 'ns', 'ps', 's'
        :param voltage: str, 电压单位，如 'V', 'mV'
        :param current: str, 电流单位，如 'A', 'mA'
        :param resistance: str, 电阻单位，如 'Ohm'
        :param inductance: str, 电感单位，如 'nH', 'uH', 'H'
        :param capacitance: str, 电容单位，如 'pF', 'uF', 'F'
        """
        f1 = f"""With Units
     .Reset
     .Frequency "{frequency}"
     .Length "{length}"
     .Temperature "{temperature}"
     .Time "{time}"
     .Voltage "{voltage}"
     .Current "{current}"
     .Resistance "{resistance}"
     .Inductance "{inductance}"
     .Capacitance "{capacitance}"
End With"""
        self.cst_file.model3d.add_to_history("Set Units", f1)
