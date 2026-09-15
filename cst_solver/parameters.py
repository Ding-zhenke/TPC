# -*- coding: utf-8 -*-
"""
CST 参数管理 Mixin 模块
=======================
封装 CST 仿真参数、表达式参数的创建与修改

@author: PC
"""

from cst_solver._guards import get_guard_state


class ParametersMixin:
    """
    CST 参数管理 Mixin
    提供参数存储、表达式设置、频率范围配置等功能
    """

    def _guard_geometry_probe(self):
        """
        守卫用的探针：工程里现在有没有几何。

        走官方公开 API ``Solid.GetNumberOfShapes()``（见
        ``docs/references/vba-official-reference.md`` 的 Solid 一节）。
        CST 调用失败时抛异常，由守卫自己吞掉并按「未知」处理。
        """
        return self.cst_file.model3d.Solid.GetNumberOfShapes() > 0

    def _guard_param_probe(self, name):
        """
        守卫用的探针：某个参数在工程里是否已经存在。

        用现成的 ``GetParameter()`` 读一次：读得到且非空 ⇒ 已存在。
        **读不到一律当作「新参数」** —— CST 对不存在的参数通常直接报错，
        而「当成新参数」的错误后果（漏一次提醒）远小于「当成已存在」的后果
        （在正常建模流水线里到处误报，把守卫变成一个会被忽略的噪音源）。
        """
        try:
            value = self.cst_file.model3d.GetParameter(name)
        except Exception:
            return False
        return value not in (None, '')

    def _guard(self):
        """取得（必要时创建）本实例的守卫状态，并接上两个探针。"""
        state = get_guard_state(self)
        if state._geometry_probe is None:
            state.attach_geometry_probe(self._guard_geometry_probe)
        if state._param_probe is None:
            state.attach_param_probe(self._guard_param_probe)
        return state

    def para(self, name, value, log_flag=0, expression=''):
        """
        在 CST 工程中创建/修改单个全局仿真参数

        ⚠️ ``log_flag=0``（默认）只把参数写进参数表，**不会**重建工程历史 ——
        **改一个已被几何引用的参数**时，几何不会随之变化，此时直接仿真会算到
        **旧几何**。守卫层（``cst_solver._guards``）会在 ``run()`` 前拦截或警告这种用法。

        :param name: str, 参数名称
        :param value: float/str, 参数赋值
        :param log_flag: int, 刷新标识 0-不刷新历史 1-全量刷新工程历史使参数立即生效
        :param expression: str, 参数说明文本（常用于备注），默认空字符串
        """
        state = self._guard()
        preexisting = state.param_existed(name)     # 必须在写入之前问

        self.cst_file.model3d.StoreParameter(f"{name}", value)
        if expression:
            self._set_parameter_description(name, expression)
        if log_flag == 1:
            self.cst_file.model3d.full_history_rebuild()
        state.mark_params_changed([name], rebuilt=(log_flag == 1),
                                  preexisting=[preexisting])

    def _set_parameter_description(self, name, description):
        """
        设置参数说明文本。

        不同 CST Python 接口版本对该能力暴露不一致，这里优先尝试
        直接 API，失败时回退到 VBA 历史命令。
        """
        try:
            self.cst_file.model3d.SetParameterDescription(
                f"{name}", f"{description}")
            return
        except Exception:
            pass

        cmd = f'''
        Parameter.SetDescription "{name}", "{description}"
        '''
        self.cst_file.model3d.add_to_history(
            f"Parameter description: {name}", cmd)

    def set_parameter(self, name, value, log_flag=0, expression=''):
        """
        创建/修改单个参数（蛇形命名）
        等同于 para()

        :param name: str, 参数名称
        :param value: float/str, 参数值
        :param log_flag: int, 0-不刷新 1-全量刷新历史
        :param expression: str, 参数表达式说明，默认空字符串
        """
        self.para(name, value, log_flag, expression)

    def paras(self, name, value, log_flag=0):
        """
        批量创建/修改全局仿真参数

        CST 的 ``StoreParameters`` 只接受**两个等长数组**
        （``string_array names, string_array values``），不接受字典，
        传入字典会报 ``type must be array, but is object``。
        本方法负责把字典形式归一化成两个数组再下发。

        :param name: list[str] 或 dict, 参数名称列表或参数字典 {名称: 值, ...}
        :param value: list 或 None, 参数值列表（当 name 为 dict 时可传 None）
        :param log_flag: int, 0-不刷新 1-全量刷新工程历史
        :raises ValueError: name 为 list 时 value 缺失或与 name 长度不一致
        """
        if isinstance(name, dict):
            names = [str(k) for k in name.keys()]
            values = [str(name[k]) for k in name.keys()]
        else:
            names = [str(k) for k in name]
            if value is None:
                raise ValueError(
                    "paras() 的 name 为列表时必须同时给出等长的 value 列表；"
                    "若要按 {名称: 值} 形式传参，请把字典直接传给 name")
            values = [str(v) for v in value]
            if len(values) != len(names):
                raise ValueError(
                    f"paras() 的 name 与 value 长度不一致："
                    f"{len(names)} 个名称 vs {len(values)} 个值")

        state = self._guard()
        preexisting = [state.param_existed(n) for n in names]   # 必须在写入之前问

        self.cst_file.model3d.StoreParameters(names, values)
        if log_flag == 1:
            self.cst_file.model3d.full_history_rebuild()
        state.mark_params_changed(names, rebuilt=(log_flag == 1),
                                  preexisting=preexisting)

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
        # 对于大多数 CST 版本，StoreParameter 直接传表达式字符串即可。
        state = self._guard()
        preexisting = state.param_existed(name)
        self.cst_file.model3d.StoreParameter(f"{name}", f"{value}")
        state.mark_params_changed([name], rebuilt=False, preexisting=[preexisting])

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
