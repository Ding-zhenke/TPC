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

    # 注意：面旋转/面拉伸不在这里 —— 它们本来就在 cst_solver/__init__.py 的
    # FaceOpsMixin 里：rotation_face(name, angle, ...) / rotate_face(...) /
    # extrude_face(name, height, material='PEC', ...)，不要在本文件再定义一份，
    # 否则会按 MRO 遮蔽原版实现。

    def pick_clear(self):
        """清除当前所有选取状态"""
        self.cst_file.model3d.add_to_history("Pick clear",
                                             'Pick.ClearAllPicks\n')

    # ---- 按坐标点拾取（绕开面编号问题）----

    def pick_face_at(self, name, x, y, z, component='component1'):
        """
        按**坐标点**拾取实体表面。

        CST 的面编号（'10'、'9'、'22' …）与实体几何/生成顺序强相关，
        扭转、布尔、阵列之后编号会变，跨模型不可复用。给定一个落在目标面上的点
        就能稳定拾取，不必知道编号。

        :param name: str, 实体名称
        :param x, y, z: float/str, 位于目标表面上的点（可为 CST 表达式）
        :param component: str, 归属组件
        """
        f1 = f"""Pick.PickFaceFromPoint "{component}:{name}", "{x}", "{y}", "{z}"
        """
        self.cst_file.model3d.add_to_history(
            f'Pick face at ({x}, {y}, {z}): {name}', f1)

    def pick_edge_at(self, name, x, y, z, component='component1'):
        """
        按**坐标点**拾取实体棱边。

        与 ``pick_face_at`` 同理：棱边编号与几何/生成顺序强相关，
        给一个落在目标棱边上的点即可稳定拾取，不必知道编号。

        :param name: str, 实体名称
        :param x, y, z: float/str, 位于目标棱边上的点（可为 CST 表达式）
        :param component: str, 归属组件
        """
        f1 = f"""Pick.PickEdgeFromPoint "{component}:{name}", "{x}", "{y}", "{z}"
        """
        self.cst_file.model3d.add_to_history(
            f'Pick edge at ({x}, {y}, {z}): {name}', f1)

    def pick_point_at(self, x, y, z):
        """
        按坐标选取一个点。

        :param x, y, z: float/str, 点坐标（可为 CST 表达式）
        """
        f1 = f"""Pick.PickPointFromCoordinates "{x}", "{y}", "{z}"
        """
        self.cst_file.model3d.add_to_history(
            f'Pick point ({x}, {y}, {z})', f1)

    # ---- 读取选取 ID（按坐标反查，不改变选取状态）----

    def _pick_object(self):
        """
        获取 CST 的 Pick 子对象。

        :return: CST Pick COM 对象
        :raises RuntimeError: 当前 CST Python 接口未暴露 ``model3d.Pick``
        """
        try:
            return self.cst_file.model3d.Pick
        except AttributeError as exc:
            raise RuntimeError(
                "当前 CST Python 接口未暴露 model3d.Pick，无法读取选取 ID。"
                "可改用 pick_face_at() / pick_edge_at() 直接按坐标拾取，"
                "无需先知道编号。"
            ) from exc

    def get_face_id_from_point(self, name, x, y, z, component='component1'):
        """
        读取实体在指定坐标处的**面编号**（只查询，不改变选取状态）。

        对面编号的用途：CST 的 ``Solid.ChamferEdge`` 等少数接口只接受
        faceID。常规建模优先用 ``pick_face_at()`` 按坐标拾取，可绕开编号。

        :param name: str, 实体名称
        :param x, y, z: float/str, 位于目标表面上的点
        :param component: str, 归属组件
        :return: int 或 None, 面编号；查询失败返回 None
        :raises RuntimeError: 当前 CST Python 接口未暴露 model3d.Pick
        """
        pick = self._pick_object()
        try:
            return pick.GetFaceIdFromPoint(f"{component}:{name}", x, y, z)
        except Exception:
            return None

    def get_edge_id_from_point(self, name, x, y, z, component='component1'):
        """
        读取实体在指定坐标处的**棱边编号**（只查询，不改变选取状态）。

        :param name: str, 实体名称
        :param x, y, z: float/str, 位于目标棱边上的点
        :param component: str, 归属组件
        :return: int 或 None, 棱边编号；查询失败返回 None
        :raises RuntimeError: 当前 CST Python 接口未暴露 model3d.Pick
        """
        pick = self._pick_object()
        try:
            return pick.GetEdgeIdFromPoint(f"{component}:{name}", x, y, z)
        except Exception:
            return None

    def get_picked_count(self, kind='face'):
        """
        返回当前已选取的面/棱边/点数量（只查询）。

        :param kind: str, 'face' / 'edge' / 'point'，默认 'face'
        :return: int 或 None, 已选数量；查询失败返回 None
        :raises ValueError: kind 取值非法
        :raises RuntimeError: 当前 CST Python 接口未暴露 model3d.Pick
        """
        attr = {
            'face': 'GetNumberOfPickedFaces',
            'edge': 'GetNumberOfPickedEdges',
            'point': 'GetNumberOfPickedPoints',
        }.get(str(kind).lower())
        if attr is None:
            raise ValueError(
                f"kind 必须是 'face' / 'edge' / 'point'，当前为: {kind}")
        pick = self._pick_object()
        try:
            return getattr(pick, attr)()
        except Exception:
            return None

    def pick_face_auto(self, name, points=None, candidates=(), component='component1'):
        """
        稳健拾取表面：先按**坐标点**逐个试，再退回按**面编号**逐个试。

        以 ``cst_file.get_messages()`` 是否报错判断是否成功
        （CST 对不存在的面/点会给出消息；该方法读取后即清空消息）。

        :param name: str, 实体名称
        :param points: list, 候选点 [[x, y, z], ...]（坐标为 float 或 CST 表达式）
        :param candidates: list, 候选面编号 ['9', '22', ...]
        :param component: str, 归属组件
        :return: 成功返回 ('point', (x, y, z)) 或 ('id', fid)；全部失败返回 None
        """
        for p in (points or ()):
            px, py = p[0], p[1]
            pz = p[2] if len(p) > 2 else 0     # 允许只给 (x, y)，z 默认 0
            self.pick_face_at(name, px, py, pz, component=component)
            if not self.cst_file.get_messages():
                return ('point', (px, py, pz))
            self.pick_clear()                 # 失败的点可能留下无效选取，先清掉
        for fid in (candidates or ()):
            self.pick_face(name, fid, component=component)
            if not self.cst_file.get_messages():
                return ('id', fid)
            self.pick_clear()
        return None
