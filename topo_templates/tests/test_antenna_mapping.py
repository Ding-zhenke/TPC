# -*- coding: utf-8 -*-
r"""
UnitAntenna 阵列范围与路径参数映射测试（P4/V1）
===============================================

守住什么
--------
真机实测（CST 2026，2026-09，见 `docs/validation/p4_real_machine_evidence.md` V1 节）
发现天线模板的阵列范围**不能**用 `path.get_array_range()`：

* 实测返回 `(26, 16, 1)` —— `yup=16`/`ydn=1` 既不对称也覆盖不到臂；
* 更要命的是 `ydn=1` 会让 `crystal.py` 下发 `int(ydn/2)` = **0 次复制**，
  CST 直接报 `Invalid number of repetitions`。

旧 notebook（参考工程 `普通单元天线\Ant1_D_{AB,BA}_120_Feed_antenna-DF`）的权威取值是：

=========================  ====================  ====================
                           AB（臂朝 +y）          BA（臂朝 −y）
=========================  ====================  ====================
`xup` = `x1+int(y1/2)`     **25**                **26**（多 1）
`yup` / `ydn` = `y1`       **14** / **14**        **14** / **14**
=========================  ====================  ====================

（x1 = 18 直段周期数、y1 = 14 臂长。）本文件把这些数字钉住，防止再次退回
「直接用 `get_array_range()`」。

`bend_angle` 语义（2026-09-17 离线逐位比对，证据 §4.5）
-----------------------------------------------------
`bend_angle` 是**张角**（两侧臂夹角）= 单臂相对直段偏角的 2 倍，与参考 notebook
文件名里的数字一致；臂的符号按拓扑取（AB 朝 +y、BA 朝 −y），两种拓扑互为镜像：

===========================  ====================  ====================
                           参考工程实测臂端       本库应得
===========================  ====================  ====================
AB 120                       (6.0625, **+2.9402**)  `turn(+60)`
BA 120                       (6.0625, **−2.9402**)  `turn(−60)`
===========================  ====================  ====================

因此 `bend_angle` 合法值只有 120 的整数倍（0 = 不拐弯）：60/180/300 会让单臂偏角
落在 30°/90°/150°，**不是三角晶格方向**，必须报错。

运行方式::

    pytest topo_templates/tests/test_antenna_mapping.py -v
"""

import math
import os
import sys
import warnings

import pytest

_TPC_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _TPC_ROOT not in sys.path:
    sys.path.insert(0, _TPC_ROOT)

from topo_templates import UnitAntenna      # noqa: E402

# 参考工程（Ant1_D_{AB,BA}_120_Feed_antenna-DF.cst）Parameters.json 的实测值
_REF_ARM_END = {
    'AB': (6.0625, +2.94015624584816),
    'BA': (6.0625, -2.94015624584816),
}


def _antenna(topology='AB', **kwargs):
    """构造模板实例（无 CST 环境时 `app` 为 None，但路径/参数照算）。"""
    params = dict(bend_angle=120, straight_length=18, arm_length=14,
                  topology=topology)
    params.update(kwargs)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')          # 「CST 初始化失败」的告警
        return UnitAntenna(**params)


def test_array_range_matches_reference_ab():
    """AB：xup = x1 + int(y1/2) = 25，yup = ydn = y1 = 14。"""
    antenna = _antenna('AB')
    assert (antenna.xup, antenna.yup, antenna.ydn) == (25, 14, 14)


def test_array_range_matches_reference_ba():
    """BA：xup 比 AB 多 1（= 26），yup = ydn 仍为 14。"""
    antenna = _antenna('BA')
    assert (antenna.xup, antenna.yup, antenna.ydn) == (26, 14, 14)


def test_array_range_never_returns_zero_repetitions():
    """回归：yup/ydn 必须成对且 ≥2 —— 否则 `int(ydn/2)` = 0，CST 直接报错。"""
    for topology in ('AB', 'BA'):
        antenna = _antenna(topology)
        assert antenna.yup == antenna.ydn >= 2
        assert int(antenna.yup / 2) >= 1
        assert int(antenna.ydn / 2) >= 1


def test_array_range_scales_with_arm_length():
    """阵列范围随臂长走（不是常量，也不是直段长度）。"""
    short = _antenna('AB', arm_length=8)
    long = _antenna('AB', arm_length=20)
    assert (short.yup, short.ydn) == (8, 8)
    assert (long.yup, long.ydn) == (20, 20)
    assert short.xup == 18 + 4          # straight + int(8/2)
    assert long.xup == 18 + 10


def test_path_endpoint_is_arm_length_steps_from_corner():
    """臂长必须是 arm_length 步（此前多走一步，与库自己的映射表不符）。"""
    antenna = _antenna('AB', arm_length=14)
    lattice = list(antenna.path.path_lattice)
    assert lattice[1] == (0, 18)                 # 直段终点
    dr = lattice[2][0] - lattice[1][0]
    dc = lattice[2][1] - lattice[1][1]
    assert max(abs(dr), abs(dc)) == 14           # 斜向一步同时改 r/c，步数取切比雪夫距离


def test_non_bent_antenna_still_works():
    """bend_angle=0（不拐弯）時不应崩：路径退化为两点。"""
    antenna = _antenna('AB', bend_angle=0)
    assert len(antenna.path.path_lattice) == 2
    assert antenna.yup == antenna.ydn == 14


def test_invalid_inputs_rejected():
    """参数校验仍然生效。"""
    with pytest.raises(ValueError):
        _antenna(topology='ab')
    with pytest.raises(ValueError):
        _antenna('AB', bend_angle=45)


# ============================================================
# `bend_angle` 语义（张角）与拓扑镜像 —— P4/V1，2026-09-17
# ============================================================

@pytest.mark.parametrize('topology', ['AB', 'BA'])
def test_arm_end_matches_reference_project(topology):
    """
    `bend_angle=120` 的臂端必须**逐位等于**参考工程的实测值。

    参考工程 `Ant1_D_{AB,BA}_120_Feed_antenna-DF.cst` 的 `Parameters.json`：
        AB: px3 = 6.0625, py3 = +2.94015624584816
        BA: px3 = 6.0625, py3 = -2.94015624584816
    """
    antenna = _antenna(topology)
    end_x, end_y = antenna.path.xy[-1]
    ref_x, ref_y = _REF_ARM_END[topology]
    assert math.isclose(end_x, ref_x, abs_tol=1e-9)
    assert math.isclose(end_y, ref_y, abs_tol=1e-9)


def test_topologies_are_mirror_images():
    """AB 与 BA 的臂必须是关于 y=0 的严格镜像（参考工程正是如此）。"""
    ab = _antenna('AB')
    ba = _antenna('BA')
    assert list(ab.path.path_lattice[:2]) == list(ba.path.path_lattice[:2])
    ab_end = ab.path.xy[-1]
    ba_end = ba.path.xy[-1]
    assert math.isclose(ab_end[0], ba_end[0], abs_tol=1e-9)      # x 相同
    assert math.isclose(ab_end[1], -ba_end[1], abs_tol=1e-9)     # y 相反


def test_bend_angle_is_aperture_not_turn():
    """
    `bend_angle` 是**张角**：turn 的实际转角是它的一半。

    `bend_angle=120` → 转角 60°（臂端 (6.0625, +2.9402)），**不是** turn(120)
    （那会给出 (2.6675, +2.9402)）。
    """
    antenna = _antenna('AB', bend_angle=120)
    assert antenna.path.path_lattice[-1] == (14, 18)             # = turn(+60)
    assert antenna.path.xy[-1][0] > 6.0                          # 臂端 x 到 6.0625
    folded = _antenna('AB', bend_angle=240)
    # 张角 240 → 转角 120°：臂端 x 收缩到 2.6675，与 120D 完全不同
    assert folded.path.xy[-1][0] < 3.0


def test_bend_angle_must_be_multiple_of_120():
    """单臂偏角必须是晶格方向：张角只能是 120 的整数倍；60/180/300 必须报错。"""
    for bad in (60, 180, 300, 90):
        with pytest.raises(ValueError, match='120'):
            _antenna('AB', bend_angle=bad)
    for good in (0, 120, 240, 360):
        assert _antenna('AB', bend_angle=good) is not None
