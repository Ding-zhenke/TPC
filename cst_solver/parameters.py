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

    def _parameter_exists(self, name):
        """
        某个参数在工程里是否已经存在（官方查询 API，带回退）。

        ⚠️ 2026-10 修复：旧实现读的是 ``model3d.GetParameter(name)`` ——
        **CST 根本没有这个方法**。官方 Parameter API 里查询用
        ``DoesParameterExist(name)``，读取用 ``RestoreParameter`` /
        ``RestoreDoubleParameter`` / ``RestoreParameterExpression``
        （见 ``docs/references/vba-official-reference.md`` 的 Parameter 一节）。
        因此旧写法在任何真机上都必然失败；在守卫里它被 ``except`` 吞掉，
        表现为「打开已有工程后改参数不再被提醒」。

        本方法**永不抛异常**：查不出来一律按「不存在」处理 ——
        「当成新参数」的错误后果（漏一次提醒，run() 前的检查与
        ``validate_model()`` 还能兜住）远小于「当成已存在」的后果
        （在正常建模流水线里到处误报，把守卫变成会被忽略的噪音源）。

        :param name: str, 参数名称
        :return: bool, True 表示工程里已经有这个参数
        """
        model3d = self.cst_file.model3d
        try:
            return bool(model3d.DoesParameterExist(f"{name}"))
        except Exception:
            pass
        try:
            value = model3d.RestoreParameter(f"{name}")
        except Exception:
            return False
        return value not in (None, '')

    def _guard_param_probe(self, name):
        """
        守卫用的探针：某个参数在工程里是否已经存在。

        直接复用 :meth:`_parameter_exists`（官方 ``DoesParameterExist`` 查询，
        读不到才退回 ``RestoreParameter``），语义与守卫需要的完全一致。
        """
        return self._parameter_exists(name)

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

        ⚠️ 参数名、表达式、说明文本会先过一遍 :mod:`cst_solver.expressions` 的
        校验；发现问题时记进**结构化失败通道**（``cst_solver.failures``）并照旧
        下发 —— 旧 notebook 的行为一字不变，需要硬拦截就开
        ``cst_solver.failures.set_failure_strict(True)``。
        """
        state = self._guard()
        self._check_parameter_inputs(name, value, expression)
        preexisting = state.param_existed(name)     # 必须在写入之前问

        self.cst_file.model3d.StoreParameter(f"{name}", value)
        if expression:
            self._set_parameter_description(name, expression)
        if log_flag == 1:
            self.cst_file.model3d.full_history_rebuild()
        state.mark_params_changed([name], rebuilt=(log_flag == 1),
                                  preexisting=[preexisting])

    def _check_parameter_inputs(self, name, value, expression=''):
        """
        参数名 / 表达式 / 说明文本的自查（P1：表达式和名称校验）。

        只**记录结构化失败**，不抛异常、不改变下发内容：既有 notebook 里哪怕
        有非常规写法也照旧跑；要硬拦截就开
        ``cst_solver.failures.set_failure_strict(True)``。
        表达式检查**不做参数表引用检查**（此刻参数表可能还没建全，
        例如 ``para('l1', '0.65*a')`` 里的 ``a`` 可能稍后才定义）。

        :param name: 参数名
        :param value: 参数值（字符串按 CST 表达式校验）
        :param expression: str, 说明文本（按「VBA 字符串字面量内的文本」校验）
        """
        from cst_solver.expressions import check_expression, check_name, check_vba_text
        from cst_solver.failures import record_failure

        name_check = check_name(name, kind='parameter')
        if not name_check.ok:
            record_failure('para', name_check.errors[0]['code'],
                           f'参数名不合法：{name_check.errors[0]["message"]}',
                           log=False, field='name', value=name,
                           issues=name_check.to_dict()['errors'])

        if isinstance(value, str):
            expr_check = check_expression(value)
            if not expr_check.ok:
                record_failure('para', expr_check.errors[0]['code'],
                               f'参数表达式不合法：{expr_check.errors[0]["message"]}',
                               log=False, field='value', value=value,
                               issues=expr_check.to_dict()['errors'])

        if expression:
            text_check = check_vba_text(expression)
            if not text_check.ok:
                record_failure('para', text_check.errors[0]['code'],
                               f'参数说明文本不合法（会破坏 VBA 字面量）：'
                               f'{text_check.errors[0]["message"]}',
                               log=False, field='expression',
                               issues=text_check.to_dict()['errors'])

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
        获取指定参数的**当前值**

        ⚠️ 2026-10 修复：旧实现调的是 ``model3d.GetParameter(name)``，而
        **CST 没有 ``GetParameter`` 这个方法** —— 官方 Parameter API 的读取成员只有
        ``RestoreParameter`` / ``RestoreDoubleParameter`` /
        ``RestoreParameterExpression``，查询成员是 ``DoesParameterExist`` /
        ``GetParameterName`` / ``GetParameterNValue`` / ``GetParameterSValue``
        （见 ``docs/references/vba-official-reference.md`` 的 Parameter 一节）。
        因此旧写法在任何真机上都必然失败：轻则抛错，重则被守卫/调用方的
        ``except`` 吞掉，表现为「参数明明写进去了却读不出来」。

        现在的读法（官方 API 逐级回退）：

        1. ``DoesParameterExist(name)`` 先确认参数存在 —— 不存在直接抛
           ``KeyError``，**不**静默返回空串或 ``None``（「读不到」与「值就是空」
           是两码事，静默返回正是这类缺陷能活下来的原因）；
        2. ``RestoreDoubleParameter(name)`` —— 数值参数返回 ``float``
           （表达式参数返回其**求值结果**）；
        3. ``RestoreParameter(name)`` —— 表达式/字符串参数返回 ``str``。

        :param name: str, 参数名称
        :return: float 或 str, 参数当前值（数值参数返回 float）
        :raises KeyError: 工程里没有这个参数（先用 ``para()`` / ``paras()`` 定义）
        :raises RuntimeError: CST 既没有 ``RestoreDoubleParameter`` 也没有
            ``RestoreParameter``，或两者都读取失败
        """
        model3d = self.cst_file.model3d
        if not self._parameter_exists(name):
            raise KeyError(
                f"工程里没有参数 {name!r}：请先用 app.para({name!r}, ...) 或 "
                f"app.paras({{...}}) 定义它，再读取。")

        errors = []
        for reader_name in ('RestoreDoubleParameter', 'RestoreParameter'):
            reader = getattr(model3d, reader_name, None)
            if reader is None:
                continue
            try:
                return reader(f"{name}")
            except Exception as exc:              # 换下一个读取接口
                errors.append(f"{reader_name}: {exc}")

        detail = ('；CST 报错：' + ' / '.join(errors)) if errors else ''
        raise RuntimeError(
            f"读取参数 {name!r} 失败：该 CST 会话没有暴露可用的参数读取接口"
            f"（试过 RestoreDoubleParameter 与 RestoreParameter）{detail}")

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
