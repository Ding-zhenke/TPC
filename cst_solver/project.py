# -*- coding: utf-8 -*-
"""
CST 项目操作 Mixin 模块
=======================
封装 CST 项目打开、关闭、激活、保存等操作

@author: PC
"""

import os
import logging

from cst_solver._guards import get_guard_state


class ProjectMixin:
    """
    CST 项目操作 Mixin
    提供项目文件打开、关闭、激活、保存等基础操作
    """

    def project_open(self, filename):
        """
        打开指定的 CST 工程文件并激活
        保留原函数名以兼容旧代码

        :param filename: str, CST 工程文件路径
        :raises CstGuardError: 在 ``mode='strict'`` 下路径后缀不是 .cst/.prj（陷阱 T10）
        """
        get_guard_state(self).check_project_path(filename)
        self.cst_file = self.project.open_project(filename)
        self.cst_file.activate()
        get_guard_state(self).mark_opened()
        logging.getLogger(__name__).info('项目已打开并激活')

    def open_project(self, filename):
        """
        打开指定的 CST 工程文件并激活（蛇形命名）
        等同于 project_open()

        :param filename: str, CST 工程文件路径
        """
        self.project_open(filename)

    def project_close(self):
        """关闭当前 CST 工程（保留设计环境）"""
        get_guard_state(self).check_before_close()
        if not get_guard_state(self).closed and getattr(self, 'cst_file', None) is not None:
            self.cst_file.close()
        get_guard_state(self).mark_closed()
        logging.getLogger(__name__).info('项目已关闭')

    def close_project(self):
        """关闭当前 CST 工程（保留设计环境），蛇形命名"""
        self.project_close()

    def close(self):
        """
        关闭当前打开的 CST 工程文件和设计环境，释放所有资源

        ⚠️ 顺序约定（陷阱 T15）：**先 save() 再 close()**。
        工程关闭后再调 ``save()`` 什么都不会写出，守卫层会直接报错。
        关闭前若检测到未保存的改动（建了几何但没 save），会给一条 warning。
        """
        state = get_guard_state(self)
        if not state.closed or getattr(self, '_environment_closed', False):
            state.check_before_close()
        if getattr(self, '_environment_closed', False):
            return
        try:
            if not state.closed and getattr(self, 'cst_file', None) is not None:
                self.cst_file.close()
                state.mark_closed()
        finally:
            # 即使工程关闭报错，也尝试释放由 setup 创建的设计环境。
            self.project.close()
            self._environment_closed = True
            state.mark_closed()

    def save(self, filename=None, include_results=True, allow_overwrite=False):
        """
        保存当前 CST 工程

        CST 的工程对象只提供 ``Project.save(path, include_results, allow_overwrite)``，
        **没有** ``save_as`` —— 早期实现误用 ``save_as``，带路径保存时必抛
        ``AttributeError: '_cst_interface.Project' object has no attribute 'save_as'``。

        ⚠️ 守卫层（陷阱 T15/T3）：工程已 ``close()`` 后再 save 会直接报错；
        刚导出过远场/2D-3D 结果时 ``include_results=True`` 会给一条
        「建议 include_results=False」的警告。

        :param filename: str 可选, 另存为路径；不传则保存到当前工程路径
        :param include_results: bool, 是否连同仿真结果一起保存，默认 True
        :param allow_overwrite: bool, 目标文件已存在时是否覆盖，默认 False
        """
        state = get_guard_state(self)
        state.check_before_save(include_results=include_results)
        if filename:
            self.cst_file.save(os.path.abspath(filename),
                               include_results=include_results,
                               allow_overwrite=allow_overwrite)
        else:
            self.cst_file.save()
        state.mark_saved()

    def save_as(self, filename, include_results=True, allow_overwrite=False):
        """
        将当前 CST 工程另存为

        :param filename: str, 保存路径
        :param include_results: bool, 是否连同仿真结果一起保存，默认 True
        :param allow_overwrite: bool, 目标文件已存在时是否覆盖，默认 False
        """
        self.save(filename,
                  include_results=include_results,
                  allow_overwrite=allow_overwrite)

    def new_project(self, project_type=None):
        """
        创建一个新的空白 CST 工程并激活

        CST 2026 的 ``DesignEnvironment.new_project()`` **必须**给出工程类型，
        缺参会直接抛 ``TypeError: new_project(): incompatible function arguments``。
        默认取 ``ProjectType.MWS``（CST 微波工作室，即本库使用的三维电磁工程）。

        :param project_type: ProjectType 可选, 工程类型枚举，不传则用
            ``ProjectType.MWS``；其它可选值见 ``cst.interface.ProjectType``
            （FD3D / EMS / PS / CS / DS / MPS / PCBS）
        """
        from cst_solver.environment import _load_cst_module
        ProjectType = _load_cst_module('cst.interface').ProjectType
        if project_type is None:
            project_type = ProjectType.MWS
        self.cst_file = self.project.new_project(project_type)
        self.cst_file.activate()
        get_guard_state(self).mark_opened()

    def activate(self):
        """激活当前 CST 工程为操作目标"""
        self.cst_file.activate()
