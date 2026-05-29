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

    def save(self, filename=None):
        """
        保存当前 CST 工程
        :param filename: str 可选, 另存为路径，不传则覆盖保存
        """
        if filename:
            self.cst_file.save_as(os.path.abspath(filename))
        else:
            self.cst_file.save()

    def save_as(self, filename):
        """
        将当前 CST 工程另存为
        :param filename: str, 保存路径
        """
        self.save(filename)

    def new_project(self):
        """
        创建一个新的空白 CST 工程（需要 CST 环境支持）
        注意：此功能依赖 CST 版本，可能不被所有版本支持
        """
        self.cst_file = self.project.new_project()
        self.cst_file.activate()

    def activate(self):
        """激活当前 CST 工程为操作目标"""
        self.cst_file.activate()
