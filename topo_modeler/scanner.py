# -*- coding: utf-8 -*-
r"""
参数扫描（阶段 7 模块 5.3）
==========================
多参数组合扫描：枚举组合 → 交给执行器 → 汇总 → 出图 / 出 CSV / 出报告。

关键设计：**把「跑仿真」这件事注入进来**
----------------------------------------
计划里 ParameterScan 的输入是「`base_model` 模板实例」，那意味着它必须能开 CST。
但扫描真正的逻辑 —— 枚举组合、唯一命名、聚合、热力图行列对齐、CSV —— **一点都不依赖 CST**。

所以这里把执行器变成参数：

.. code-block:: python

    def runner(point) -> .cst 路径 | ResultReader | dict

- 返回**字符串** → 当作 .cst 路径，用 `ResultReader` 离线读结果；
- 返回**有 `read_s_parameters()` 的对象** → 直接当 reader 用；
- 返回**字典** → 直接当指标值用（不需要 CST 也不需要结果文件）。

于是：真跑 CST 时给一个「建模 → 求解 → 存盘」的 runner；
跑单测 / 只验证扫描逻辑时给一个桩 runner。**同一套扫描代码，两种用法。**

判据可执行
----------
计划原文的验证标准是「扫描结果合理，热力图正确」——**不可测量**。这里按
`stages/07` §5.2 的改写实现：

- 每个组合有**唯一** `name`，且 `name` 只由参数值决定（可复现、不撞名）；
- 每个点都能追溯到自己的参数组合、.cst 路径与状态；
- 热力图的行列标签**就是**扫描轴取值（`len(x_labels) == len(轴1)`）；
- 导出的 CSV 行数 == 组合数。

用法::

    from topo_modeler.scanner import ParameterScan, value_metric, peak_metric
    from topo_modeler import config

    base = config.example_config('straight_waveguide')
    scan = ParameterScan(base,
                         {'large_hole_ratio': [0.60, 0.65, 0.70],
                          'length': [16, 18]},
                         runner=my_cst_runner,          # 真跑 CST 时才需要
                         workdir='scan_out',
                         metric_specs={'S21@330': value_metric('S2,1', 330.0),
                                       'S11 谐振谷': peak_metric('S1,1')})
    scan.run()
    scan.export_csv('scan.csv')
    scan.report('scan.html')

@author: PC
"""

import csv
import itertools
import math
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

__all__ = [
    'ParameterScan',
    'ScanPoint',
    'ScanError',
    'value_metric',
    'peak_metric',
    'band_min_metric',
]


class ScanError(RuntimeError):
    """扫描配置非法（空参数、轴取值非法、指标定义错…）。"""


# ============================================================
# 指标（metric）工厂
# ============================================================

def value_metric(s_param: str, freq_ghz: float, in_db: bool = True) -> Callable:
    """
    取某个频点上某个 S 参数的值。

    :param s_param: str, 如 ``'S2,1'``
    :param freq_ghz: float, 目标频率 [GHz]（取最近点，不插值）
    :param in_db: bool, 是否返回 dB
    :return: callable(reader) -> float
    """
    def _m(reader):
        return reader.value_at(s_param, freq_ghz, in_db=in_db)
    _m.__name__ = f'{s_param}@{freq_ghz:g}GHz'
    return _m


def peak_metric(s_param: str = 'S1,1', kind: str = 'min',
                band: Optional[Tuple[float, float]] = None) -> Callable:
    """
    取谐振峰**位置**（频点）或峰值。

    :param s_param: str, 如 ``'S1,1'``
    :param kind: str, ``'min'``（反射谷）/ ``'max'``
    :param band: tuple 可选, 只在带内找
    :return: callable(reader) -> float（频点 GHz）
    """
    def _m(reader):
        return reader.peak_position(s_param, band=band, kind=kind)[0]
    _m.__name__ = f'{s_param} {"谷" if kind == "min" else "峰"}位'
    return _m


def band_min_metric(s_param: str, band: Tuple[float, float]) -> Callable:
    """
    取带内的最小值（dB）—— 用来表达「整个带内反射最差多少」。

    :param s_param: str, 如 ``'S1,1'``
    :param band: tuple, ``(fmin, fmax)`` GHz
    :return: callable(reader) -> float
    """
    def _m(reader):
        xs, ys = reader.read_s_parameters_db(names=[s_param])[s_param]
        vals = [y for x, y in zip(xs, ys) if band[0] <= x <= band[1]]
        if not vals:
            raise ScanError(f'{s_param} 在 {band} 内没有数据点')
        return min(vals)
    _m.__name__ = f'{s_param} 带内最小{band}'
    return _m


# ============================================================
# 扫描点
# ============================================================

@dataclass
class ScanPoint:
    """
    一个参数组合（= 一次待执行的建模 + 仿真）。

    :param index: int, 组合序号（从 0 起，按枚举顺序）
    :param name: str, **唯一**标识（只由参数值决定 ⇒ 可复现、不撞名）
    :param params: dict, 本次组合的参数取值
    :param config: dict, 已把参数写进对应小节后的完整配置
    :param cst_path: str, 预期/实际的 .cst 路径
    """

    index: int
    name: str
    params: Dict[str, Any]
    config: Dict[str, Any]
    cst_path: str = ''
    status: str = 'pending'                 # pending / ok / error / skipped
    error: str = ''
    duration_s: float = 0.0
    metrics: Dict[str, float] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        """这一步是否成功。"""
        return self.status == 'ok'

    def row(self, param_names: Sequence[str], metric_names: Sequence[str]) -> List[Any]:
        """CSV / 表格用的一行。"""
        return ([self.index, self.name, self.status, self.cst_path]
                + [self.params.get(p, '') for p in param_names]
                + [self.metrics.get(m, '') for m in metric_names]
                + [round(self.duration_s, 3)])


# ============================================================
# 扫描器
# ============================================================

def _sanitize(text: str, limit: int = 40) -> str:
    """把参数值变成能进文件名的一段（去掉路径分隔符等）。"""
    out = re.sub(r'[^0-9A-Za-z._+-]+', '', str(text))
    return (out or 'x')[:limit]


class ParameterScan:
    """
    多参数组合扫描。

    :param base_config: dict, 基础配置（会被 `validate_config()` 校验）
    :param params: dict, ``{参数名: 取值序列}``；空序列或无参数会报错
    :param runner: callable 可选, ``runner(point) -> 路径 | reader | dict``；
        不传则 `run()` 时必须给
    :param workdir: str, 每个组合的 .cst 输出目录（默认当前目录）
    :param audit: AuditLog 可选, 每个组合都会记一条（含耗时与状态）
    :param metric_specs: dict, ``{指标名: callable(reader) -> float}``；
        用 :func:`value_metric` / :func:`peak_metric` / :func:`band_min_metric` 构造
    :param apply_to: str 或 dict, 参数写进哪个配置小节；
        传字符串表示全部写进该小节，传 dict 表示 ``{参数名: 小节}``
    :param model_type: str 可选, 覆盖 `base_config` 里的 `model.type`
    :param dry_run: bool, True 时 `run()` 只枚举不执行（等于只调 `plan()`）
    """

    def __init__(self, base_config, params: Dict[str, Sequence],
                 runner: Optional[Callable] = None, workdir: str = '.',
                 audit=None, metric_specs: Optional[Dict[str, Callable]] = None,
                 apply_to: Any = 'geometry', model_type: Optional[str] = None,
                 name: Optional[str] = None):
        if not params:
            raise ScanError('params 不能为空 —— 没有要扫描的参数')
        self.axis_names: List[str] = list(params.keys())
        self.axis_values: Dict[str, List[Any]] = {}
        for key, values in params.items():
            seq = list(values)
            if not seq:
                raise ScanError(f'参数 {key!r} 的取值序列为空')
            if len(seq) != len(set(map(repr, seq))):
                raise ScanError(f'参数 {key!r} 的取值序列里有重复项：{seq}')
            self.axis_values[key] = seq

        self.workdir = os.path.abspath(workdir)
        self.runner = runner
        self.audit = audit
        self.metric_specs: Dict[str, Callable] = dict(metric_specs or {})
        self.model_type = model_type
        self.stem = name or (str(base_config.get('model', {}).get('type', 'model')))
        self.apply_to = apply_to
        self._base_config = base_config
        self._points: Optional[List[ScanPoint]] = None
        self.last_errors: Dict[str, str] = {}

    # ------------------------------------------------------------
    # 枚举
    # ------------------------------------------------------------

    def _section_for(self, param: str) -> str:
        if isinstance(self.apply_to, dict):
            return self.apply_to.get(param, 'geometry')
        return str(self.apply_to)

    def combinations(self) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
        """
        笛卡尔积枚举：返回 ``[(参数取值, 完整配置), …]``。

        **这是纯函数** —— 不碰 CST、不碰磁盘，可以单独调用来检查组合数对不对。

        :return: list[tuple[dict, dict]]
        """
        from topo_modeler import config as _config

        names = self.axis_names
        out = []
        for combo in itertools.product(*(self.axis_values[n] for n in names)):
            values = dict(zip(names, combo))
            cfg = _copy_config(self._base_config)
            for key, value in values.items():
                cfg.setdefault(self._section_for(key), {})[key] = value
            clean = _config.validate_config(cfg, model_type=self.model_type)
            out.append((values, clean))
        return out

    def name_for(self, index: int, values: Dict[str, Any]) -> str:
        """
        组合的**唯一**名字：``<stem>_<参数名><值>-…``。

        只由参数值决定（不含序号以外的随机成分），所以同样配置重跑名字一致。

        :param index: int, 组合序号
        :param values: dict, 参数取值
        :return: str
        """
        tag = '-'.join(f'{k}{_sanitize(v)}' for k, v in values.items())
        return f'{self.stem}_{tag}' if tag else f'{self.stem}_{index:03d}'

    def plan(self) -> List[ScanPoint]:
        """
        生成扫描计划（**不执行**）。

        :return: list[ScanPoint]
        """
        points = []
        for i, (values, cfg) in enumerate(self.combinations()):
            point = ScanPoint(index=i, name=self.name_for(i, values),
                              params=values, config=cfg)
            point.cst_path = os.path.join(self.workdir, point.name + '.cst')
            points.append(point)
        self._points = points
        return points

    @property
    def points(self) -> List[ScanPoint]:
        """当前扫描点（未 `plan()` / `run()` 过则自动 plan）。"""
        if self._points is None:
            self.plan()
        return self._points

    @property
    def n_combinations(self) -> int:
        """组合数 = 各轴取值数之积。"""
        total = 1
        for values in self.axis_values.values():
            total *= len(values)
        return total

    # ------------------------------------------------------------
    # 执行
    # ------------------------------------------------------------

    def run(self, runner: Optional[Callable] = None,
            continue_on_error: bool = True, echo: bool = False) -> 'ParameterScan':
        """
        依次执行每个组合。

        **串行**执行：并发模型尚未在真机上确认（见阶段 5 §5.7.2），
        而且 CST 的 COM/许可约束下多实例风险不明 —— 这里不做并行，
        要并行请自己在 runner 里排队，本方法不替你决定。

        :param runner: callable 可选, 覆盖构造时的 runner
        :param continue_on_error: bool, 单个组合失败是否继续（失败会记进 `point.error`）
        :param echo: bool, True 时每步打印一行进度
        :return: self
        :raises ScanError: 没有 runner，或 `continue_on_error=False` 时某个组合失败
        """
        runner = runner or self.runner
        if runner is None:
            raise ScanError(
                'run() 需要一个执行器：ParameterScan(..., runner=…) 或 run(runner=…)。\n'
                '  runner(point) 应返回三者之一：.cst 路径 / ResultReader / 指标字典。')
        os.makedirs(self.workdir, exist_ok=True)

        for point in self.plan() if self._points is None else self._points:
            point.status = 'running'
            t0 = time.perf_counter()
            try:
                payload = runner(point)
                self._absorb(point, payload)
                point.status = 'ok'
            except BaseException as exc:                     # noqa: BLE001
                point.status = 'error'
                point.error = repr(exc)
                self.last_errors[point.name] = repr(exc)
                if not continue_on_error:
                    point.duration_s = time.perf_counter() - t0
                    self._audit(point)
                    raise ScanError(
                        f'组合 {point.name} 失败（continue_on_error=False）：{exc!r}') from exc
            finally:
                point.duration_s = time.perf_counter() - t0
            self._audit(point)
            if echo:
                flag = 'OK ' if point.ok else 'x  '
                metrics = ', '.join(f'{k}={v:.4g}' for k, v in point.metrics.items())
                print(f'[{point.index + 1}/{self.n_combinations}] {flag} '
                      f'{point.name}  {point.duration_s:.2f}s  {metrics}')
        return self

    def _absorb(self, point: ScanPoint, payload):
        """
        把 runner 的返回值归一化成 reader / 指标。

        三种形态（见模块 docstring）：

        - **字典** → 直接当指标值用；⚠️ 此时 `metric_specs` **不会**被执行
          （没有 reader 可算），这一点会记进 `last_errors['_contract']`，
          免得「设了指标却一直没值」查不出来；
        - **字符串** → 当 .cst 路径，用 `ResultReader` 离线读；
        - **其它** → 当 reader 对象，直接用 `metric_specs` 算指标。
        """
        if payload is None:
            return
        if isinstance(payload, dict) and not hasattr(payload, 'read_s_parameters'):
            point.metrics.update({k: float(v) for k, v in payload.items()
                                  if _is_number(v)})
            if self.metric_specs:
                self.last_errors['_contract'] = (
                    'runner 返回了指标字典，因此 metric_specs '
                    f'({", ".join(self.metric_specs)}) 未被执行 —— '
                    '两者取其一：要么让 runner 返回 reader/路径，要么直接用字典给出指标')
            return
        reader = payload
        if isinstance(payload, str):
            point.cst_path = os.path.abspath(payload)
            from topo_modeler.result_reader import ResultReader
            reader = ResultReader(payload)
        for name, spec in self.metric_specs.items():
            try:
                point.metrics[name] = float(spec(reader))
            except Exception as exc:                     # noqa: BLE001
                self.last_errors[f'{point.name}:{name}'] = repr(exc)

    def _audit(self, point: ScanPoint):
        if self.audit is None:
            return
        self.audit.record('scan_point', status=point.status,
                          duration_s=point.duration_s, name=point.name,
                          params=point.params, cst_path=point.cst_path,
                          error=point.error, metrics=point.metrics)

    # ------------------------------------------------------------
    # 汇总
    # ------------------------------------------------------------

    @property
    def failed(self) -> List[ScanPoint]:
        """失败的点。"""
        return [p for p in self.points if p.status == 'error']

    @property
    def succeeded(self) -> List[ScanPoint]:
        """成功的点。"""
        return [p for p in self.points if p.ok]

    @property
    def metric_names(self) -> List[str]:
        """出现过的指标名（保持首次出现顺序）。"""
        names: List[str] = list(self.metric_specs)
        for point in self.points:
            for key in point.metrics:
                if key not in names:
                    names.append(key)
        return names

    def metric_matrix(self, metric: str, ax_x: str, ax_y: str
                      ) -> Tuple[List[List[float]], List[Any], List[Any]]:
        """
        把某个指标摊成二维矩阵（热力图用）。

        :param metric: str, 指标名
        :param ax_x: str, 横轴参数名
        :param ax_y: str, 纵轴参数名
        :return: ``(matrix, x_labels, y_labels)`` —— ``matrix[i][j]`` 对应
            ``(y_labels[i], x_labels[j])``；缺的点填 ``nan``
        :raises ScanError: 轴名不在扫描参数里，或该轴不是恰好一维取值
        """
        for axis in (ax_x, ax_y):
            if axis not in self.axis_values:
                raise ScanError(
                    f'轴 {axis!r} 不在扫描参数里；可用的轴：{self.axis_names}')
        xs = list(self.axis_values[ax_x])
        ys = list(self.axis_values[ax_y])
        idx_x = {repr(v): j for j, v in enumerate(xs)}
        idx_y = {repr(v): i for i, v in enumerate(ys)}
        matrix = [[float('nan')] * len(xs) for _ in ys]
        for point in self.points:
            if not point.ok or metric not in point.metrics:
                continue
            key_x = repr(point.params.get(ax_x))
            key_y = repr(point.params.get(ax_y))
            if key_x in idx_x and key_y in idx_y:
                matrix[idx_y[key_y]][idx_x[key_x]] = point.metrics[metric]
        return matrix, xs, ys

    def series_for(self, metric: str, along: str) -> Dict[Any, Tuple[List, List]]:
        """
        沿某个轴取曲线（其他轴固定时最有用）。

        :param metric: str, 指标名
        :param along: str, 沿哪个参数变化
        :return: dict, ``{其余参数取值组合: (along 取值列表, 指标列表)}``
        """
        if along not in self.axis_values:
            raise ScanError(f'参数 {along!r} 不在扫描参数里')
        others = [n for n in self.axis_names if n != along]
        groups: Dict[Any, Tuple[List, List]] = {}
        for point in self.points:
            if not point.ok or metric not in point.metrics:
                continue
            key = tuple(point.params.get(n) for n in others)
            bucket = groups.setdefault(key, ([], []))
            bucket[0].append(point.params.get(along))
            bucket[1].append(point.metrics[metric])
        # 按 along 顺序排好
        order = {repr(v): i for i, v in enumerate(self.axis_values[along])}
        out = {}
        for key, (xs, ys) in groups.items():
            pairs = sorted(zip(xs, ys), key=lambda p: order.get(repr(p[0]), 0))
            out[key] = ([p[0] for p in pairs], [p[1] for p in pairs])
        return out

    # ------------------------------------------------------------
    # 导出与出图
    # ------------------------------------------------------------

    def export_csv(self, path: str) -> str:
        """
        导出扫描结果 CSV（**行数 == 组合数**）。

        列：``index, name, status, cst_path, <参数…>, <指标…>, duration_s``

        :param path: str, 输出路径
        :return: str, 写出的绝对路径
        """
        path = os.path.abspath(path)
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        header = (['index', 'name', 'status', 'cst_path']
                  + self.axis_names + self.metric_names + ['duration_s'])
        with open(path, 'w', encoding='utf-8-sig', newline='') as fh:
            writer = csv.writer(fh)
            writer.writerow(header)
            for point in self.points:
                writer.writerow(point.row(self.axis_names, self.metric_names))
        return path

    def plot_heatmap(self, path: str = 'scan_heatmap.html',
                     metric: Optional[str] = None,
                     ax_x: Optional[str] = None, ax_y: Optional[str] = None,
                     title: str = '参数扫描', digits: int = 3) -> str:
        """
        出热力图（自包含 HTML）。

        :param path: str, 输出 .html
        :param metric: str 可选, 指标名；不给则取第一个
        :param ax_x: str 可选, 横轴参数；不给则取第一个参数
        :param ax_y: str 可选, 纵轴参数；不给则取第二个（**必须有两个参数轴**）
        :param title: str, 标题
        :param digits: int, 格子小数位
        :return: str, 写出的绝对路径
        :raises ScanError: 参数轴少于 2 个
        """
        if len(self.axis_names) < 2:
            raise ScanError(
                f'热力图需要两个参数轴，当前只有 {self.axis_names}；'
                f'一维扫描请用 plot_curve()')
        metric = metric or (self.metric_names[0] if self.metric_names else None)
        if metric is None:
            raise ScanError('没有任何指标可用于出图')
        ax_x = ax_x or self.axis_names[0]
        ax_y = ax_y or self.axis_names[1]
        matrix, xl, yl = self.metric_matrix(metric, ax_x, ax_y)
        from topo_modeler.report import HtmlReport
        rep = HtmlReport(title=title, meta={
            '指标': metric, '横轴': ax_x, '纵轴': ax_y,
            f'组合数': self.n_combinations, '失败': len(self.failed)})
        rep.add_heatmap(matrix, xl, yl, title=f'{metric}（按 {ax_y} × {ax_x}）',
                        xlabel=ax_x, ylabel=ax_y, digits=digits)
        note = (f'共 {self.n_combinations} 个组合，成功 {len(self.succeeded)}、'
                f'失败 {len(self.failed)}；空格 = 该组合未成功或没有该指标。')
        rep.add_note(note, level='ok' if not self.failed else 'warn')
        return rep.write(path)

    def plot_curve(self, path: str = 'scan_curve.html',
                   metric: Optional[str] = None, along: Optional[str] = None,
                   title: str = '参数扫描曲线') -> str:
        """
        沿一个参数出曲线（一维扫描用这个）。

        :param path: str, 输出 .html
        :param metric: str 可选, 指标名；不给取第一个
        :param along: str 可选, 沿哪个参数；不给取第一个
        :param title: str, 标题
        :return: str, 写出的绝对路径
        """
        metric = metric or (self.metric_names[0] if self.metric_names else None)
        if metric is None:
            raise ScanError('没有任何指标可用于出图')
        along = along or self.axis_names[0]
        groups = self.series_for(metric, along)
        series = []
        for key, (xs, ys) in sorted(groups.items(), key=lambda kv: kv[0]):
            others = [n for n in self.axis_names if n != along]
            label = ', '.join(f'{n}={v}' for n, v in zip(others, key)) or metric
            series.append((label, xs, ys))
        from topo_modeler.report import HtmlReport
        from topo_modeler.report import svg_line_chart
        rep = HtmlReport(title=title, meta={'指标': metric, '横轴': along})
        rep.add_section(f'{metric} vs {along}',
                        svg_line_chart(series, xlabel=along, ylabel=metric))
        if self.failed:
            rep.add_note(f'{len(self.failed)} 个组合失败：'
                         + ', '.join(p.name for p in self.failed), level='warn')
        return rep.write(path)

    def report(self, path: str = 'scan_report.html',
               title: str = '参数扫描报告') -> str:
        """
        出完整报告：元信息 + 时间线（有审计时）+ 点表 + 热力图/曲线。

        :param path: str, 输出 .html
        :param title: str, 标题
        :return: str, 写出的绝对路径
        """
        from topo_modeler.report import HtmlReport
        rep = HtmlReport(title=title, meta={
            '模型': self.stem,
            '参数轴': '; '.join(f'{k}={self.axis_values[k]}' for k in self.axis_names),
            '组合数': self.n_combinations,
            '成功 / 失败': f'{len(self.succeeded)} / {len(self.failed)}',
            '工作目录': self.workdir,
        })
        if self.audit is not None:
            rep.add_audit(self.audit, title='扫描耗时')
        if len(self.axis_names) >= 2 and self.metric_names:
            metric = self.metric_names[0]
            matrix, xl, yl = self.metric_matrix(metric, self.axis_names[0],
                                                self.axis_names[1])
            rep.add_heatmap(matrix, xl, yl,
                            title=f'{metric}（按 {self.axis_names[1]} × {self.axis_names[0]}）',
                            xlabel=self.axis_names[0], ylabel=self.axis_names[1])
        header = (['#', '名称', '状态'] + self.axis_names + self.metric_names)
        rows = [[p.index, p.name, p.status]
                + [p.params.get(a) for a in self.axis_names]
                + [p.metrics.get(m) for m in self.metric_names]
                for p in self.points]
        rep.add_table(header, rows, caption='扫描点')
        if self.failed:
            for p in self.failed:
                rep.add_note(f'失败：{p.name} — {p.error}', level='error')
        return rep.write(path)

    def __repr__(self):
        return (f'ParameterScan({self.stem!r}, axes={self.axis_names}, '
                f'{self.n_combinations} 组合, 已执行={sum(1 for p in self.points if p.status != "pending")})')


# ============================================================
# 小工具
# ============================================================

def _copy_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """深拷贝配置（只到 dict/list 深度，够用且不引入 copy 的意外）。"""
    out: Dict[str, Any] = {}
    for key, value in cfg.items():
        if isinstance(value, dict):
            out[key] = dict(value)
        elif isinstance(value, (list, tuple)):
            out[key] = list(value)
        else:
            out[key] = value
    return out


def _is_number(value) -> bool:
    """真数值（排除 bool 与不可转换的东西）。"""
    if isinstance(value, bool):
        return False
    try:
        float(value)
    except (TypeError, ValueError):
        return False
    return True
