# -*- coding: utf-8 -*-
"""
材料构建器
==========
在建模之前确保工程中存在所需材料。

参考工程 ``AB_feed.cst`` 的历史树里，``Copper (annealed)`` 与
``Silicon (lossy)`` 是**显式创建**的两条最早记录；而本库的建模流水线
此前从不定义材料，一旦模板工程（``tmp.cst``）里没有这两个材料，
第一条 ``extrude`` 就会报
``The specified material does not exist``。

@author: PC
"""

# cst_solver.material.materials.new_material() 支持的预设材料
_PRESET_MATERIALS = (
    'Copper (annealed)',
    'Silicon (lossy)',
    'Quartz (Fused) (lossy)',
)

# 建模流水线默认需要的材料：介质结构用损耗硅，空心波导用退火铜
DEFAULT_MATERIALS = ('Silicon (lossy)', 'Copper (annealed)')


def build_materials(app, names=DEFAULT_MATERIALS):
    """
    确保工程中存在指定的预设材料。

    幂等：CST 的 ``With Material ... .Create`` 按名字定义材料，
    对已存在且定义相同的材料重复调用无副作用。

    :param app: cst_solver.setup 实例
    :param names: tuple, 材料名称序列，默认 ``('Silicon (lossy)', 'Copper (annealed)')``
    :return: list, 实际下发的材料名称列表
    :raises ValueError: names 中含 ``new_material()`` 不支持的预设材料名
        （该接口对未知名字只打印一句提示就返回，静默跳过会让后续建模
        在第一条 extrude 处才报错，故在此提前拦下）
    """
    unknown = [n for n in names if n not in _PRESET_MATERIALS]
    if unknown:
        raise ValueError(
            f"build_materials() 收到不支持的预设材料名：{unknown}；"
            f"cst_solver 的 new_material() 仅支持 {list(_PRESET_MATERIALS)}。"
            f"需要自定义材料请改用 create_material_custom()。")

    for name in names:
        app.new_material(name)
    return list(names)
