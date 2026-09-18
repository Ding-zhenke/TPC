# -*- coding: utf-8 -*-
r"""
`scripts/classify_notebook_migration.py` 的离线自检
==================================================

这个脚本负责 P5「87 个 notebook 迁移」里 P1/P2/P3 的**全量分类与登记**。
它的判据必须被钉住，否则会出现第一版那种情况：
**特征正则写得太宽**（把 `wg1`/`add_port` 这类通用写法也算成"器件特征"），
于是 82 个 notebook 里 68 个被判成"有缺口" —— 等于没有结论。

本文件用**合成 notebook**覆盖每条判据：

============================  ============================================
场景                           期望
============================  ============================================
目录 → 类别/模板映射正确        `MPMBA` → 多端口天线 → `MultiPortAntenna`
GRIN 天线 + 就地 hexagon        `PARTIAL`，缺口是 `lens_in_situ`
GRIN 天线 + 只用 DXF            `COVERED`
MZI + 两组 `ax/ay`              `PARTIAL`，缺口是 `mzi_anti`
MZI + 10 点路径                 `PARTIAL`，缺口是 `mzi_parallel`
功分器 + `xq/yq`（2H4L）        `PARTIAL`，缺口是 `divider_2h4l`
通用写法（`wg1`/`add_port`）      **不产生缺口**（防噪声回归）
Leaky（无模板）                 `NO_TEMPLATE`
P3 分析类                       `NOT_MIGRATED`
文件缺失                        `FAIL`
============================  ============================================

运行方式::

    pytest tests/test_notebook_migration_classifier.py -v
"""

import importlib.util
import json
import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
_SCRIPTS = os.path.join(ROOT, 'scripts')
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)


def _load_module():
    path = os.path.join(_SCRIPTS, 'classify_notebook_migration.py')
    spec = importlib.util.spec_from_file_location('classify_notebook_migration',
                                                  path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope='module')
def classifier():
    return _load_module()


def _write_notebook(root, rel, code):
    """写一个合成 notebook（只有 code cell，够分类器读）。"""
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = {'cells': [{'cell_type': 'code', 'source': code.splitlines(True)}],
               'nbformat': 4, 'nbformat_minor': 5,
               'metadata': {}}
    with open(path, 'w', encoding='utf-8') as handle:
        json.dump(payload, handle, ensure_ascii=False)
    return path


# ============================================================
# 1. 目录 → 类别/模板映射
# ============================================================

@pytest.mark.parametrize('rel, category, template', [
    (r'MPMBA\Ant3_epc.ipynb', '多端口天线', 'MultiPortAntenna'),
    (r'多端口\Ant3_1W2N\Ant3_240D3_epc.ipynb', '多端口天线', 'MultiPortAntenna'),
    (r'开关尝试\AB\MZI.ipynb', 'MZI 开关', 'MZISwitch'),
    (r'功分器加天线\B5\Ant6_2H4L_epc.ipynb', '功分器', 'PowerDivider'),
    (r'单元天线GRIB\AB型\120°透镜\Ant1_grid.ipynb', 'GRIN 透镜单元天线',
     'GRINLensAntenna'),
    (r'椭圆透镜单元天线\BA\D120\x.ipynb', 'GRIN 透镜单元天线', 'GRINLensAntenna'),
    (r'Leaky\ANT_LEAKY_EPC_GRID.ipynb', '泄漏波天线', None),
    (r'针对隔离和开关的分析研究\x.ipynb', '分析/测试/优化', None),
])
def test_directory_maps_to_category_and_template(classifier, rel, category, template):
    got_category, got_template, _prio = classifier.classify(rel)
    assert got_category == category, rel
    assert got_template == template, rel


# ============================================================
# 2. 缺口判据（每类一条）
# ============================================================

def _audit(classifier, tmp_path, rel, code, priority):
    """在**临时目录**里造一个 notebook 并判定它。

    ⚠️ `LEGACY_ROOT` 是模块级全局：用完必须**还原**，否则后面的测试会继续拿
    临时目录去判真实的清点表（`test_registry_accounts_for_every_notebook`
    就是这么发现它的 —— 真实 notebook 被判成"读不到"⇒`FAIL`）。
    """
    _write_notebook(str(tmp_path), rel, code)
    previous = classifier.LEGACY_ROOT
    classifier.LEGACY_ROOT = str(tmp_path)
    try:
        return classifier.audit_one(rel, priority)
    finally:
        classifier.LEGACY_ROOT = previous


def test_grin_with_in_situ_hexagon_is_now_covered(classifier, tmp_path):
    """GRIN 天线用 CST 内 `app.hexagon()` 建环 ⇒ **已实现**
    （`GRINLensAntenna(lens_method='insitu')`），所以不再是缺口。
    """
    result = _audit(classifier, tmp_path,
                    r'单元天线GRIB\AB型\120°透镜\x.ipynb',
                    "app1.para('HEX_SIZE','a/sqr(3)/2')\napp1.hexagon('a', r1)\n",
                    'P1')
    assert result['status'] == 'COVERED', result
    assert result['gaps'] == []
    assert 'GRINLensAntenna' in classifier.TEMPLATE_CAPABILITIES
    assert 'lens_in_situ' in classifier.TEMPLATE_CAPABILITIES['GRINLensAntenna']


def test_in_situ_hexagon_outside_supported_templates_is_partial(classifier, tmp_path):
    """就地建环只有四个含透镜模板覆盖（`GRINLensAntenna` / `MultiPortAntenna` /
    `MZISwitch` / `PowerDivider`）—— 落到**别的**模板（这里是单元天线）上仍然是缺口，
    不能算「库里做到了就等于谁都能做」。
    """
    result = _audit(classifier, tmp_path,
                    r'普通单元天线\AB\MZI-GRIB-not-really.ipynb',
                    "app1.para('HEX_SIZE','a/sqr(3)/2')\napp1.hexagon('a', r1)\n",
                    'P1')
    assert result['status'] == 'PARTIAL', result
    assert result['template'] == 'UnitAntenna', result
    assert 'lens_in_situ' in result['gaps'], result


def test_in_situ_hexagon_on_multiport_is_covered(classifier, tmp_path):
    """多端口批次带透镜的 notebook = `MultiPortAntenna` 的三条路线覆盖
    （参考口径：单枚放原点）。"""
    result = _audit(classifier, tmp_path,
                    r'多端口\Ant3_1W2N\Ant3_240D3_epc.ipynb',
                    "app1.para('HEX_SIZE','a/sqr(3)/2')\n"
                    "app1.para('ec_a','Nx*a2')\napp1.dxf_import('lens.dxf')\n"
                    "app1.hexagon('a', r1)\n",
                    'P1')
    assert result['status'] == 'COVERED', result
    caps = classifier.TEMPLATE_CAPABILITIES['MultiPortAntenna']
    assert {'grin_lens', 'lens_dxf', 'lens_in_situ'} <= caps


def test_in_situ_hexagon_on_power_divider_is_covered(classifier, tmp_path):
    """功分器的 `1分4` 族就地建环 = `PowerDivider(lens_method='insitu')` 覆盖。"""
    result = _audit(classifier, tmp_path,
                    r'功分器加天线\1分4\Ant4_circle_DF.ipynb',
                    "app1.para('HEX_SIZE','a/sqr(3)/2')\napp1.hexagon('a', r1)\n",
                    'P2')
    assert result['status'] == 'COVERED', result
    assert result['template'] == 'PowerDivider'
    assert 'lens_in_situ' in classifier.TEMPLATE_CAPABILITIES['PowerDivider']


def test_grin_with_dxf_only_is_covered(classifier, tmp_path):
    """只用 DXF 的 GRIN 天线 ⇒ 模板覆盖（我们的两条入口正好是 DXF）。"""
    result = _audit(classifier, tmp_path,
                    r'单元天线GRIB\BA型\120°透镜\y.ipynb',
                    "app1.para('ec_a','Nx*a2')\napp1.dxf_import('lens.dxf')\n",
                    'P1')
    assert result['status'] == 'COVERED', result
    assert result['gaps'] == []


def test_mzi_with_two_arm_parameter_groups_is_partial(classifier, tmp_path):
    result = _audit(classifier, tmp_path, r'开关尝试\AB\MZI-anti.ipynb',
                    "app1.para('ax1','0')\napp1.para('ax2','2')\n", 'P2')
    assert result['status'] == 'PARTIAL'
    assert 'mzi_anti' in result['gaps'], result


def test_mzi_with_ten_point_path_is_partial(classifier, tmp_path):
    result = _audit(classifier, tmp_path, r'开关尝试\AB\MZI-parallel.ipynb',
                    "app1.para('px10','1')\n", 'P2')
    assert result['status'] == 'PARTIAL'
    assert 'mzi_parallel' in result['gaps'], result


def test_divider_with_2h4l_structure_is_partial(classifier, tmp_path):
    result = _audit(classifier, tmp_path, r'功分器加天线\B5\Ant6_2H4L_epc.ipynb',
                    "app1.para('xq1','2')\n", 'P2')
    assert result['status'] == 'PARTIAL'
    assert 'divider_2h4l' in result['gaps'], result


def test_plain_mzi_basic_is_covered(classifier, tmp_path):
    result = _audit(classifier, tmp_path, r'开关尝试\AB\MZI.ipynb',
                    "app1.para('ax','2')\napp1.para('ay','1')\n", 'P2')
    assert result['status'] == 'COVERED', result


# ============================================================
# 3. 防噪声回归：通用写法不算器件特征
# ============================================================

def test_generic_constructs_do_not_create_gaps(classifier, tmp_path):
    """
    `wg1` / `add_port` / `pick_face` / `px3` 这类**每个 notebook 都有**的写法
    不许被当成"器件特征" —— 第一版就是因此把 68/82 判成有缺口。
    """
    result = _audit(classifier, tmp_path, r'开关尝试\AB\MZI.ipynb',
                    "app1.para('px3','1')\napp1.pick_face('wg1','10')\n"
                    "app1.add_port(1)\napp1.polyline(data)\n", 'P2')
    assert result['gaps'] == [], result
    assert result['status'] == 'COVERED'


# ============================================================
# 4. 无模板 / 不迁移 / 文件缺失
# ============================================================

def test_leaky_has_no_template(classifier, tmp_path):
    result = _audit(classifier, tmp_path, r'Leaky\ANT_LEAKY_EPC_GRID.ipynb',
                    "app1.para('a','1')\n", 'P2')
    assert result['status'] == 'NO_TEMPLATE'
    assert result['template'] is None


def test_analysis_notebooks_are_not_migrated(classifier, tmp_path):
    result = _audit(classifier, tmp_path,
                    r'针对隔离和开关的分析研究\x.ipynb', "print(1)\n", 'P3')
    assert result['status'] == 'NOT_MIGRATED'
    assert '保留不迁移' in result['notes']


def test_missing_file_is_reported(classifier, tmp_path):
    """读不到 notebook ⇒ `FAIL`（不是静默跳过）。

    ⚠️ 用完**必须还原** `LEGACY_ROOT`（模块级全局）：不还原会让后面的测试
    拿临时目录去判真实清点表（`test_registry_accounts_for_every_notebook`
    就是这么抓到它的）。
    """
    previous = classifier.LEGACY_ROOT
    classifier.LEGACY_ROOT = str(tmp_path)
    try:
        result = classifier.audit_one(r'MPMBA\does_not_exist.ipynb', 'P1')
    finally:
        classifier.LEGACY_ROOT = previous
    assert result['status'] == 'FAIL'


def test_gap_meaning_covers_every_detectable_feature(classifier):
    """每个可检测特征都要有**人话说明**（否则登记表里会出现裸 key）。"""
    missing = sorted(set(classifier.FEATURE_PATTERNS)
                     - set(classifier.GAP_MEANING))
    covered_by_template = set()
    for caps in classifier.TEMPLATE_CAPABILITIES.values():
        covered_by_template |= caps
    assert not (set(missing) - covered_by_template), (
        f'这些特征没有说明文字：{missing}')


# ============================================================
# 6. 注释里的代码**不算特征**（2026-09-17 修正）
# ============================================================
#
# 真实案例：8 个 MZI notebook 把整段 GRIB 环透镜建环代码**注释掉了**
# （`#     app1.hexagon('r1','h', …)`），按原文匹配会凭空造出 9 个不存在的缺口。

def test_commented_out_lens_code_is_not_a_feature(classifier, tmp_path):
    """整行注释掉的就地建环 ⇒ 不算特征（该模板没有透镜也不该报缺口）。"""
    result = _audit(classifier, tmp_path,
                    r'多端口\Ant3_1W2N\x.ipynb',
                    "# app1.para('HEX_SIZE','a/sqr(3)/2')\n"
                    "# app1.hexagon('r1','h',center=[0,0,'-h/2'])\n"
                    "app1.para('a', 0.2425)\n",
                    'P1')
    assert result['status'] == 'COVERED', result
    assert result['gaps'] == [], result
    assert result['n_para'] == 1, result      # 注释里的 .para( 也不该计数


def test_active_lens_code_is_still_a_feature(classifier, tmp_path):
    """没被注释掉的就地建环仍然是特征（否则这条修正会掩盖真缺口）。

    用**单元天线**做例子：它没有透镜（四个含透镜模板都不是它），
    所以活代码必须被判成缺口。
    """
    result = _audit(classifier, tmp_path,
                    r'普通单元天线\AB\x.ipynb',
                    "app1.para('HEX_SIZE','a/sqr(3)/2')\n"
                    "app1.hexagon('r1','h',center=[0,0,'-h/2'])\n",
                    'P1')
    assert result['status'] == 'PARTIAL', result
    assert 'lens_in_situ' in result['gaps'], result
    assert result['n_para'] == 1, result


def test_line_tail_comments_do_not_hide_code(classifier, tmp_path):
    """行尾注释不影响同一行的代码；字符串里的 `#`（如颜色 `'#ff0000'`）不算注释。"""
    result = _audit(classifier, tmp_path,
                    r'普通单元天线\AB\x.ipynb',
                    "app1.hexagon('r1','h')  # 建一个孔\n"
                    "color = cmap('#ff0000')  # 颜色\n"
                    "app1.para('a', 0.2425)\n",
                    'P1')
    assert 'lens_in_situ' in result['gaps'], result

    clean = _audit(classifier, tmp_path,
                   r'多端口\Ant3_1W2N\y.ipynb',
                   "color = '#ff0000'\napp1.para('a', 0.2425)\n",
                   'P1')
    assert clean['status'] == 'COVERED', clean
    assert clean['n_para'] == 1, clean


def test_strip_comments_keeps_strings_and_code(classifier):
    """`strip_comments()` 的直接单元测试（含引号里的 `#`）。"""
    text = "a = 1  # 注释\nb = '#ff0000'\nc = 'x#y'  # 尾巴\n# 整行\n"
    out = classifier.strip_comments(text)
    assert 'a = 1' in out and '注释' not in out
    assert "b = '#ff0000'" in out
    assert "c = 'x#y'" in out and '尾巴' not in out
    assert '# 整行' not in out


def test_lens_self_rotation_covers_the_antenna_dphi_feature(classifier, tmp_path):
    """`dphi`（透镜绕自身近焦点自转）现在由 `GRINLensAntenna(lens_rotation=…)` 覆盖。

    ⚠️ `phase_dphi` 有两层含义，两个模板各覆盖一层：
    * 天线：**透镜自转**（参考 `*_rotation.ipynb` 的 `dphi`）；
    * 功分器：**第二个相位副本**（`dphi1/dphi2`，把透镜绕 z 转后复制）。
    """
    assert 'phase_dphi' in classifier.TEMPLATE_CAPABILITIES['GRINLensAntenna']
    assert 'phase_dphi' in classifier.TEMPLATE_CAPABILITIES['PowerDivider']
    result = _audit(classifier, tmp_path,
                    r'椭圆透镜单元天线\BA\rotation\x.ipynb',
                    "app1.para('dphi','10')\napp1.para('ec_a','Nx*a2')\n",
                    'P1')
    assert result['status'] == 'COVERED', result
    assert result['gaps'] == [], result


# ============================================================
# 8. 判据自身的第二个坑：**分析/绘图变量不算器件特征**（2026-09-18）
# ============================================================
#
# 真实案例：`开关尝试\AB\mzi_opt_cal_feed.ipynb` 用
# `dphi = np.rad2deg(np.angle(a) - np.angle(b))` **画相位差曲线** ——
# 那是"对结果做的分析"，不是器件特征；按裸标识符匹配会凭空造出一个缺口。

def test_analysis_variable_is_not_a_device_feature(classifier, tmp_path):
    """`dphi` 只作为分析/绘图变量时**不算**器件特征（只认 `para('dphi…')`）。"""
    result = _audit(classifier, tmp_path, r'开关尝试\AB\x.ipynb',
                    "dphi = np.rad2deg(np.angle(a) - np.angle(b))\n"
                    "ax.plot(f, dphi)\n",
                    'P2')
    assert result['status'] == 'COVERED', result
    assert result['gaps'] == [], result


def test_dphi_as_cst_parameter_is_still_a_feature(classifier, tmp_path):
    """真正当器件参数用（`para('dphi', …)`）时仍然是特征。"""
    result = _audit(classifier, tmp_path, r'开关尝试\AB\x.ipynb',
                    "app1.para('dphi','10')\n", 'P2')
    assert 'phase_dphi' in result['gaps'], result


def test_mzi_grib_lens_is_covered_by_mzi_switch(classifier, tmp_path):
    """`MZI-GRIB` 的活代码环透镜 = `MZISwitch(lens_method='insitu')` 覆盖。"""
    result = _audit(classifier, tmp_path, r'开关尝试\AB\MZI-GRIB.ipynb',
                    "app1.para('HEX_SIZE','a/sqr(3)/2')\n"
                    "app1.hexagon('r1','h',center=[0,0,'-h/2'])\n",
                    'P2')
    assert result['status'] == 'COVERED', result
    caps = classifier.TEMPLATE_CAPABILITIES['MZISwitch']
    assert {'grin_lens', 'lens_dxf', 'lens_in_situ'} <= caps


def test_pump_switching_is_covered_by_power_divider(classifier, tmp_path):
    """功分器家族的 `pump_switching`（自定义材料 + 开关圆柱）已由
    `PowerDivider(switch_mode=…)` 覆盖。"""
    result = _audit(classifier, tmp_path,
                    r'功分器加天线\椭圆透镜1div3\x.ipynb',
                    "app1.para('sigma1','0')\n"
                    "app1.create_material_custom(name='switch1', epsilon=11.9, mu=1,"
                    " kappa='sigma1', material_type='Normal')\n"
                    "app1.cylinder(center=['(px3+px4)/2','py3'], r=['rc1',0],"
                    " h=['-h/2','h/2'], name='pump1', material='switch1')\n",
                    'P2')
    assert result['status'] == 'COVERED', result
    assert 'pump_switching' in classifier.TEMPLATE_CAPABILITIES['PowerDivider']


# ============================================================
# 9. 判据自身的第三个坑：**docstring 交叉引用不算结构**（2026-09-18）
# ============================================================
#
# 真实案例：三个 `MPMBA/Ant3_*.ipynb` 的 `lens_update` docstring 里写着
# "参照 Ant6_2H4L_epc.ipynb 更新" —— 那只是**指路**，不代表该 notebook 有 2H4L
# 结构（它们连 `xq` 都没定义）。按名字匹配 `2H4L` 会凭空造出 3 个缺口。

def test_docstring_cross_reference_is_not_structure(classifier, tmp_path):
    """docstring 里提到 `2H4L` ≠ 有 2H4L 结构（真正的信号是 `xq` 数组/参数）。"""
    result = _audit(classifier, tmp_path,
                    r'MPMBA\x.ipynb',
                    'def lens_update(lens_para, r, lens_name):\n'
                    '    """生成渐变折射率透镜；参照 Ant6_2H4L_epc.ipynb 更新"""\n'
                    "    app1.para('a', 0.2425)\n",
                    'P1')
    assert result['status'] == 'COVERED', result
    assert 'divider_2h4l' not in result['gaps'], result


def test_real_xq_structure_is_still_a_feature(classifier, tmp_path):
    """真的定义了 `xq`（2H4L 结构）时仍然是特征。"""
    result = _audit(classifier, tmp_path,
                    r'功分器加天线\B5\x.ipynb',
                    "xq=np.array([2,])\napp1.para('xq1','2')\n", 'P2')
    assert 'divider_2h4l' in result['gaps'], result


# ============================================================
# 10. 迁移登记**完整性**：87 个 notebook 一个都不能漏
# ============================================================
#
# 计划原文（P5）：「按 87 个 notebook 清点表的 P0/P1/P2 顺序迁移，**每个**登记迁移结果
# 及几何/仿真验收；P3 保留并注明不迁移原因。」
# ⇒ 本条守住"每个都有判定"这一半（几何/仿真验收是另一半，属 D4/P4 的求解级）。

def test_registry_accounts_for_every_notebook(classifier):
    """清点表 87 行 = P0 的 5 个 + 本脚本判定的 82 个，且判定集合互不重复。"""
    rows = classifier.inventory_rows()
    assert len(rows) == 87, f'清点表行数变了：{len(rows)}'
    paths = [rel for rel, _prio in rows]
    assert len(set(paths)) == len(paths), '清点表里有重复行'

    p0 = [rel for rel, prio in rows if prio == 'P0']
    rest = [(rel, prio) for rel, prio in rows if prio != 'P0']
    assert len(p0) == 5 and len(rest) == 82, (len(p0), len(rest))

    allowed = {'COVERED', 'PARTIAL', 'NO_TEMPLATE', 'NOT_MIGRATED'}
    for rel, prio in rest:
        result = classifier.audit_one(rel, prio)
        assert result['status'] in allowed, (rel, result['status'])
        # 每个"有缺口"的判定都必须能说出缺口是什么
        if result['status'] in ('PARTIAL', 'NO_TEMPLATE'):
            assert result.get('gaps') or result.get('notes'), rel
    # P0 批次由另一个脚本登记（`scripts/verify_notebook_p0_migration.py`）
    assert len(p0) + len(rest) == 87
