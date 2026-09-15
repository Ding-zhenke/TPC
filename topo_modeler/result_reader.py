# -*- coding: utf-8 -*-
r"""
结果读取与自动绘图（阶段 7 模块 5.1）
====================================
`ResultReader` = `cst_solver.Result` 的**批量化 + 可视化**外壳。

不重复造轮子
------------
底层读取全部复用 `cst_solver.Result`（阶段 5 已补齐 `list_s_parameters()` /
`read_all_s_parameters()` / `export_s_parameters_csv()`），本模块只加三件事：

1. **批量**：一次读回全部 S 参数 / 远场，不用手写循环；
2. **统一口径**：频率一律 float、S 值一律复数或 dB，**不把 CST 的复数外壳漏给调用方**
   （阶段 4 T6 踩过：CST 的 `xdata` 是 complex，直接算会触发
   `ComplexWarning: Casting complex values to real discards the imaginary part`）；
3. **出图 / 出报告**：转交给 `topo_modeler.report`（自包含 HTML），不在这里重写绘图。

离线可用
--------
`cst_solver.Result` 走 `cst.results.ProjectFile`，**不需要设计环境（DE）** ——
只要工程里已经存有仿真结果就能读（阶段 4 T6 就是这么做的）。
所以本模块可以在「不想占算力、不想开 CST」的时候随便跑。

可注入
------
`ResultReader(source)` 的 `source` 可以是：

- **工程路径**（str）：自己构造 `cst_solver.Result`；
- **任何有 `read_all_s_parameters()` 的对象**（真正的 `Result`、或测试用的假对象）。

第二条让本模块的核心逻辑**完全可离线验收** —— 测试不必造一个含结果的 .cst。

用法::

    from topo_modeler.result_reader import ResultReader

    rr = ResultReader(r'D:\out\wg_AB.cst')
    params = rr.read_s_parameters()          # {'S1,1': (freqs, complex...), ...}
    db = rr.read_s_parameters_db()           # {'S1,1': (freqs, db), ...}
    rr.export_csv('s_params.csv')
    rr.plot_all('report.html')               # 自包含 HTML

@author: PC
"""

import math
import os
from typing import Any, Dict, List, Optional, Sequence, Tuple

__all__ = [
    'ResultReader',
    'ResultReaderError',
]


class ResultReaderError(RuntimeError):
    """结果读取失败（工程无结果 / 底层接口报错）。"""


def _as_float_list(values) -> List[float]:
    """把（可能带复数外壳的）序列压成 float 列表。"""
    out = []
    for v in values:
        try:
            c = complex(v)
        except (TypeError, ValueError):
            out.append(float(v))
            continue
        out.append(c.real)
    return out


def _as_complex_list(values) -> List[complex]:
    """把序列压成 complex 列表。"""
    out = []
    for v in values:
        try:
            out.append(complex(v))
        except (TypeError, ValueError):
            out.append(complex(float(v), 0.0))
    return out


def _to_db(values) -> List[float]:
    """|S| → dB（20·log10|v|）；幅度 0 记 −300 dB（与阶段 5 的导出口径一致）。"""
    out = []
    for v in values:
        try:
            mag = abs(complex(v))
        except (TypeError, ValueError):
            mag = abs(float(v))
        out.append(20 * math.log10(mag) if mag > 0 else -300.0)
    return out


def _split(arr) -> Tuple[List[float], List[complex]]:
    """把 ``(n,2)`` 数组拆成 ``(频率 float 列表, 复数值列表)``。"""
    rows = list(arr)
    if not rows:
        return [], []
    xs, ys = [], []
    for row in rows:
        pair = list(row)
        if len(pair) < 2:
            raise ResultReaderError(f'结果数组每行应有 2 列，收到 {row!r}')
        xs.append(complex(pair[0]).real)
        ys.append(complex(pair[1]))
    return xs, ys


class ResultReader:
    """
    仿真结果读取器（`cst_solver.Result` 的批量 + 出图外壳）。

    :param source: str（.cst 路径）或任何实现了 `read_all_s_parameters()` 的对象
    :param names: 序列可选, 只读这些 S 参数名；不给则自动发现
    :param run_id: int, 运行 ID（0 = 当前/最新结果）
    :param cache: bool, 是否缓存已读结果（默认 True；同一个 reader 反复取不重复读盘）
    """

    def __init__(self, source, names: Optional[Sequence[str]] = None,
                 run_id: int = 0, cache: bool = True):
        self.source = source
        self.names = tuple(names) if names else None
        self.run_id = int(run_id)
        self.cache = bool(cache)
        self._raw: Optional[Dict[str, Any]] = None
        self.last_errors: Dict[str, str] = {}
        self._result = None

    # ------------------------------------------------------------
    # 底层
    # ------------------------------------------------------------

    @property
    def result(self):
        """
        底层 `cst_solver.Result`（或注入的对象）。

        `source` 是路径时才惰性构造 —— 这样导入本模块、甚至 `ResultReader(obj)`
        都不需要 CST；只有真的要读一个 .cst 才需要。
        """
        if self._result is None:
            if isinstance(self.source, str):
                try:
                    from cst_solver import Result
                except Exception as exc:            # pragma: no cover - 环境相关
                    raise ResultReaderError(
                        f'读 .cst 结果需要可导入的 cst_solver（{exc!r}）；'
                        f'也可以直接把一个已有 Result 对象传给 ResultReader()') from exc
                if not os.path.exists(self.source):
                    raise ResultReaderError(f'工程文件不存在：{self.source}')
                self._result = Result(self.source)
            else:
                self._result = self.source
        return self._result

    def list_s_parameters(self) -> List[str]:
        """
        可用 S 参数名。

        :return: list[str]；注入的对象没有 `list_s_parameters()` 时，
            退化为「读一次全部再取键名」
        """
        if self.names:
            return list(self.names)
        lister = getattr(self.result, 'list_s_parameters', None)
        if callable(lister):
            return list(lister())
        return sorted(self.read_s_parameters().keys())

    # ------------------------------------------------------------
    # 读
    # ------------------------------------------------------------

    def read_s_parameters(self, names: Optional[Sequence[str]] = None,
                          run_id: Optional[int] = None,
                          ignore_errors: bool = True) -> Dict[str, Tuple[List[float], List[complex]]]:
        """
        批量读回 S 参数。

        :param names: 序列可选, 只读这些；不给则用构造时的 names 或自动发现
        :param run_id: int 可选, 覆盖构造时的 run_id
        :param ignore_errors: bool, 单个 S 参数读失败时跳过（记进 `last_errors`）；
            False 则直接抛
        :return: dict, ``{名称: (频率 float 列表, 复数值列表)}``
        :raises ResultReaderError: 一个都没读到，或 `ignore_errors=False` 时出错
        """
        if self._raw is not None and self.cache and names is None and run_id is None:
            return self._raw

        rid = self.run_id if run_id is None else int(run_id)
        wanted = tuple(names) if names else self.names

        raw_reader = getattr(self.result, 'read_all_s_parameters', None)
        out: Dict[str, Tuple[List[float], List[complex]]] = {}
        errors: Dict[str, str] = {}

        if callable(raw_reader) and wanted is None:
            data = raw_reader(run_id=rid)
            self.last_errors = dict(getattr(self.result, 'last_errors', {}) or {})
            for name, arr in (data or {}).items():
                out[name] = _split(arr)
        else:
            for name in (wanted or ()):
                try:
                    arr = self.result.read_s_parameter(name, rid)
                    out[name] = _split(arr)
                except Exception as exc:            # noqa: BLE001 - 缺项是常态
                    if not ignore_errors:
                        raise ResultReaderError(f'读 {name} 失败：{exc!r}') from exc
                    errors[name] = repr(exc)
            self.last_errors = errors

        if not out:
            raise ResultReaderError(
                '没有读到任何 S 参数；'
                f'已知错误：{self.last_errors or "（无）"}。'
                '该工程可能还没算，或结果树里没有 S-Parameters。')
        if self.cache and names is None and run_id is None:
            self._raw = out
        return out

    def read_s_parameters_db(self, names: Optional[Sequence[str]] = None,
                             run_id: Optional[int] = None) -> Dict[str, Tuple[List[float], List[float]]]:
        """
        与 :meth:`read_s_parameters` 相同，但值转成 dB。

        :return: dict, ``{名称: (频率 float 列表, dB float 列表)}``
        """
        return {name: (xs, _to_db(ys))
                for name, (xs, ys) in
                self.read_s_parameters(names=names, run_id=run_id).items()}

    def value_at(self, name: str, freq_ghz: float, in_db: bool = True) -> float:
        """
        取某个频点上最近的一点的值（**不插值** —— CST 结果本来就是离散频点）。

        :param name: str, S 参数名，如 ``'S1,1'``
        :param freq_ghz: float, 目标频率 [GHz]
        :param in_db: bool, 是否返回 dB
        :return: float
        :raises ResultReaderError: 该 S 参数不存在
        """
        data = self.read_s_parameters(names=[name])
        if name not in data:
            raise ResultReaderError(f'结果里没有 {name}；可用：{sorted(data)}')
        xs, ys = data[name]
        idx = min(range(len(xs)), key=lambda i: abs(xs[i] - float(freq_ghz)))
        return _to_db([ys[idx]])[0] if in_db else abs(ys[idx])

    def peak_position(self, name: str, band: Optional[Tuple[float, float]] = None,
                      kind: str = 'min') -> Tuple[float, float]:
        """
        找谐振峰位置（判据「谐振峰偏差 < 1 GHz」要用它）。

        :param name: str, S 参数名（通常 ``'S1,1'``）
        :param band: tuple 可选, ``(fmin, fmax)` 只在带内找
        :param kind: str, ``'min'``（反射谷）或 ``'max'``
        :return: ``(频率 GHz, dB 值)``
        :raises ResultReaderError: 带内没有数据点
        """
        xs, ys = self.read_s_parameters_db(names=[name])[name]
        pairs = [(x, y) for x, y in zip(xs, ys)
                 if band is None or (band[0] <= x <= band[1])]
        if not pairs:
            raise ResultReaderError(
                f'{name} 在 {band or "全频段"} 内没有数据点')
        pick = min if kind == 'min' else max
        return pick(pairs, key=lambda p: p[1])

    def peak_shift(self, other, name: str = 'S1,1',
                   band: Optional[Tuple[float, float]] = None) -> float:
        """
        两个 reader 之间某个 S 参数的**谐振峰频差** [GHz]。

        这是阶段 4 的原始判据（「谐振峰偏差 < 1 GHz」）的**可执行版本** ——
        在此之前它只是文档里的一句话，没有 API 支撑。

        :param other: ResultReader 或 .cst 路径
        :param name: str, S 参数名
        :param band: tuple 可选, 只在带内找峰
        :return: float, ``|f_this − f_other|``（GHz）
        """
        if not isinstance(other, ResultReader):
            other = ResultReader(other, names=[name])
        f1, _ = self.peak_position(name, band=band)
        f2, _ = other.peak_position(name, band=band)
        return abs(f1 - f2)

    # ------------------------------------------------------------
    # 导出 / 出图
    # ------------------------------------------------------------

    def export_csv(self, path: str, in_db: bool = True) -> str:
        """
        导出成 CSV（**优先**用 `cst_solver.Result.export_s_parameters_csv()`；
        注入的对象没有该方法时，自己按同样的列格式写一份）。

        :param path: str, 输出路径
        :param in_db: bool, True 写 dB，False 写 ``_re`` / ``_im`` 两列
        :return: str, 写出的绝对路径
        """
        exporter = getattr(self.result, 'export_s_parameters_csv', None)
        if callable(exporter):
            return exporter(path, run_id=self.run_id, names=self.names, in_db=in_db)

        data = self.read_s_parameters()
        path = os.path.abspath(path)
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        names = sorted(data)
        freq = data[names[0]][0]
        with open(path, 'w', encoding='utf-8-sig', newline='') as fh:
            import csv as _csv
            writer = _csv.writer(fh)
            writer.writerow(['freq_GHz'] + names)
            for i in range(len(freq)):
                row = [f'{freq[i]:.10g}']
                for name in names:
                    v = data[name][1][i]
                    row.append(f'{_to_db([v])[0]:.10g}' if in_db else f'{v.real:.10g}')
                writer.writerow(row)
        return path

    def plot_all(self, path: str, title: str = '仿真结果报告',
                 meta: Optional[Dict[str, Any]] = None,
                 note: str = '', highlight: Optional[Sequence[Tuple[float, str]]] = None,
                 include_audit=None) -> str:
        """
        生成自包含 HTML 报告（S 参数曲线 + 可选审计小节）。

        :param path: str, 输出 .html 路径
        :param title: str, 报告标题
        :param meta: dict 可选, 顶部元信息
        :param note: str, 图下附注
        :param highlight: 可选, ``[(频点, 标注), …]``
        :param include_audit: AuditLog 可选, 一并附上审计小节
        :return: str, 写出的绝对路径
        """
        from topo_modeler.report import HtmlReport

        db = self.read_s_parameters_db()
        auto_meta = {'数据来源': str(self.source) if isinstance(self.source, str)
                     else type(self.source).__name__,
                     'run_id': self.run_id,
                     'S 参数': ', '.join(sorted(db))}
        if self.last_errors:
            auto_meta['读失败的项'] = ', '.join(sorted(self.last_errors))
        auto_meta.update(meta or {})

        rep = HtmlReport(title=title, meta=auto_meta)
        if include_audit is not None:
            rep.add_audit(include_audit)
        rep.add_s_parameters(db, note=note, highlight=highlight, in_db=False)
        if self.last_errors:
            rep.add_note('部分 S 参数读取失败（通常是该器件本来就没有那一项，'
                         '如单端口器件没有 S2,1）：' + ', '.join(sorted(self.last_errors)),
                         level='warn')
        return rep.write(path)

    def plot_s_parameters(self, path: str = 's_parameters.html',
                          **kwargs) -> str:
        """
        只画 S 参数（`plot_all` 的别名，便于链式脚本读起来自然）。

        :return: str, 写出的绝对路径
        """
        return self.plot_all(path, **kwargs)

    def __repr__(self):
        src = self.source if isinstance(self.source, str) else type(self.source).__name__
        return (f'ResultReader({src!r}, names={self.names}, run_id={self.run_id}, '
                f'cached={self._raw is not None})')
