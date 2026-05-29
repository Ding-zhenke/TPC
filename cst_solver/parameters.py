# -*- coding: utf-8 -*-
"""
CST 参数管理 Mixin 模块
=======================
封装 CST 仿真参数、表达式参数的创建与修改

@author: PC
"""


class ParametersMixin:
    """
    CST 参数管理 Mixin
    提供参数存储、表达式设置、频率范围配置等功能
    """

    def para(self, name, value, log_flag=0):
        """
        在 CST 工程中创建/修改单个全局仿真参数

        :param name: str, 参数名称
        :param value: float/str, 参数赋值
        :param log_flag: int, 刷新标识 0-不刷新历史 1-全量刷新工程历史使参数立即生效
        """
        self.cst_file.model3d.StoreParameter(f"{name}", value)
        if log_flag == 1:
            self.cst_file.model3d.full_history_rebuild()

    def set_parameter(self, name, value, log_flag=0):
        """
        创建/修改单个参数（蛇形命名）
        等同于 para()

        :param name: str, 参数名称
        :param value: float/str, 参数值
        :param log_flag: int, 0-不刷新 1-全量刷新历史
        """
        self.para(name, value, log_flag)

    def paras(self, name, value, log_flag=0):
        """
        批量创建/修改全局仿真参数

        :param name: list[str] 或 dict, 参数名称列表或参数字典 {名称: 值, ...}
        :param value: list 或 None, 参数值列表（当 name 为 dict 时忽略）
        :param log_flag: int, 0-不刷新 1-全量刷新工程历史
        """
        self.cst_file.model3d.StoreParameters(name, value)
        if log_flag == 1:
            self.cst_file.model3d.full_history_rebuild()

    def set_parameters(self, name, value, log_flag=0):
        """
        批量创建/修改参数（蛇形命名）
        等同于 paras()
        """
        self.paras(name, value, log_flag)

    def expression(self, name, value):
        """
        创建/修改带表达式的参数（支持公式、关联其他参数）

        :param name: str, 表达式参数名称
        :param value: str, 表达式内容，如 'a*2+1', 'sqrt(b)'
        """
        self.cst_file.model3d.RestoreParameterExpression(f"{name}", f"{value}")

    def set_expression(self, name, value):
        """
        设置表达式参数（蛇形命名）
        等同于 expression()
        """
        self.expression(name, value)

    def freq_limit(self, fmin, fmax):
        """
        设置 CST 仿真的求解频率范围

        :param fmin: float/str, 起始频率
        :param fmax: float/str, 终止频率
        """
        f1 = """
        'Set Freq
        Solver.FrequencyRange %s, %s
        """ % (fmin, fmax)
        self.cst_file.model3d.add_to_history("Freq_range", f1)

    def set_frequency_range(self, fmin, fmax):
        """
        设置频率范围（蛇形命名）
        等同于 freq_limit()
        """
        self.freq_limit(fmin, fmax)

    def get_parameter(self, name):
        """
        获取指定参数的值
        :param name: str, 参数名称
        :return: 参数值
        """
        return self.cst_file.model3d.GetParameter(f"{name}")

    def delete_parameter(self, name):
        """
        删除指定参数
        :param name: str, 参数名称
        """
        self.cst_file.model3d.DeleteParameter(f"{name}")

    def rename_parameter(self, old_name, new_name):
        """
        重命名参数
        :param old_name: str, 原参数名
        :param new_name: str, 新参数名
        """
        self.cst_file.model3d.RenameParameter(f"{old_name}", f"{new_name}")
