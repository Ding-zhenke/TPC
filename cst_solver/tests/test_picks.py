# -*- coding: utf-8 -*-
"""
面拾取的成功判定测试（P4/V5 真机发现）
=======================================

守住什么
--------
真机实测（CST 2026，2026-09）发现两件事，直接推翻了「按消息判定拾取」的可靠性：

1. 工程历史里只要留下**一条失败命令**，``get_messages()`` 会**反复**报那条历史失败
   —— 不是「读一次就干净」；
2. 于是 ``pick_face_auto()`` 用「消息为空 = 拾取成功」判定时，**在脏工程里会一直判失败**，
   哪怕拾取其实成功了（实测 ``GetNumberOfPickedFaces() == 1`` 而消息非空）。

修法：优先用 ``GetNumberOfPickedFaces()`` 作为**正向信号**，取不到才退回消息判定。
本文件用假宿主把这两条路径钉住（真机证据见
``docs/validation/p4_real_machine_evidence.md`` 的 V5 节）。
"""

import os
import sys

import pytest

_TPC_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _TPC_ROOT not in sys.path:
    sys.path.insert(0, _TPC_ROOT)

from cst_solver.modeling.picks import PickMixin   # noqa: E402


class _FakePick:
    """假的 ``model3d.Pick``：``GetNumberOfPickedFaces`` 返回设定值。"""

    def __init__(self, counts):
        self.counts = list(counts)

    def GetNumberOfPickedFaces(self):                 # noqa: N802 (CST 原名)
        return self.counts.pop(0) if self.counts else 0


class _FakeModel3D:
    def __init__(self, pick=None):
        self.history = []
        if pick is not None:
            self.Pick = pick

    def add_to_history(self, caption, vba):
        self.history.append((caption, vba))


class _FakeCstFile:
    def __init__(self, model3d, messages=None):
        self.model3d = model3d
        self._messages = list(messages or [])

    def get_messages(self):
        """模拟「历史失败反复出现」：读了也还在。"""
        return list(self._messages)


class _Host(PickMixin):
    """最小宿主：只带 PickMixin。"""

    def __init__(self, model3d, messages=None):
        self.cst_file = _FakeCstFile(model3d, messages=messages)


def test_pick_succeeds_even_when_messages_are_dirty():
    """核心回归：消息非空但已选面数为 1 ⇒ 必须判成功。"""
    host = _Host(_FakeModel3D(_FakePick([1])),
                 messages=['历史里的旧失败（会反复出现）'])
    result = host.pick_face_auto('box', points=[(0.5, 0.5, 1.0)])
    assert result == ('point', (0.5, 0.5, 1.0))
    assert len(host.cst_file.model3d.history) == 1     # 只试了第一个点


def test_pick_falls_through_when_count_is_zero():
    """已选面数为 0 ⇒ 换下一个候选点（历史里会多一条 Pick clear）。"""
    host = _Host(_FakeModel3D(_FakePick([0, 1])),
                 messages=['历史失败'])
    result = host.pick_face_auto('box', points=[(0.1, 0.1, 0.1),
                                                (0.5, 0.5, 1.0)])
    assert result == ('point', (0.5, 0.5, 1.0))
    labels = [caption for caption, _ in host.cst_file.model3d.history]
    assert sum('Pick clear' in label for label in labels) == 1
    assert len(labels) == 3                            # 拾取 + 清空 + 拾取


def test_candidates_used_when_no_point_works():
    """点全失败时退回按面编号。"""
    host = _Host(_FakeModel3D(_FakePick([0, 1])), messages=[])
    result = host.pick_face_auto('box', points=[(0.1, 0.1, 0.1)],
                                 candidates=('10', '22'))
    assert result == ('id', '10')
    labels = [caption for caption, _ in host.cst_file.model3d.history]
    assert len(labels) == 3                            # 点 + 清空 + 面编号


def test_fallback_to_messages_when_pick_object_missing():
    """拿不到已选面数时，退回旧的消息判定（保持向后兼容）。"""
    host = _Host(_FakeModel3D(), messages=[])          # 没有 model3d.Pick
    # 公开接口在接口未暴露时**按文档抛 RuntimeError**（不是返回 None）
    with pytest.raises(RuntimeError):
        host.get_picked_count('face')
    # 但 pick_face_auto 内部会把这条异常吞掉并退回消息判定
    assert host.pick_face_auto('box', points=[(0.5, 0.5, 1.0)]) == \
        ('point', (0.5, 0.5, 1.0))

    dirty = _Host(_FakeModel3D(), messages=['旧失败'])
    assert dirty.pick_face_auto('box', points=[(0.5, 0.5, 1.0)]) is None


def test_pick_failure_when_count_unavailable_and_messages_dirty():
    """反向保证：拿不到计数 + 消息非空 ⇒ 判失败（不要把脏消息当成功）。"""
    host = _Host(_FakeModel3D(),
                 messages=['(&H8000ffff) The picked port area is empty'])
    assert host._pick_succeeded() is False
