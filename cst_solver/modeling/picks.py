# -*- coding: utf-8 -*-
"""
CST 选取操作 Mixin 模块
=======================
封装 Pick 对象的棱边、端点、表面等选取功能

@author: PC
"""


class PickMixin:
    """
    CST 选取操作 Mixin
    提供棱边选取、端点选取、表面选取、清除选取等操作
    """

    def pick_edge(self, name, id1, id2, component='component1'):
        """
        拾取实体的指定棱边
        保留原函数名以兼容旧代码

        :param name: str, 实体名称
        :param id1: int/str, 棱边起始点 ID
        :param id2: int/str, 棱边终止点 ID
        :param component: str, 归属组件，默认 component1
        """
        f1 = f"""
        Pick.PickEdgeFromId "{component}:{name}", "{id1}", "{id2}"
        """
        self.cst_file.model3d.add_to_history("Pick edge: " + str(name) +
                                              f'{id1}_{id2}', f1)

    def pick_endpoint(self, name, id_val, component='component1'):
        """
        拾取实体的指定端点
        保留原函数名以兼容旧代码

        :param name: str, 实体名称
        :param id_val: int/str, 端点 ID
        :param component: str, 归属组件
        """
        f1 = f"""
        Pick.PickEndpointFromId "{component}:{name}", "{id_val}"
        """
        self.cst_file.model3d.add_to_history("Pick endpoint: " + str(name), f1)

    def pick_face(self, name, id_val, component='component1'):
        """
        拾取实体的指定表面
        保留原函数名以兼容旧代码

        :param name: str, 实体名称
        :param id_val: int/str, 表面 ID
        :param component: str, 归属组件
        """
        f1 = f"""
        Pick.PickFaceFromId "{component}:{name}", "{id_val}"
        """
        self.cst_file.model3d.add_to_history("Pick face: " + str(name), f1)

    def pick_vertex(self, name, id_val, component='component1'):
        """
        拾取实体的指定顶点

        :param name: str, 实体名称
        :param id_val: int/str, 顶点 ID
        :param component: str, 归属组件
        """
        f1 = f"""
        Pick.PickVertexFromId "{component}:{name}", "{id_val}"
        """
        self.cst_file.model3d.add_to_history("Pick vertex: " + str(name), f1)

    def set_edge(self, x1, y1, z1, x2, y2, z2):
        """
        手动创建指定两点之间的棱边（用于辅助建模/定位）
        保留原函数名以兼容旧代码

        :param x1,y1,z1: float/str, 起始点坐标
        :param x2,y2,z2: float/str, 终止点坐标
        """
        f1 = f"""Pick.AddEdge "{x1}", "{y1}", "{z1}", "{x2}", "{y2}", "{z2}"
        """
        self.cst_file.model3d.add_to_history("Set edge ", f1)

    def pick_clear(self):
        """清除当前所有选取状态"""
        self.cst_file.model3d.add_to_history("Pick clear",
                                             'Pick.ClearAllPicks\n')
