# -*- coding: utf-8 -*-
r"""
任务持久化与工作目录约束（P2）
==============================

落盘格式
--------
::

    <workdir>/                    服务工作目录（服务只在这里写东西）
    ├── jobs/<job_id>.json        每条任务的完整记录（原子写：tmp + os.replace）
    ├── events.jsonl              追加式事件流（创建/开始/结束，便于事后追溯）
    └── projects/<name>.cst       工程工作副本（由 registry 管理）

为什么逐任务一个文件
--------------------
扫描/批量/优化会一次产生几十上百条任务；单文件 JSONL 每次都要全量重写，
进程被打断时更容易只写坏一半。逐任务一个小文件 + 原子替换，读回时逐个解析、
坏文件单独报告，不会因为一条坏记录丢掉全部历史。

工作目录约束
------------
:func:`ensure_within` 是所有产物路径的**唯一入口**：任何逃出工作目录的路径
（``..``、绝对路径指向别处）都直接失败，避免「服务把文件写到用户不知道的地方」。
"""

import json
import os
from typing import Any, Dict, Iterator, List, Optional

from tpc_service.errors import ServiceError
from tpc_service.state import JobRecord

__all__ = ['JobStore', 'ensure_within', 'is_within']


def _norm(path: str) -> str:
    return os.path.abspath(os.path.expanduser(str(path)))


def is_within(root: str, path: str) -> bool:
    """``path`` 是否在 ``root`` 之内（含 root 自身）。"""
    root_abs, path_abs = _norm(root), _norm(path)
    return path_abs == root_abs or path_abs.startswith(root_abs + os.sep)


def ensure_within(root: str, path: str) -> str:
    """
    校验路径在工作目录内，返回规范化后的绝对路径。

    :param root: str, 工作目录
    :param path: str, 待校验路径
    :return: str, 绝对路径
    :raises ServiceError: ``workdir_escape``
    """
    root_abs, path_abs = _norm(root), _norm(path)
    if not is_within(root_abs, path_abs):
        raise ServiceError(
            'workdir_escape',
            f'路径 {path_abs} 逃出服务工作目录 {root_abs}；'
            f'服务只在自己的工作目录内写文件',
            path=path_abs, workdir=root_abs)
    return path_abs


class JobStore:
    """
    任务记录与事件流的落盘器。

    :param root: str, 服务工作目录
    """

    def __init__(self, root: str):
        self.root = _norm(root)
        self.jobs_dir = os.path.join(self.root, 'jobs')
        self.events_path = os.path.join(self.root, 'events.jsonl')

    # ---- 目录 ----

    def ensure(self) -> 'JobStore':
        """创建目录（幂等）。"""
        os.makedirs(self.jobs_dir, exist_ok=True)
        return self

    def job_path(self, job_id: str) -> str:
        """某个任务的记录文件路径（做工作目录约束）。"""
        safe = str(job_id).replace('/', '_').replace('\\', '_')
        return ensure_within(self.root, os.path.join(self.jobs_dir, f'{safe}.json'))

    # ---- 读写 ----

    def save(self, record: JobRecord) -> str:
        """
        原子写入任务记录（先写临时文件再 ``os.replace``）。

        :param record: JobRecord
        :return: str, 记录文件路径
        """
        path = self.job_path(record.job_id)
        os.makedirs(self.jobs_dir, exist_ok=True)
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as handle:
            json.dump(record.to_dict(), handle, ensure_ascii=False,
                      sort_keys=True, indent=2, default=str)
        os.replace(tmp, path)
        return path

    def load(self, job_id: str) -> Optional[JobRecord]:
        """读回一条记录；不存在返回 None。"""
        path = self.job_path(job_id)
        if not os.path.exists(path):
            return None
        with open(path, encoding='utf-8') as handle:
            return JobRecord.from_dict(json.load(handle))

    def all(self) -> List[JobRecord]:
        """
        读回全部记录（按创建时间排序）。

        坏掉的记录**不会被静默忽略**：它会被解析成一条 ``failed`` 记录放进结果里，
        这样调用方能看见「这里有一条读不出来的历史」，而不是以为历史很干净。
        """
        if not os.path.isdir(self.jobs_dir):
            return []
        records: List[JobRecord] = []
        for name in sorted(os.listdir(self.jobs_dir)):
            if not name.endswith('.json'):
                continue
            path = os.path.join(self.jobs_dir, name)
            try:
                with open(path, encoding='utf-8') as handle:
                    records.append(JobRecord.from_dict(json.load(handle)))
            except Exception as exc:                  # noqa: BLE001
                job_id = name[:-len('.json')]
                broken = JobRecord(job_id=job_id, kind='unknown',
                                   status='failed')
                broken.note(f'记录文件损坏，无法解析：{exc!r}')
                from tpc_service.errors import error_dict
                broken.error = error_dict(
                    'backend_failed', f'任务记录损坏：{path}',
                    retryable=False, path=path)
                records.append(broken)
        records.sort(key=lambda r: (r.created_at or '', r.job_id))
        return records

    def append_event(self, record: JobRecord, event: str, **extra) -> str:
        """
        追加一条事件（JSONL）。

        :param record: JobRecord
        :param event: str, 事件名（``created`` / ``started`` / ``finished`` …）
        :param extra: 额外字段
        :return: str, 事件文件路径
        """
        os.makedirs(self.root, exist_ok=True)
        line = json.dumps({'event': event, 'job_id': record.job_id,
                           'status': record.status,
                           'params_digest': record.params_digest,
                           **extra}, ensure_ascii=False, sort_keys=True,
                          default=str)
        with open(self.events_path, 'a', encoding='utf-8') as handle:
            handle.write(line + '\n')
        return self.events_path

    def events(self) -> Iterator[Dict[str, Any]]:
        """逐行读事件流（坏行跳过并标注）。"""
        if not os.path.exists(self.events_path):
            return
        with open(self.events_path, encoding='utf-8') as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    yield {'event': 'unparsable', 'raw': line[:200]}
