# -*- coding: utf-8 -*-
"""
CST 边界条件 Mixin 模块
=======================
封装 Boundary、Background、LayerStacking 等边界与背景设置

@author: PC
"""

import warnings

#: ``Background.Type`` 的**合法取值全集**（官方 VBA 参考：Background Object →
#: ``Type(enum)``，只有 normal / pec 两种）。历史上代码里写的 'PMC' / 'Open'
#: 都不是合法值 —— CST 会静默忽略，背景仍旧，调用方却以为设好了。
BACKGROUND_TYPES = ('normal', 'pec')

#: 背景「材料名」→ (相对介电常数 εr, 相对磁导率 μr)；``None`` 表示该名字对应
#: ``Type "pec"``（理想导体背景，不需要 εr/μr）。
#:
#: ⚠️ CST 的 Background **没有材料属性**，只有「类型 + εr + μr」，所以这里
#: 只登记**能无损翻译**的名字；其余名字一律要求调用方显式给 ``epsilon``/``mu``。
BACKGROUND_MATERIALS = {
    'vacuum': (1.0, 1.0),
    'air': (1.0, 1.0),
    'free space': (1.0, 1.0),
    'pec': None,
    'metal': None,
}

#: ``BACKGROUND_MATERIALS`` 里没有的材料名用的哨兵。
_UNKNOWN_MATERIAL = object()


class BoundaryMixin:
    """
    CST 边界条件 Mixin
    提供边界条件、背景材料、层叠设置等功能
    """

    def boundary(self, xmax='expanded open', xmin='expanded open',
                 ymax='expanded open', ymin='expanded open',
                 zmax='expanded open', zmin='expanded open',
                 Xsymmetry='none', Ysymmetry='none', Zsymmetry='none',
                 ApplyInAllDirections=False, OpenAddSpaceFactor=0.5):
        """
        配置仿真区域的边界条件
        保留原函数名以兼容旧代码

        :param xmax/xmin: str, X轴边界类型
        :param ymax/ymin: str, Y轴边界类型
        :param zmax/zmin: str, Z轴边界类型
          常见取值: 'expanded open', 'open', 'electric', 'magnetic', 'periodic', 'unit cell'
        :param Xsymmetry/Ysymmetry/Zsymmetry: str, 对称面
          'magnetic'-磁对称 'electric'-电对称 'none'-无对称
        :param ApplyInAllDirections: bool, 是否全局应用
        :param OpenAddSpaceFactor: float, 开放边界扩展空间系数
        """
        f1 = f"""
            With Boundary
        .Xmin "{xmax}"
        .Xmax "{xmin}"
        .Ymin "{ymax}"
        .Ymax "{ymin}"
        .Zmin "{zmax}"
        .Zmax "{zmin}"
        .Xsymmetry "{Xsymmetry}"
        .Ysymmetry "{Ysymmetry}"
        .Zsymmetry "{Zsymmetry}"
        .ApplyInAllDirections "{ApplyInAllDirections}"
        .OpenAddSpaceFactor "{OpenAddSpaceFactor}"
    End With
    """
        self.cst_file.model3d.add_to_history('Define boundary', f1)

    def set_boundary(self, **kwargs):
        """
        设置边界条件（蛇形命名）
        等同于 boundary(**kwargs)

        支持的关键字参数:
            xmin, xmax, ymin, ymax, zmin, zmax: 边界类型
            Xsymmetry, Ysymmetry, Zsymmetry: 对称面
            ApplyInAllDirections: 全局应用
            OpenAddSpaceFactor: 扩展空间系数
        """
        self.boundary(**kwargs)

    def set_background(self, material='Vacuum', xmin_space=0, xmax_space=0,
                       ymin_space=0, ymax_space=0, zmin_space=0, zmax_space=0,
                       background_type=None, apply_in_all_directions=False,
                       *, epsilon=None, mu=None):
        """
        设置背景材料与扩展空间

        ⚠️ 2026-10 修复：旧实现下发 ``.Material "<名字>"``，而 **Background 对象
        没有 ``.Material`` 方法** —— 官方 VBA 参考（Background Object）里
        Background 只有 ``Reset`` / ``Type(enum, 取值仅 normal|pec)`` /
        ``Epsilon`` / ``Mu`` / ``ElConductivity`` / ``ThermalType`` /
        ``ThermalConductivity`` / ``XminSpace…ZmaxSpace`` /
        ``ApplyInAllDirections``。往 ``With Background`` 里写 ``.Material``
        在本版本 CST 上无效（命令被忽略，背景仍是原来的材料，而调用方以为设好了）。

        CST 的背景**只能**用「类型 + εr + μr」表达，所以本方法现在这样翻译：

        - ``'Vacuum'`` / ``'Air'`` / ``'Free space'`` ⇒
          ``.Type "normal"`` + ``.Epsilon "1.0"`` + ``.Mu "1.0"``（默认，与 CST 默认一致）
        - ``'PEC'`` / ``'Metal'`` ⇒ ``.Type "pec"``（理想导体背景，不再下发 εr/μr）
        - 其它名字 ⇒ **报错**，除非同时给了 ``epsilon`` / ``mu``

        不认识的材料名**不静默退化成真空**（那只是把「设错了」换个地方藏起来）：
        要么显式给出 ``epsilon`` / ``mu``（此时 ``material`` 只当标签），
        要么用上面那些名字之一。历史上 ``'PMC'`` / ``'Open'`` 这两个类型名
        也一并被拒 —— 它们不是 Background 的合法枚举值。

        :param material: str, 背景材料名：'Vacuum' / 'Air' / 'PEC' / 'Metal'
            （别的名字必须同时给 ``epsilon`` 或 ``mu``）
        :param xmin_space/xmax_space: float, X方向扩展空间
        :param ymin_space/ymax_space: float, Y方向扩展空间
        :param zmin_space/zmax_space: float, Z方向扩展空间
        :param background_type: str 可选, 'normal' / 'pec'（大小写不敏感）。
            不传 = 由 ``material`` 推断（PEC 类名字 ⇒ 'pec'，其余 ⇒ 'normal'）
        :param apply_in_all_directions: bool, 是否全局应用
        :param epsilon: float 可选, 背景相对介电常数 εr（仅 ``normal`` 生效）
        :param mu: float 可选, 背景相对磁导率 μr（仅 ``normal`` 生效）
        :raises ValueError: 材料名无法表达且没给 ``epsilon``/``mu``，或
            ``background_type`` 不是 ``'normal'``/``'pec'``
        """
        item = str(material).strip().lower()
        known = BACKGROUND_MATERIALS.get(item, _UNKNOWN_MATERIAL)

        if epsilon is None and mu is None and known is _UNKNOWN_MATERIAL:
            raise ValueError(
                f"set_background() 无法表达材料 {material!r}：CST 的 Background "
                f"**没有材料属性**，只能用「类型 + εr + μr」描述（合法的类型只有 "
                f"{' / '.join(BACKGROUND_TYPES)}）。\n"
                f"  请改用 {sorted(BACKGROUND_MATERIALS)} 之一，"
                f"或直接给出 epsilon=/mu=（例如 epsilon=11.9 表示硅背景）。")

        if background_type is None:
            btype = 'pec' if known is None else 'normal'
        else:
            btype = str(background_type).strip().lower()
            if btype not in BACKGROUND_TYPES:
                raise ValueError(
                    f"set_background(background_type={background_type!r}) 不合法："
                    f"``Background.Type`` 只接受 {' / '.join(BACKGROUND_TYPES)}"
                    f"（'PMC'/'Open' 都不是 Background 的合法取值）。")

        apply_str = 'True' if apply_in_all_directions else 'False'

        eps, mu_r = self._resolve_background_material(item, known, epsilon, mu)

        lines = ['With Background',
                 '     .Reset',
                 f'     .Type "{btype}"']
        if btype == 'normal':
            lines += [f'     .Epsilon "{eps}"',
                      f'     .Mu "{mu_r}"']
        lines += [f'     .XminSpace "{xmin_space}"',
                  f'     .XmaxSpace "{xmax_space}"',
                  f'     .YminSpace "{ymin_space}"',
                  f'     .YmaxSpace "{ymax_space}"',
                  f'     .ZminSpace "{zmin_space}"',
                  f'     .ZmaxSpace "{zmax_space}"',
                  f'     .ApplyInAllDirections "{apply_str}"',
                  'End With']
        self.cst_file.model3d.add_to_history("Set Background", '\n'.join(lines))

    def _resolve_background_material(self, item, known, epsilon, mu):
        """
        把 ``material`` + ``epsilon``/``mu`` 归一成 CST 能表达的 (εr, μr)。

        只在 ``Type "normal"`` 时才会被用到 —— PEC 背景不需要这两个值。

        :param item: str, 小写化后的材料名
        :param known: tuple 或 None（PEC 类）或 ``_UNKNOWN_MATERIAL``
        :param epsilon: 调用方显式给的 εr，可为 None
        :param mu: 调用方显式给的 μr，可为 None
        :return: (εr, μr)
        """
        table_eps, table_mu = (1.0, 1.0) if known in (None, _UNKNOWN_MATERIAL) else known
        eps = table_eps if epsilon is None else epsilon
        mu_r = table_mu if mu is None else mu
        if known is _UNKNOWN_MATERIAL:
            warnings.warn(
                f"set_background(material={item!r})：CST 的 Background 没有材料属性，"
                f"该名字只当作标签，实际下发的是 εr={eps} / μr={mu_r} —— "
                f"请自行确认这就是你要的背景。",
                UserWarning, stacklevel=3)
        return eps, mu_r

    # ================================================================
    # 补充: LayerStacking 层叠设置
    # ================================================================

    def set_layer_stacking(self, direction='z', stack_type='Default',
                            periodicity=None):
        """
        设置层叠参数（用于多层板结构仿真）

        :param direction: str, 层叠方向 'x'/'y'/'z'，默认 'z'
        :param stack_type: str, 层叠类型 'Default'/'Periodic'，默认 'Default'
        :param periodicity: list 可选, 周期 [nx, ny]（仅 stack_type='Periodic' 时生效）
        """
        f1 = f"""With LayerStacking
     .Reset
     .Direction "{direction}"
     .StackingType "{stack_type}"
"""
        if periodicity:
            f1 += f'     .Periodicity "{periodicity[0]}", "{periodicity[1]}"\n'
        f1 += """End With"""
        self.cst_file.model3d.add_to_history("LayerStacking Config", f1)
