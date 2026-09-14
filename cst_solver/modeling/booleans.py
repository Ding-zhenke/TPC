# -*- coding: utf-8 -*-
"""
CST 布尔运算 Mixin 模块
=======================
封装 Solid 对象的 Add、Subtract、Insert、Intersect、Blend 等布尔运算

@author: PC
"""


class SolidOpsMixin:
    """
    CST 布尔运算 Mixin
    提供实体相加、相减、相交、插入、倒角、弯曲等操作
    """

    def add(self, name1, name2, component1='component1', component2='component1'):
        """
        布尔运算-相加：将两个实体合并为一个实体
        保留原函数名以兼容旧代码

        :param name1: str, 实体1名称
        :param name2: str, 实体2名称
        :param component1: str, 实体1归属组件
        :param component2: str, 实体2归属组件
        """
        f1 = f"""
        Solid.Add "{component1}:{name1}", "{component2}:{name2}"
        """
        self.cst_file.model3d.add_to_history(name1 + " add " + name2, f1)

    def boolean_add(self, name1, name2, component1='component1',
                    component2='component1'):
        """
        布尔相加（蛇形命名）
        等同于 add()
        """
        self.add(name1, name2, component1, component2)

    def subtract(self, name1, name2, component1='component1',
                 component2='component1'):
        """
        布尔运算-相减：从实体1中减去实体2的部分

        :param name1: str, 被减实体名称
        :param name2: str, 裁剪实体名称
        :param component1: str, 实体1归属组件
        :param component2: str, 实体2归属组件
        """
        f1 = f"""
        Solid.Subtract "{component1}:{name1}", "{component2}:{name2}"
        """
        self.cst_file.model3d.add_to_history(name1 + " subtract " + name2, f1)

    def boolean_subtract(self, name1, name2, component1='component1',
                         component2='component1'):
        """
        布尔相减（蛇形命名）
        等同于 subtract()
        """
        self.subtract(name1, name2, component1, component2)

    # ---------------------------------------------------------------
    # 兼容别名：历史拼写错误（substract → subtract）
    # 早期版本把 subtract 拼成了 substract，旧脚本大量使用该名字。
    # 现已统一为 subtract()，substract() 保留为等价别名，请勿在新代码中使用。
    # ---------------------------------------------------------------
    substract = subtract

    def insert(self, name1, name2, component1='component1',
               component2='component1'):
        """
        布尔运算-插入：在实体1中嵌入实体2，保留各自独立属性
        保留原函数名以兼容旧代码

        :param name1: str, 基础实体名称
        :param name2: str, 插入实体名称
        """
        f1 = f"""
        Solid.Insert "{component1}:{name1}", "{component2}:{name2}"
        """
        self.cst_file.model3d.add_to_history(name1 + " Insert " + name2, f1)

    def boolean_insert(self, name1, name2, component1='component1',
                       component2='component1'):
        """
        布尔插入（蛇形命名）
        等同于 insert()
        """
        self.insert(name1, name2, component1, component2)

    def intersect(self, name1, name2, component1='component1',
                  component2='component1'):
        """
        布尔运算-相交：仅保留两个实体的重叠交集部分
        保留原函数名以兼容旧代码

        :param name1: str, 实体1名称
        :param name2: str, 实体2名称
        """
        f1 = f"""
        Solid.Intersect "{component1}:{name1}", "{component2}:{name2}"
        """
        self.cst_file.model3d.add_to_history(name1 + " intersect " + name2, f1)

    def boolean_intersect(self, name1, name2, component1='component1',
                          component2='component1'):
        """
        布尔相交（蛇形命名）
        等同于 intersect()
        """
        self.intersect(name1, name2, component1, component2)

    def boolean_imprint(self, name1, name2, component1='component1',
                        component2='component1'):
        """
        布尔运算-压印：将实体2的形状压印到实体1表面

        :param name1: str, 被压印实体
        :param name2: str, 压印工具实体
        """
        f1 = f"""
        Solid.Imprint "{component1}:{name1}", "{component2}:{name2}"
        """
        self.cst_file.model3d.add_to_history(name1 + " imprint " + name2, f1)

    def blend(self, r):
        """
        对拾取的棱边执行倒圆角操作
        保留原函数名以兼容旧代码
        注意：调用前需先使用 pick_edge() 选取棱边

        :param r: float/str, 倒角半径
        """
        f1 = f"""
        Solid.BlendEdge "{r}"
        """
        self.cst_file.model3d.add_to_history("Blend edge ", f1)

    def blend_edge(self, r):
        """
        倒圆角（蛇形命名）
        等同于 blend()
        """
        self.blend(r)
