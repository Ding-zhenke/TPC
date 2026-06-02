# -*- coding: utf-8 -*-
"""
CST 工作坐标系 (WCS) Mixin 模块
=================================
封装 WCS 对象的坐标系创建、变换、对齐等操作

@author: PC
"""


class WCSMixin:
    """
    CST 工作坐标系 (WCS) Mixin
    提供局部坐标系创建、旋转、平移、对齐、重置等功能
    """

    def wcs_reset(self):
        """
        将工作坐标系重置为全局坐标系 (WCS)

        恢复 WCS 与全局坐标系对齐，原点和轴向归零。
        """
        f1 = """WCS.Reset
"""
        self.cst_file.model3d.add_to_history("WCS Reset", f1)

    def reset_wcs(self):
        """
        重置工作坐标系（蛇形命名）
        等同于 wcs_reset()
        """
        self.wcs_reset()

    def wcs_rotate(self, axis, angle):
        """
        绕指定轴旋转工作坐标系

        :param axis: str, 旋转轴 'x'/'y'/'z'
        :param angle: float/str, 旋转角度（度）
        """
        f1 = f"""WCS.RotateWCS "{axis}", "{angle}"
"""
        self.cst_file.model3d.add_to_history(f"WCS Rotate {axis}={angle}", f1)

    def rotate_wcs(self, axis, angle):
        """
        旋转工作坐标系（蛇形命名）
        等同于 wcs_rotate()
        """
        self.wcs_rotate(axis, angle)

    def wcs_translate(self, vector):
        """
        平移工作坐标系

        :param vector: list, 平移矢量 [X, Y, Z]
        """
        f1 = f"""WCS.MoveWCS "{vector[0]}", "{vector[1]}", "{vector[2]}"
"""
        self.cst_file.model3d.add_to_history(f"WCS Translate {vector}", f1)

    def translate_wcs(self, vector):
        """
        平移工作坐标系（蛇形命名）
        等同于 wcs_translate()
        """
        self.wcs_translate(vector)

    def wcs_align(self, name, face_id=0, component='component1'):
        """
        将工作坐标系与指定实体的面对齐

        :param name: str, 实体名称
        :param face_id: int, 表面 ID，默认 0（需预先选取面）
        :param component: str, 组件名称
        """
        if face_id > 0:
            self.pick_face(name, face_id, component)
        f1 = """WCS.AlignWCSWithSelected "Face"
"""
        face_desc = f"face_{face_id}" if face_id > 0 else "picked"
        self.cst_file.model3d.add_to_history(
            f"WCS Align {name} {face_desc}", f1)

    def align_wcs(self, name, face_id=0, component='component1'):
        """
        对齐工作坐标系到实体面（蛇形命名）
        等同于 wcs_align()
        """
        self.wcs_align(name, face_id, component)

    def wcs_set_origin(self, point):
        """
        设置工作坐标系原点

        :param point: list, 原点坐标 [X, Y, Z]
        """
        f1 = f"""WCS.SetOrigin "{point[0]}", "{point[1]}", "{point[2]}"
"""
        self.cst_file.model3d.add_to_history(f"WCS Origin {point}", f1)

    def set_wcs_origin(self, point):
        """
        设置 WCS 原点（蛇形命名）
        等同于 wcs_set_origin()
        """
        self.wcs_set_origin(point)

    def wcs_rotate_axis(self, from_axis, to_axis):
        """
        将工作坐标系的指定轴旋转到与另一轴对齐
        例如将 WCS 的 X 轴旋转到全局 Y 轴方向

        :param from_axis: str, 当前轴 'x'/'y'/'z'
        :param to_axis: str, 目标轴 'x'/'y'/'z'
        """
        axis_map = {
            ('x', 'y'): ('z', 90), ('x', 'z'): ('y', -90),
            ('y', 'x'): ('z', -90), ('y', 'z'): ('x', 90),
            ('z', 'x'): ('y', 90), ('z', 'y'): ('x', -90),
        }
        if from_axis == to_axis:
            return  # 无需旋转
        key = (from_axis, to_axis)
        if key in axis_map:
            rot_axis, angle = axis_map[key]
            self.wcs_rotate(rot_axis, angle)
        else:
            raise ValueError(f"不支持的轴向变换: {from_axis} -> {to_axis}")

    def wcs_store(self, name):
        """
        保存当前工作坐标系为指定名称（用于后续恢复）

        :param name: str, 坐标系保存名称
        """
        f1 = f"""WCS.Store "{name}"
"""
        self.cst_file.model3d.add_to_history(f"WCS Store {name}", f1)

    def store_wcs(self, name):
        """
        保存工作坐标系（蛇形命名）
        等同于 wcs_store()
        """
        self.wcs_store(name)

    def wcs_restore(self, name):
        """
        恢复之前保存的工作坐标系

        :param name: str, 已保存的坐标系名称
        """
        f1 = f"""WCS.Restore "{name}"
"""
        self.cst_file.model3d.add_to_history(f"WCS Restore {name}", f1)

    def restore_wcs(self, name):
        """
        恢复工作坐标系（蛇形命名）
        等同于 wcs_restore()
        """
        self.wcs_restore(name)

    def wcs_scale(self, factor_u, factor_v):
        """
        设置工作坐标系的 UV 缩放因子（用于参数化建模）

        :param factor_u: float, U 方向缩放因子
        :param factor_v: float, V 方向缩放因子
        """
        f1 = f"""WCS.Scale "{factor_u}", "{factor_v}"
"""
        self.cst_file.model3d.add_to_history(
            f"WCS Scale u={factor_u} v={factor_v}", f1)

    def scale_wcs(self, factor_u, factor_v):
        """
        缩放工作坐标系（蛇形命名）
        等同于 wcs_scale()
        """
        self.wcs_scale(factor_u, factor_v)
