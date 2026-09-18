# -*- coding: utf-8 -*-
r"""
工程注册与会话归属（P2）
========================

要解决的三件事
--------------
1. **工程副本策略**：CST 工程是「``xxx.cst`` 文件 + ``xxx/`` 目录」一对，
   直接在用户原工程上做扫描/优化会把人家的工作文件改烂。默认行为是
   **复制到服务工作目录再动手**；要就地操作必须显式 ``copy=False``。
2. **覆盖策略**：目标工作副本已存在时默认**报错**（``project_exists``），
   只有 ``overwrite=True`` 才删除重建 —— 删掉别人正在用的工作副本比报错危险得多。
3. **会话归属**：服务只关闭**自己创建**的会话。挂到外部已有会话上的工程，
   ``release()`` 只解除注册，不会去关别人的 CST（``cst_mcp.md`` §4）。

线程/进程归属
-------------
:class:`ProjectRecord` 里的 ``session`` 是后端会话对象（真实 CST 下就是
DesignEnvironment / Project 句柄）。它**只属于单 CST worker 线程**，
不出服务、不落盘、不跨线程传递；调用方拿到的是 JSON 记录与路径。
"""

import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

from tpc_service.errors import ServiceError
from tpc_service.store import ensure_within

__all__ = ['ProjectRecord', 'ProjectRegistry', 'copy_project']


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def copy_project(source: str, destination: str, *, overwrite: bool = False) -> Dict[str, Any]:
    """
    复制一个 CST 工程（``.cst`` 文件 + 同名目录）。

    :param source: str, 源 ``.cst`` 路径
    :param destination: str, 目标 ``.cst`` 路径
    :param overwrite: bool, 目标已存在时是否删除重建
    :return: dict, ``{'project': 目标 .cst, 'folder': 目标目录或 None}``
    :raises ServiceError: ``project_not_found`` / ``project_exists`` / ``project_copy_failed``
    """
    source = os.path.abspath(source)
    destination = os.path.abspath(destination)
    if not os.path.isfile(source):
        raise ServiceError('project_not_found', f'工程文件不存在：{source}',
                           path=source)
    source_folder = os.path.splitext(source)[0]
    destination_folder = os.path.splitext(destination)[0]
    existing = [p for p in (destination, destination_folder) if os.path.exists(p)]
    if existing and not overwrite:
        raise ServiceError(
            'project_exists',
            f'目标工作副本已存在：{existing[0]}（要重建请显式 overwrite=True）',
            path=existing[0], existing=existing)
    try:
        for path in existing:
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
        os.makedirs(os.path.dirname(destination) or '.', exist_ok=True)
        shutil.copy2(source, destination)
        if os.path.isdir(source_folder):
            shutil.copytree(source_folder, destination_folder)
            return {'project': destination, 'folder': destination_folder}
        return {'project': destination, 'folder': None}
    except ServiceError:
        raise
    except Exception as exc:                          # noqa: BLE001
        raise ServiceError('project_copy_failed',
                           f'复制工程失败：{type(exc).__name__}: {exc}',
                           retryable=True, source=source,
                           destination=destination) from exc


@dataclass
class ProjectRecord:
    """
    一个已注册工程。

    :param project_id: str, 工程 ID（服务生成，用于对外引用）
    :param path: str, 执行时使用的工程路径（工作副本或原路径）
    :param source_path: str 可选, 原始工程路径（``copy=True`` 时才有）
    :param owned_copy: bool, ``path`` 是否是服务复制出来的工作副本
    :param session_owned: bool, 后端会话是否由服务创建（决定能否关闭）
    :param created_at: str, 注册时间
    :param note: str, 备注
    :param session: 后端会话对象 —— **不落盘、不出 worker 线程**
    """

    project_id: str
    path: str
    source_path: Optional[str] = None
    owned_copy: bool = False
    session_owned: bool = False
    created_at: str = field(default_factory=_utcnow)
    note: str = ''
    session: Any = None

    def to_dict(self) -> Dict[str, Any]:
        """JSON 友好字典（**不含** session 对象；CST 句柄不对外暴露）。"""
        return {
            'project_id': self.project_id,
            'path': self.path,
            'source_path': self.source_path,
            'owned_copy': self.owned_copy,
            'session_owned': self.session_owned,
            'created_at': self.created_at,
            'note': self.note,
            'has_session': self.session is not None,
        }


class ProjectRegistry:
    """
    工程注册表：注册、查、列、释放。

    :param workdir: str, 服务工作目录（工作副本写在这里）
    :param clock: 可调用 可选, 返回时间字符串（测试注入）
    """

    def __init__(self, workdir: str, *, clock: Optional[Callable[[], str]] = None):
        self.workdir = os.path.abspath(workdir)
        self.projects_dir = os.path.join(self.workdir, 'projects')
        self.clock = clock or _utcnow
        self._projects: Dict[str, ProjectRecord] = {}

    # ---- 注册 ----

    def register(self, path: str, *, copy: bool = True, overwrite: bool = False,
                 project_id: Optional[str] = None, session: Any = None,
                 session_owned: bool = False, note: str = '') -> ProjectRecord:
        """
        注册一个工程。

        :param path: str, 工程 ``.cst`` 路径（原工程）
        :param copy: bool, True（默认）复制到工作目录再执行；False 就地执行
        :param overwrite: bool, 工作副本已存在时是否删除重建
        :param project_id: str 可选, 指定 ID（不传则生成）
        :param session: 后端会话对象（不落盘）
        :param session_owned: bool, 会话是否由服务创建（``copy=False`` 且挂了
            外部会话时应为 False）
        :param note: str, 备注
        :return: ProjectRecord
        :raises ServiceError: 见 :func:`copy_project`
        """
        source = os.path.abspath(path)
        if not os.path.isfile(source):
            raise ServiceError('project_not_found', f'工程文件不存在：{source}',
                               path=source)
        pid = project_id or f'prj-{uuid4().hex[:12]}'
        if copy:
            os.makedirs(self.projects_dir, exist_ok=True)
            destination = ensure_within(
                self.workdir,
                os.path.join(self.projects_dir, os.path.basename(source)))
            copy_project(source, destination, overwrite=overwrite)
            record = ProjectRecord(project_id=pid, path=destination,
                                   source_path=source, owned_copy=True,
                                   session_owned=session_owned,
                                   created_at=self.clock(), note=note,
                                   session=session)
        else:
            record = ProjectRecord(project_id=pid, path=source,
                                   source_path=None, owned_copy=False,
                                   session_owned=session_owned,
                                   created_at=self.clock(),
                                   note=note or '就地执行（未复制）',
                                   session=session)
        self._projects[pid] = record
        return record

    # ---- 查询 ----

    def get(self, project_id: str) -> ProjectRecord:
        """
        取一个已注册工程。

        :raises ServiceError: ``project_not_registered``
        """
        record = self._projects.get(project_id)
        if record is None:
            raise ServiceError('project_not_registered',
                               f'工程 ID {project_id!r} 没有注册'
                               f'（现有：{sorted(self._projects)}）',
                               project_id=project_id)
        return record

    def find_by_path(self, path: str) -> Optional[ProjectRecord]:
        """按执行路径找已注册工程。"""
        target = os.path.abspath(path)
        for record in self._projects.values():
            if os.path.abspath(record.path) == target:
                return record
        return None

    def find_by_source(self, path: str) -> Optional[ProjectRecord]:
        """
        按**原始工程路径**找已注册工程（用于「同一源工程重复提交」时复用工作副本）。

        没有这个查法时，第二次提交同一个源工程会再复制一遍，
        撞上 ``project_exists``（工作副本已存在）—— 那是**误报**：
        用户只是又提交了一次同一个工程。
        """
        target = os.path.abspath(path)
        for record in self._projects.values():
            if record.source_path and os.path.abspath(record.source_path) == target:
                return record
        return None

    def list(self) -> List[ProjectRecord]:
        """全部已注册工程（按注册时间排序）。"""
        return sorted(self._projects.values(), key=lambda r: r.created_at)

    # ---- 释放 ----

    def release(self, project_id: str,
                closer: Optional[Callable[[ProjectRecord], Any]] = None) -> Dict[str, Any]:
        """
        释放一个工程：**只关闭服务自己创建的会话**。

        :param project_id: str, 工程 ID
        :param closer: 可调用 可选, 关闭会话的函数（收 ProjectRecord）——
            只有 ``session_owned`` 为真时才会被调用
        :return: dict, ``{'project_id', 'closed_session', 'reason'}``
        :raises ServiceError: ``project_not_registered``
        """
        record = self.get(project_id)
        closed = False
        if record.session_owned and record.session is not None:
            if closer is not None:
                closer(record)
            record.session = None
            closed = True
            reason = '服务创建的会话已关闭'
        else:
            reason = ('外部已有会话，只解除注册不关闭'
                      if not record.session_owned else '没有会话可关闭')
        self._projects.pop(project_id, None)
        return {'project_id': project_id, 'closed_session': closed,
                'reason': reason}

    def release_all(self, closer: Optional[Callable[[ProjectRecord], Any]] = None
                    ) -> List[Dict[str, Any]]:
        """释放全部工程（逐个按归属规则处理）。"""
        return [self.release(pid, closer) for pid in list(self._projects)]

    # ---- 约束 ----

    def artifact_path(self, project_id: str, name: str) -> str:
        """
        给某个工程生成**工作目录内**的产物路径。

        :param project_id: str, 工程 ID
        :param name: str, 文件名
        :return: str, 绝对路径（已做逃逸校验）
        :raises ServiceError: ``workdir_escape``
        """
        record = self.get(project_id)
        base = os.path.join(self.workdir, 'artifacts', record.project_id)
        return ensure_within(self.workdir, os.path.join(base, name))

    def describe(self) -> Dict[str, Any]:
        """注册表快照（可 JSON 序列化）。"""
        return {'workdir': self.workdir,
                'projects': [r.to_dict() for r in self.list()]}
