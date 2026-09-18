# -*- coding: utf-8 -*-
r"""
**真实 CST 输出**上的结果读取回归（P4/V7 的「读」半边）
======================================================

背景：`topo_modeler/tests/test_result_reader.py` 开头写着「本机没有任何『已存结果可读』
的工程 ……所以用**假的 Result 对象**」，并把它登记为**未验证风险**：
「`source` 是真 .cst 路径时，`cst_solver.Result(...)` 的实际读取路径仍未验证」。

2026-09-17 复查发现该前提**已不成立**：参考工程
`普通单元天线\Ant1_D_BA_120_Feed_antenna-DF.cst` 里**真的有求解结果**
（31 个结果树条目、run ids `[0, 1]`、`S1,1` 曲线 1001 点 / 300–380 GHz）。
而 CST 官方明确写着 `cst.results` **不需要运行中的 CST**（"No running instance of
CST Studio Suite is required for data access"）—— 于是这条「未验证风险」
可以**离线**关掉。

本文件就做这件事（需要本机装有 CST 的 Python 库、且参考工程存在；否则整文件 skip）：

* 用**真路径**构造 `cst_solver.Result` / `topo_modeler.ResultReader`，读曲线、峰位置、
  指定频点值与 `read_all_s_parameters()`，并导出 CSV 到临时目录；
* 缺项（`S9,9`）必须**报错**而不是返回空数据；
* **只读**：脚本级快照证明工程目录 3049 个文件一个都没变；
* 「工程不存在」必须给出可执行的原因（含非 ASCII 路径时 CST 会误报
  `UnicodeDecodeError`，本库已把它翻译成「工程文件不存在」）。

运行方式::

    pytest tests/test_result_reading_real_project.py -v
    python scripts/verify_result_reading.py        # 同一件事的独立脚本版（人可读输出）
"""

import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

CST_ROOT = os.environ.get('CST_INSTALL_PATH', r'C:\SOFTWARE\CST Studio Suite 2026')
CST_LIB = os.path.join(CST_ROOT, 'AMD64', 'python_cst_libraries')
REFERENCE = os.path.join(
    r'D:\成电博士生涯\拓扑光子晶体模型\硅基\普通单元天线',
    'Ant1_D_BA_120_Feed_antenna-DF.cst')

#: 真实参考工程的已知事实（由 scripts/verify_result_reading.py 实测记录）
REFERENCE_FACTS = {'run_ids': [0, 1], 'n_tree_items': 31, 'peak_min_db_below': -20.0}


def _ensure_lib():
    if not os.path.isdir(CST_LIB):
        return False
    if CST_LIB not in sys.path:
        sys.path.insert(0, CST_LIB)
    try:
        import cst.results                              # noqa: F401
    except Exception:                                   # noqa: BLE001
        return False
    return True


pytestmark = [
    pytest.mark.skipif(not _ensure_lib(),
                       reason='本机没有可导入的 CST Python 库（cst.results）'),
    pytest.mark.skipif(not os.path.isfile(REFERENCE),
                       reason='本机没有已求解的参考工程'),
]


@pytest.fixture(scope='module')
def reader():
    from topo_modeler.result_reader import ResultReader
    return ResultReader(REFERENCE, names=['S1,1'], run_id=0)


# ============================================================
# 真路径读取
# ============================================================

def test_result_opens_real_project_and_lists_tree():
    from cst_solver import Result

    result = Result(REFERENCE)
    items = list(result.get_tree_items())
    run_ids = sorted(int(r) for r in result.get_all_run_ids(max_mesh_passes_only=False))
    assert len(items) >= 20, f'结果树条目太少：{len(items)}'
    assert run_ids == REFERENCE_FACTS['run_ids']
    assert any('S-Parameters' in str(item) for item in items)


def test_reader_reads_the_real_s_parameter_curve(reader):
    names = reader.list_s_parameters()
    assert 'S1,1' in names, f'参考工程里应有 S1,1，实际 {names}'
    xs, ys = reader.read_s_parameters(names=['S1,1'])['S1,1']
    assert len(xs) > 100, f'曲线点数太少：{len(xs)}'
    assert 300.0 <= float(xs[0]) <= 310.0
    assert 370.0 <= float(xs[-1]) <= 380.0


def test_reader_peak_and_value_at_work_on_real_data(reader):
    peak = reader.peak_position('S1,1', kind='min')
    assert peak is not None
    freq, value_db = float(peak[0]), float(peak[1])
    assert 300.0 <= freq <= 380.0
    assert value_db < REFERENCE_FACTS['peak_min_db_below'], (
        f'反射最小值应明显低于 -20 dB，实测 {value_db:.3f} dB @ {freq:.3f} GHz')
    # 指定频点取值：与曲线一致（同一函数内部插值，不另行造数）
    value = reader.value_at('S1,1', freq, in_db=True)
    assert value == pytest.approx(value_db, abs=1e-6)


def test_result_read_all_and_export_csv(tmp_path):
    from cst_solver import Result

    result = Result(REFERENCE)
    data = result.read_all_s_parameters(run_id=0)
    assert 'S1,1' in data, f'read_all_s_parameters 没读到 S1,1：{list(data)[:5]}'

    out = tmp_path / 'sparams.csv'
    result.export_s_parameters_csv(str(out), run_id=0, names=['S1,1'])
    assert out.is_file() and out.stat().st_size > 1000
    header = out.read_text(encoding='utf-8-sig', errors='replace').splitlines()[0]
    assert 'S1,1' in header or 'freq' in header.lower()


def test_missing_result_item_raises_instead_of_empty_data(reader):
    from topo_modeler.result_reader import ResultReaderError

    with pytest.raises(ResultReaderError):
        reader.read_s_parameters(names=['S9,9'])


# ============================================================
# 只读性 & 错误信息
# ============================================================

def _snapshot(root):
    out = {}
    for dirpath, _dirnames, filenames in os.walk(root):
        for filename in filenames:
            path = os.path.join(dirpath, filename)
            try:
                stat = os.stat(path)
            except OSError:
                continue
            out[os.path.relpath(path, root)] = (stat.st_size, int(stat.st_mtime))
    return out


def test_reading_never_modifies_the_project():
    """读取必须是只读的：模块级快照前后比对（含 mtime）。"""
    from cst_solver import Result
    from topo_modeler.result_reader import ResultReader

    root = os.path.dirname(REFERENCE)
    before = _snapshot(root)
    Result(REFERENCE).get_tree_items()
    ResultReader(REFERENCE, names=['S1,1']).read_s_parameters(names=['S1,1'])
    after = _snapshot(root)

    changed = sorted(k for k in set(before) | set(after)
                     if before.get(k) != after.get(k))
    assert changed == [], f'读取动了工程里的文件：{changed[:5]}'


def test_missing_project_reports_a_clear_reason(tmp_path):
    """工程不存在 ⇒ 说「不存在」；含非 ASCII 字符时 CST 会误报 UnicodeDecodeError。"""
    from cst_solver import Result

    with pytest.raises(RuntimeError) as ascii_case:
        Result(str(tmp_path / 'no_such.cst'))
    assert '工程文件不存在' in str(ascii_case.value)

    with pytest.raises(RuntimeError) as chinese_case:
        Result(str(tmp_path / '不存在的工程.cst'))
    message = str(chinese_case.value)
    assert '工程文件不存在' in message
    assert 'UnicodeDecodeError' in message            # 原始原因仍保留在消息里


# ============================================================
# 多端口工程：`list_s_parameters()` 的不变式（2026-09-17 修掉的误报）
# ============================================================

#: `Leaky\ANT_LEAKY_EPC_GRID.cst` 里有一条**收敛监控**曲线
#: `1D Results\Convergence\S-Parameters\Reflection S-Parameters [1]`：
#: 路径含 `S-Parameters`、也确实挂在同名目录下，但**不是** S 参数。
LEAKY_REFERENCE = os.path.join(
    r'D:\成电博士生涯\拓扑光子晶体模型\硅基\Leaky',
    'ANT_LEAKY_EPC_GRID.cst')

leaky_only = pytest.mark.skipif(not os.path.isfile(LEAKY_REFERENCE),
                                reason='本机没有多端口的 Leaky 参考工程')


@leaky_only
def test_list_s_parameters_only_returns_readable_s_parameters():
    """
    **不变式**：`list_s_parameters()` 返回的每个名字都必须能真的读出来。

    修之前它会把收敛监控曲线 `Reflection S-Parameters [1]` 排在**第一个**返回，
    于是 `names[0]` 之类的调用直接失败。
    """
    from cst_solver import Result

    result = Result(LEAKY_REFERENCE)
    names = result.list_s_parameters()
    assert names == ['S1,1', 'S2,1'], names
    for name in names:
        xs, ys = result.read_s_parameter(name, 0).T
        assert len(xs) > 100 and len(xs) == len(ys)
    assert 'Reflection S-Parameters [1]' not in names


# ============================================================
# 路径写法在**整类**里统一（2026-09-17 修：三种方法三种约定）
# ============================================================

@leaky_only
def test_get_run_ids_and_get_result_item_accept_both_path_forms():
    """
    `get_run_ids('S-Parameters\\S1,1')` 曾经报 `tree path not found` ——
    当时只有 `read_1D()` 接受相对写法。现在三个方法统一。
    """
    from cst_solver import Result

    result = Result(LEAKY_REFERENCE)
    full = '1D Results\\S-Parameters\\S1,1'
    relative = 'S-Parameters\\S1,1'

    full_ids = result.get_run_ids(full)
    relative_ids = result.get_run_ids(relative)
    assert full_ids == relative_ids, (full_ids, relative_ids)
    assert full_ids, '真实工程应当至少有一个 run id'
    assert 0 in full_ids
    assert 0 not in result.get_run_ids(relative, skip_nonparametric=True)
    assert len(result.get_result_item(full).get_xdata()) == \
        len(result.get_result_item(relative).get_xdata())


@leaky_only
def test_reader_round_trip_on_the_multiport_project():
    """多端口工程：读出两条 S 参数、导出 CSV、取峰位置，全程可用。"""
    from topo_modeler.result_reader import ResultReader

    reader = ResultReader(LEAKY_REFERENCE, names=['S1,1', 'S2,1'], run_id=0)
    assert reader.list_s_parameters() == ['S1,1', 'S2,1']
    data = reader.read_s_parameters_db(names=['S1,1', 'S2,1'])
    assert set(data) == {'S1,1', 'S2,1'}
    for name, (xs, ys) in data.items():
        assert len(xs) == len(ys) > 100
        assert min(ys) < -30.0, f'{name} 的最小值应当明显低于 −30 dB'
    # `names[0]` 现在是真的 S 参数，取峰不会再炸
    peak = reader.peak_position('S1,1', kind='min')
    assert 290.0 <= peak[0] <= 380.0 and peak[1] < -30.0


# ============================================================
# 3 端口工程：6 条 S 参数（广域核验里发现的最复杂形态）
# ============================================================

THREE_PORT_REFERENCE = os.path.join(
    r'D:\成电博士生涯\拓扑光子晶体模型\硅基\MPMBA', 'Ant3_epc.cst')

three_port_only = pytest.mark.skipif(not os.path.isfile(THREE_PORT_REFERENCE),
                                     reason='本机没有 3 端口参考工程')

_EXPECTED_SIX = ['S1,1', 'S1,2', 'S2,1', 'S2,2', 'S3,1', 'S3,2']


@three_port_only
def test_three_port_project_lists_and_reads_all_six_parameters(tmp_path):
    """3 端口 ⇒ 6 条 S 参数，逐条可读；CSV 表头必须含全部 6 个名字。"""
    from cst_solver import Result

    result = Result(THREE_PORT_REFERENCE)
    assert result.list_s_parameters() == _EXPECTED_SIX

    data = result.read_all_s_parameters(run_id=0)
    assert sorted(data) == _EXPECTED_SIX
    for name, curve in data.items():
        assert len(curve) > 100, f'{name} 点数太少'
    lengths = {len(curve) for curve in data.values()}
    assert len(lengths) == 1, f'各条曲线长度不一致：{lengths}'

    out = tmp_path / 'three_port.csv'
    result.export_s_parameters_csv(str(out), run_id=0, names=_EXPECTED_SIX)
    lines = out.read_text(encoding='utf-8-sig', errors='replace').splitlines()
    assert len(lines) == lengths.pop() + 1              # 点数 + 表头
    for name in _EXPECTED_SIX:
        assert name in lines[0], f'CSV 表头缺 {name}：{lines[0]!r}'


@three_port_only
def test_three_port_reader_peak_and_pairing_work():
    """3 端口工程上，取峰与「谐振峰频差」判据都能跑（V3 用得上）。"""
    from topo_modeler.result_reader import ResultReader

    reader = ResultReader(THREE_PORT_REFERENCE, names=_EXPECTED_SIX, run_id=0)
    peak = reader.peak_position('S1,1', kind='min')
    assert 290.0 <= peak[0] <= 380.0
    # 同一条曲线自比：频差为 0（配对必须配得上，而不是 no_matched_resonance）
    verdict = reader.resonance_shift(reader, 'S1,1', min_prominence_db=0.5,
                                     limit_ghz=1.0)
    assert verdict['n_matched'] >= 1
    assert verdict['max_delta_ghz'] == pytest.approx(0.0)
    assert verdict['ok'] is True
