# -*- coding: utf-8 -*-
"""
命名管理器
==========
自动管理 CST 中 solid 名称，保证唯一、有意义、不冲突。

@author: PC
"""


class NameManager:
    """
    CST 实体名称管理器。
    自动生成唯一名称，支持多端口结构中的命名规范。
    """

    def __init__(self):
        self._counters = {}
        self._aliases = {}

    def get(self, prefix):
        """
        获取唯一名称，格式为 'prefix_N'。

        :param prefix: str, 名称前缀，如 'substrate', 'feed', 'wg'
        :return: str, 唯一名称，如 'substrate_1'
        """
        if prefix not in self._counters:
            self._counters[prefix] = 0
        self._counters[prefix] += 1
        return f"{prefix}_{self._counters[prefix]}"

    def alias(self, name, alias_name):
        """
        为已有名称起别名。

        :param name: str, 原名称
        :param alias_name: str, 别名
        """
        self._aliases[alias_name] = name

    def resolve(self, name):
        """
        解析名称，若为别名则返回原名称。

        :param name: str, 名称或别名
        :return: str, 原名称
        """
        return self._aliases.get(name, name)

    def get_feed(self, idx=1):
        """
        获取探针名称。

        :param idx: int, 探针序号（多端口用），默认 1
        :return: str, 如 'feed_1'
        """
        return f"feed_{idx}"

    def get_waveguide(self, idx=1):
        """
        获取波导名称。

        :param idx: int, 波导序号，默认 1
        :return: str, 如 'wg_1'
        """
        return f"wg_{idx}"

    def get_port(self, idx=1):
        """
        获取端口名称。

        :param idx: int, 端口序号，默认 1
        :return: str, 如 'port_1'
        """
        return f"port_{idx}"

    def get_crystal(self, side='A'):
        """
        获取光子晶体阵列名称。

        :param side: str, 'A' 或 'B'（VPC-A / VPC-B）
        :return: str, 如 'crystal_A'
        """
        return f"crystal_{side}"

    def reset(self):
        """重置所有计数器和别名。"""
        self._counters.clear()
        self._aliases.clear()

    def __repr__(self):
        total = sum(self._counters.values())
        return f"NameManager(generated={total}, aliases={len(self._aliases)})"
