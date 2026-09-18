# -*- coding: utf-8 -*-
r"""
假后端（P2 验收用）
===================

计划要求「可注入假后端覆盖失败、重复请求、竞争、重启中断、旧结果和清理」。
本类就是那个假后端：**不碰 CST**，行为完全确定，并提供若干「坏行为」开关。

开关
----
:param fail_on: 集合, 哪些种类直接抛异常（``{'build', 'solve', 'study'}``）
:param fail_result_on: 集合, 哪些种类返回 ``ok=False``（结构化失败而非异常）
:param delay: float, 每个调用阻塞多少秒（用来验证**串行**：并发数必须恒为 1）
:param confirm_save: bool, False 时 ``solve`` 不确认保存 —— 服务层必须因此判失败
:param stale: bool, True 时 ``solve`` 返回「上一轮结果」摘要（``stale=True``），
    用来验证「旧结果」不会被当成新结果
:param metrics: dict, 自定义指标（默认给一组固定值）

它同时记录 :attr:`calls`、:attr:`max_concurrent`、:attr:`closed`，
让测试可以断言「谁被调过、有没有并行、有没有被正确关闭」。

@author: PC
"""

import os
import threading
import time
from typing import Any, Dict, List, Optional, Sequence, Set

from tpc_service.backends.base import Backend, artifact, fail_result, ok_result

__all__ = ['FakeBackend']


class FakeBackend(Backend):
    """
    确定性假后端。

    :param fail_on: 集合 可选, 这些种类**抛异常**
    :param fail_result_on: 集合 可选, 这些种类返回 ``ok=False``
    :param delay: float, 每次调用的阻塞秒数（默认 0）
    :param confirm_save: bool, ``solve`` 是否确认已保存（默认 True）
    :param stale: bool, ``solve`` 是否假装返回上一轮结果
    :param metrics: dict 可选, 自定义指标
    """

    name = 'fake'

    def __init__(self, *, fail_on: Optional[Sequence[str]] = None,
                 fail_result_on: Optional[Sequence[str]] = None,
                 delay: float = 0.0, confirm_save: bool = True,
                 stale: bool = False, metrics: Optional[Dict[str, Any]] = None,
                 write_csv: bool = True):
        self.fail_on: Set[str] = set(fail_on or ())
        self.fail_result_on: Set[str] = set(fail_result_on or ())
        self.delay = float(delay)
        self.confirm_save = bool(confirm_save)
        self.stale = bool(stale)
        self.write_csv = bool(write_csv)
        self.metrics = dict(metrics or {'S1,1_min_db': -18.5,
                                        'S2,1_at_330GHz_db': -3.2})
        self.calls: List[Dict[str, Any]] = []
        self.closed: List[Dict[str, Any]] = []
        self.max_concurrent = 0
        self._concurrent = 0
        self._lock = threading.Lock()

    # ---- 并发观测 ----

    def _enter(self, kind: str, params: Dict[str, Any]) -> None:
        with self._lock:
            self._concurrent += 1
            self.max_concurrent = max(self.max_concurrent, self._concurrent)
            self.calls.append({'kind': kind, 'params': dict(params or {})})
        if self.delay:
            time.sleep(self.delay)

    def _exit(self) -> None:
        with self._lock:
            self._concurrent -= 1

    # ---- 三个方法 ----

    def build(self, *, project, params, job):
        """建模：按 ``params['spec']`` 造一个假的工程产物。"""
        self._enter('build', params)
        try:
            if 'build' in self.fail_on:
                raise RuntimeError('假后端：build 故意抛异常')
            if 'build' in self.fail_result_on:
                return fail_result('backend_failed', '假后端：build 故意失败',
                                   retryable=True)
            path = params.get('output') or project.get('path')
            return ok_result(
                log=[f'假后端建模：{path}'],
                artifacts=[artifact(path, kind='project', note='假工程')],
                result_summary={'built': True, 'path': path})
        finally:
            self._exit()

    def solve(self, *, project, params, job):
        """求解：可按开关不确认保存 / 返回旧结果。"""
        self._enter('solve', params)
        try:
            if 'solve' in self.fail_on:
                raise RuntimeError('假后端：solve 故意抛异常')
            if 'solve' in self.fail_result_on:
                return fail_result('backend_failed', '假后端：solve 故意失败',
                                   retryable=True)
            summary = dict(self.metrics)
            if self.stale:
                summary.update({'stale': True,
                                'note': '这是上一轮留下的结果（假后端模拟）'})
            artifacts = [artifact(project.get('path', ''), kind='result',
                                  note='假结果')]
            if self.write_csv:
                csv_path = self._write_synthetic_csv(project, job)
                if csv_path:
                    artifacts.append(artifact(
                        csv_path, kind='csv',
                        note='假后端生成的**合成** S 参数曲线（不是真实仿真）'))
            return ok_result(
                log=['假后端求解完成'],
                artifacts=artifacts,
                run_identity={'run_token': f'fake-{job.get("job_id", "")}',
                              'run_id': 0},
                result_summary=summary,
                saved=self.confirm_save)
        finally:
            self._exit()

    def _write_synthetic_csv(self, project, job) -> str:
        """
        写一条**合成** S 参数曲线（300–380 GHz，步长 1 GHz）。

        ⚠️ 这是假数据，用途只有一个：让「建模 → 求解 → 分析 → 报告」这条闭环
        在没有 CST 的机器上也能端到端跑通并被测试。能力报告里会写明后端是
        ``fake``，产物备注也写明「合成曲线」，不得当作仿真结论。
        """
        import csv
        import math

        base = os.path.dirname(str(project.get('path') or '')) or '.'
        path = os.path.join(base, f'fake_sparams_{job.get("job_id", "job")}.csv')
        try:
            os.makedirs(base, exist_ok=True)
            with open(path, 'w', newline='', encoding='utf-8-sig') as handle:
                writer = csv.writer(handle)
                writer.writerow(['freq_GHz', 'S1,1', 'S2,1'])
                for step in range(81):
                    freq = 300.0 + step
                    s11 = -5.0 - 12.0 * math.exp(-((freq - 330.0) / 6.0) ** 2)
                    s21 = -1.5 - 20.0 * math.exp(-((freq - 330.0) / 8.0) ** 2)
                    writer.writerow([f'{freq:.3f}', f'{s11:.6f}', f'{s21:.6f}'])
        except OSError:
            return ''
        return path

    def study(self, *, project, params, job):
        """参数研究：对 ``params['study']['points']`` 逐个串行执行。"""
        self._enter('study', params)
        try:
            if 'study' in self.fail_on:
                raise RuntimeError('假后端：study 故意抛异常')
            points = list((params.get('study') or {}).get('points') or [])
            rows = []
            for point in points:
                rows.append({'point': point,
                             'metric': self.metrics.get('S2,1_at_330GHz_db')})
            return ok_result(
                log=[f'假后端研究：{len(rows)} 个点'],
                result_summary={'n_points': len(rows), 'rows': rows},
                saved=True)
        finally:
            self._exit()

    def close_project(self, *, project, save=True):
        """记录关闭请求（服务层只对自有会话调用）。"""
        self.closed.append({'project': dict(project or {}), 'save': bool(save)})
