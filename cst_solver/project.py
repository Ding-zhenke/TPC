# -*- coding: utf-8 -*-
"""
CST 项目操作 Mixin 模块
=======================
封装 CST 项目打开、关闭、激活、保存等操作

@author: PC
"""

import os


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
        """
        self.cst_file = self.project.open_project(filename)
        self.cst_file.activate()
        print('项目已打开并激活')

    def open_project(self, filename):
        """
        打开指定的 CST 工程文件并激活（蛇形命名）
        等同于 project_open()

        :param filename: str, CST 工程文件路径
        """
        self.project_open(filename)

    def project_close(self):
        """关闭当前 CST 工程（保留设计环境）"""
        self.cst_file.close()
        print('项目已关闭')

    def close_project(self):
        """关闭当前 CST 工程（保留设计环境），蛇形命名"""
        self.project_close()

    def close(self):
        """
        关闭当前打开的 CST 工程文件和设计环境，释放所有资源
        """
        self.cst_file.close()
        self.project.close()

    def save(self, filename=None, include_results=True, allow_overwrite=False):
        """
        保存当前 CST 工程

        CST 的工程对象只提供 ``Project.save(path, include_results, allow_overwrite)``，
        **没有** ``save_as`` —— 早期实现误用 ``save_as``，带路径保存时必抛
        ``AttributeError: '_cst_interface.Project' object has no attribute 'save_as'``。

        :param filename: str 可选, 另存为路径；不传则保存到当前工程路径
        :param include_results: bool, 是否连同仿真结果一起保存，默认 True
        :param allow_overwrite: bool, 目标文件已存在时是否覆盖，默认 False
        """
        if filename:
            self.cst_file.save(os.path.abspath(filename),
                               include_results=include_results,
                               allow_overwrite=allow_overwrite)
        else:
            self.cst_file.save()

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
        from cst.interface import ProjectType
        if project_type is None:
            project_type = ProjectType.MWS
        self.cst_file = self.project.new_project(project_type)
        self.cst_file.activate()

    def activate(self):
        """激活当前 CST 工程为操作目标"""
        self.cst_file.activate()
