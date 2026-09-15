# -*- coding: utf-8 -*-
"""
CST 结构化验收 Mixin 模块
==========================
把「验收必须读 ``get_messages()`` 并跑 ``Rebuild()``」这条**口头约定**
变成一个有返回值、可被脚本判断的 API。

为什么需要它
------------
``skills/developer/WORKFLOW.md`` 的硬约定 §3 写明：

    验收一律以 ``get_messages()`` 为准 —— **CST 不抛异常**，
    非法 VBA 只会安静地写一条消息然后什么都不做。

但在此之前这条约定**没有任何 API 支撑**：每个脚本都要自己抄一遍
「读消息 → 判空 → 跑 Rebuild → 再读消息」。抄错一次（比如忘了重建、
或者只看返回值不看消息）就会把失败当成功。本模块把它固化下来。

@author: PC
"""

from cst_solver._guards import get_guard_state


class ValidationMixin:
    """
    CST 结构化验收 Mixin
    提供 ``validate_model()``：一次调用给出「工程当前是否健康」的结构化结论
    """

    def get_messages(self):
        """
        读取并清空 CST 的待处理消息。

        CST 的 VBA 失败**不会**抛 Python 异常，只会往消息队列里写一条；
        非空即代表上一步操作有问题。读取即清空（CST 自身行为）。

        :return: list, 消息列表（可能是字符串或消息对象）；空列表表示无消息
        """
        return list(self.cst_file.get_messages() or [])

    def validate_model(self, rebuild=True, messages_prefix='1D Results'):
        """
        验收当前工程：读消息 + 跑 Rebuild + 再读消息，返回结构化结果。

        :param rebuild: bool, 是否执行 ``Rebuild()`` 重放工程历史，默认 True。
            重放会重新生成几何，是发现「参数改了但历史没重建」的最后一道检查。
        :param messages_prefix: str, 预留参数（当前未用于过滤，仅为将来按导航树
            筛消息留出签名位置）
        :return: dict::

            {
              "status":     "success" | "error",   # 结论
              "messages":   [ ... ],               # 本次验收到的问题消息（含 rebuild 阶段）
              "rebuild_ok": bool,                  # Rebuild 本身是否干净
              "before":     [ ... ],               # 调用前积压的历史消息（已清空）
              "guard":      {...},                 # 守卫层发现摘要
            }

        判定规则（与 WORKFLOW §3 一致，不引入新口径）：

        - ``before`` 或 ``rebuild`` 阶段**任一条**消息 ⇒ ``status='error'``
        - ``rebuild=False`` 时 ``rebuild_ok`` 恒为 True（未执行即不作失败论）
        - 本方法**不抛异常**，调用方按 ``status`` 分流；这样它既能用在
          断言脚本里，也能用在「先跑一遍看看能不能继续」的探测场景
        """
        state = get_guard_state(self)

        before = self.get_messages()
        rebuild_ok = True
        rebuild_messages = []

        if rebuild:
            try:
                self.cst_file.model3d.Rebuild()
            except Exception as exc:          # 只有 Rebuild 本身炸了才走到这里
                rebuild_ok = False
                rebuild_messages = [f'Rebuild() 抛出异常：{exc!r}']
            else:
                rebuild_messages = self.get_messages()
                if rebuild_messages:
                    rebuild_ok = False
                else:
                    # 历史已重放 ⇒ 参数与几何重新一致，清掉脏标记
                    state.mark_rebuilt()

        messages = list(before) + list(rebuild_messages)
        return {
            'status': 'error' if messages else 'success',
            'messages': messages,
            'rebuild_ok': rebuild_ok,
            'before': before,
            'guard': state.summary(),
        }
