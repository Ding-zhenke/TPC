# -*- coding: utf-8 -*-
"""
CST 项目操作 Mixin 模块
=======================
封装 CST 项目打开、关闭、激活、保存等操作

@author: PC
"""

import os
import logging

from cst_solver._guards import get_guard_state, require_project_file


class ProjectMixin:
    """
    CST 项目操作 Mixin
    提供项目文件打开、关闭、激活、保存等基础操作
    """

    def project_open(self, filename):
        """
        打开指定的 CST 工程文件并激活
        保留原函数名以兼容旧代码

        2026-10 修复：本方法原先**完全不检查路径是否存在**，路径写错时一路走到
        ``self.project.open_project()`` 才由 CST 报一个语焉不详的错；现在与
        ``setup(filename)`` / ``open()`` 走**同一个**校验入口
        :func:`cst_solver._guards.require_project_file`，并且接受
        ``pathlib.Path``（此前传 Path 会被后缀守卫误判成「路径非法」）。

        :param filename: str 或 os.PathLike, CST 工程文件路径（必须已存在且是文件）
        :raises FileNotFoundError: 路径不存在
        :raises IsADirectoryError: 路径存在但是目录（CST 工程是单个 .cst/.prj 文件）
        :raises CstGuardError: 在 ``mode='strict'`` 下路径后缀不是 .cst/.prj（陷阱 T10）
        """
        filename = require_project_file(filename)
        get_guard_state(self).check_project_path(filename)
        self.cst_file = self.project.open_project(filename)
        self.cst_file.activate()
        get_guard_state(self).mark_opened()
        logging.getLogger(__name__).info('项目已打开并激活')

    def open_project(self, filename):
        """
        打开指定的 CST 工程文件并激活（蛇形命名）
        等同于 project_open()

        :param filename: str 或 os.PathLike, CST 工程文件路径（必须已存在且是文件）
        """
        self.project_open(filename)

    def project_close(self):
        """关闭当前 CST 工程（保留设计环境）。

        ⚠️ attach 借用的会话不做真实关闭，只解除 Python 侧引用，
        避免关掉用户自己打开的工程。
        """
        if getattr(self, '_attached', False):
            get_guard_state(self).mark_closed()
            self.cst_file = None
            logging.getLogger(__name__).info(
                'attach 会话已解除引用（未关闭用户的工程）')
            return
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

        ⚠️ **attach 实例例外**：实例若是经 ``setup.attach()`` 借用的用户会话，
        ``close()`` 只解除 Python 侧引用，**不会**关闭借用的工程或 DE
        （否则会把用户自己开着的 CST 关掉）。
        """
        # attach 借用的会话不归本实例所有：只标记逻辑关闭、解除引用。
        if getattr(self, '_attached', False):
            get_guard_state(self).mark_closed()
            self.cst_file = None
            self._environment_closed = True
            logging.getLogger(__name__).info(
                'attach 会话已解除引用（未关闭用户的 CST DE）')
            return
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

        ⚠️ 2026-10 修复：原先不传 ``filename`` 时直接调 ``self.cst_file.save()``
        （**无参**）—— 真机上这是**静默 no-op**：工程文件根本不会被写出，
        调用方却以为已保存，接着 ``close()`` 就把整场建模丢掉了
        （没有任何报错、没有任何 warning，是最难查的一类缺陷）。
        现在不传路径时**显式**把当前工程路径传给 CST：

        1. 用 ``self.cst_file.filename()`` 取当前工程文件路径
           （官方 API ``Project.filename() -> str``）；
        2. 路径为空（例如刚 ``new_project()`` 还没落盘）⇒ 抛 ``RuntimeError``，
           明确要求给出 ``filename`` 或改用 :meth:`save_as`；
        3. 否则按绝对路径 + ``allow_overwrite=True`` 调用 ``cst_file.save(path, …)``
           —— 覆盖的是「工程自己的文件」，这正是 save 的语义。

        ⚠️ 守卫层（陷阱 T15/T3）：工程已 ``close()`` 后再 save 会直接报错；
        刚导出过远场/2D-3D 结果时 ``include_results=True`` 会给一条
        「建议 include_results=False」的警告。

        :param filename: str 可选, 另存为路径；不传则保存到**当前工程路径**
        :param include_results: bool, 是否连同仿真结果一起保存，默认 True
        :param allow_overwrite: bool, ``filename`` 已存在时是否覆盖，默认 False
            （不传 ``filename`` 时本项被忽略：工程自己的文件总是覆盖写）
        :return: str, 实际写出的绝对路径（便于日志与验收脚本核对）
        :raises RuntimeError: 不传 ``filename``，且当前 CST 工程没有可用的文件路径
        :raises IsADirectoryError: ``filename`` 指向一个目录
        """
        state = get_guard_state(self)
        state.check_before_save(include_results=include_results)
        if filename:
            target = os.path.abspath(filename)
            if os.path.isdir(target):
                raise IsADirectoryError(
                    f"save(filename=...) 指向一个目录：{target}\n"
                    f"    工程要写成**单个** .cst/.prj 文件，请把路径指到文件"
                    f"（如 r'D:\\work\\wg_AB.cst'）。")
            overwrite = allow_overwrite
        else:
            target = self._current_project_path()
            overwrite = True
        self.cst_file.save(target,
                            include_results=include_results,
                            allow_overwrite=overwrite)
        state.mark_saved()
        return target

    def _current_project_path(self):
        """
        当前 CST 工程文件的绝对路径；取不到就抛 ``RuntimeError``。

        为什么不让调用方继续无参 ``save()``：真机上那是个静默 no-op。
        这里宁可**响亮地失败**，也不给出「保存成功」的假象。

        :return: str, 绝对路径
        :raises RuntimeError: 工程还没有文件路径，或 ``filename()`` 调用失败
        """
        try:
            current = self.cst_file.filename()
        except Exception as exc:
            raise RuntimeError(
                f"无法取得当前 CST 工程的路径（cst_file.filename() 报错：{exc}）；"
                f"请显式给出 app.save(path)。") from exc
        if not current:
            raise RuntimeError(
                "当前 CST 工程还没有文件路径（例如刚 new_project() 还没落盘），"
                "save() 不传路径无法保存；请用 app.save(path) 或 app.save_as(path)。")
        return os.path.abspath(str(current))

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
