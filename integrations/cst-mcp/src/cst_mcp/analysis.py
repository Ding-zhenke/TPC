# -*- coding: utf-8 -*-
r"""
S 参数分析（P3）
================

口径先行（照抄实现，别另立）
----------------------------
* **频率单位 GHz**、**幅度 dB = 20·log10(|S|)**、**幅度为 0 记 −300 dB** ——
  与 `cst_solver._result_core._to_db`、`topo_modeler/result_reader.py`、
  `topo_modeler/report.py::_to_db` 完全一致（由
  `cst_solver.run_contract.result_conventions()` 提供，测试里会比对实现）。
* 复数结果的实部/虚部由读取层归一化，本模块只处理**实数 dB 序列**。

连续带宽：**只按相邻采样点合并**
--------------------------------
判定阈值后，只有**采样索引相邻**且都合格的点才并成一段：

* 中间只要有一个不合格点，就断成两段（`n_bands` 增加）；
* **绝不**把两段不相连的合格区间并成一个「总带宽」；
* `total_bandwidth_ghz` 明确是**各段带宽之和**（字段名里写清了，避免误读）；
* 需要按「频率间隔」而不是「采样索引」断开时，传 ``max_gap_ghz``：
  相邻两点频差超过它就开始新的一段（用于拼接过多段扫频的曲线）。

谐振定义：**相邻三点比较的局部极值**（明确、可复现）
----------------------------------------------------
* 谷：``v[i] < v[i-1] 且 v[i] < v[i+1]``；峰对称；
* 幅度：``prominence_db = min(两侧) - v[i]``（谷；峰取对称量），
  低于 ``min_prominence_db`` 的极值被过滤掉；
* ⚠️ **这是采样点级定义，不做抛物线插值** —— 报告里给出的频率精度受限于
  扫频步长。要精确比较两个模型的谐振位置（计划 P4/V3），必须用**同一套频点**
  的曲线逐段比较，不能只看某个单点 dB 值。

@author: PC
"""

import csv
import math
import os
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from cst_mcp.errors import ToolError
from tpc_toolkit.curves import (        # 规则实现只有一份，见模块 docstring
    contiguous_bands as library_contiguous_bands,
    find_resonances as library_find_resonances,
)

__all__ = [
    'to_db',
    'read_series_csv',
    'contiguous_bands',
    'find_resonances',
    'analyze_series',
    'conventions',
]


def conventions() -> Dict[str, Any]:
    """分析口径（来自底层唯一实现，避免文档与代码漂移）。"""
    from cst_solver.run_contract import result_conventions
    base = result_conventions()
    return {'frequency_unit': base['frequency_unit'],
            's_db': base['s_db'],
            'zero_magnitude_db': base['zero_magnitude_db'],
            'run_id_default': base['run_id_default'],
            'run_id_semantics': base['run_id_semantics'],
            'source': 'cst_solver.run_contract.result_conventions()'}


def to_db(values: Iterable[Any]) -> List[float]:
    """
    线性/复数幅度 → dB（``20·log10|v|``，幅度 0 记 −300 dB）。

    :param values: 可迭代, 复数或实数
    :return: list[float]
    """
    out: List[float] = []
    for value in values:
        if value is None or value == '':
            out.append(float('nan'))
            continue
        try:
            magnitude = abs(complex(value))
        except (TypeError, ValueError):
            magnitude = abs(float(value))
        out.append(20.0 * math.log10(magnitude) if magnitude > 0 else -300.0)
    return out


def read_series_csv(path: str) -> Dict[str, Any]:
    """
    读一份 S 参数 CSV（第一列频率 GHz，其余列为各 S 参数）。

    兼容两种表头：``freq_GHz`` / ``freq_ghz`` / ``frequency_GHz``（大小写与
    下划线不敏感）；没有表头时按 ``(freq, S1,1, S2,1, …)`` 处理。

    :param path: str, CSV 路径
    :return: dict, ``{'freqs': [...], 'columns': {名称: [dB, ...]},
        'path': 绝对路径, 'column_names': [...]}``；``columns`` **统一是 dB**
    :raises ToolError: ``not_found`` / ``analysis_failed``
    """
    if not path or not os.path.isfile(path):
        raise ToolError('not_found', f'CSV 不存在：{path}', path=path)
    freqs: List[float] = []
    raw_columns: Dict[str, List[Any]] = {}
    try:
        with open(path, newline='', encoding='utf-8-sig') as handle:
            reader = csv.reader(handle)
            rows = [row for row in reader if row and any(c.strip() for c in row)]
    except OSError as exc:
        raise ToolError('analysis_failed', f'读 CSV 失败：{exc}', path=path) from exc
    if not rows:
        raise ToolError('analysis_failed', 'CSV 里没有数据行', path=path)

    header = [c.strip() for c in rows[0]]
    first = header[0].lower().replace('_', '').replace(' ', '')
    has_header = not _is_number(rows[0][0]) or first.startswith('freq')
    if has_header:
        names = _merge_split_s_parameter_names(
            header[1:] or [f'col{i}' for i in range(1, len(rows[0]))])
        data_rows = rows[1:]
    else:
        names = [f'col{i}' for i in range(1, len(rows[0]))]
        data_rows = rows

    for name in names:
        raw_columns[name] = []
    for row in data_rows:
        if not row or not _is_number(row[0]):
            continue
        freqs.append(float(row[0]))
        for index, name in enumerate(names, start=1):
            cell = row[index] if index < len(row) else ''
            raw_columns[name].append(cell)

    # 判断列里是线性幅度还是已经是 dB：出现负值、或列名含 db ⇒ 按 dB 处理
    columns_db: Dict[str, List[float]] = {}
    units: Dict[str, str] = {}
    for name, values in raw_columns.items():
        numbers = [float(v) for v in values if _is_number(v)]
        looks_db = ('db' in name.lower()) or any(v < 0 for v in numbers)
        converted: List[float] = []
        for cell in values:
            if not _is_number(cell):
                converted.append(float('nan'))
                continue
            number = float(cell)
            if looks_db:
                converted.append(number)
            else:
                converted.append(20.0 * math.log10(abs(number))
                                 if abs(number) > 0 else -300.0)
        columns_db[name] = converted
        units[name] = 'dB' if looks_db else 'linear→dB'
    return {'freqs': freqs, 'columns': columns_db, 'column_units': units,
            'path': os.path.abspath(path), 'column_names': list(names)}


def _is_number(value: Any) -> bool:
    try:
        float(value)
    except (TypeError, ValueError):
        return False
    return True


#: 可能被逗号切开的表头片段：``S3`` + ``1``
_HEAD_INDEX_RE = re.compile(r'^[sS]\d+$')
_HEAD_DIGITS_RE = re.compile(r'^\d+$')


def _merge_split_s_parameter_names(names: List[str]) -> List[str]:
    """
    把被逗号切开的 S 参数名拼回去（``['S1', '1', 'S2', '1']`` → ``['S1,1', 'S2,1']``）。

    为什么需要：S 参数名**本身含逗号**（``S1,1``）。标准 CSV 会给这种字段加引号
    （``csv.writer`` 的默认行为，本仓库导出的文件就是这样），``csv.reader`` 读回来
    是一个整体；但手写的 CSV 常常不加引号，于是被切成两列。
    这里只对**明确的模式**动手（``S<数字>`` 后紧跟纯数字），不误伤正常表头。

    :param names: list[str], 表头去掉第一列后的单元格
    :return: list[str], 拼好的列名
    """
    merged: List[str] = []
    index = 0
    while index < len(names):
        current = str(names[index]).strip()
        following = str(names[index + 1]).strip() if index + 1 < len(names) else ''
        if _HEAD_INDEX_RE.match(current) and _HEAD_DIGITS_RE.match(following):
            merged.append(f'{current},{following}')
            index += 2
            continue
        merged.append(current)
        index += 1
    return merged



def contiguous_bands(freqs: Sequence[float], values: Sequence[float], *,
                     threshold_db: float, criterion: str = 'below',
                     max_gap_ghz: Optional[float] = None) -> List[Dict[str, Any]]:
    """
    找**连续合格区间**（只按相邻采样点合并，绝不跨越不合格点）。

    ⚠️ **实现只有一份**（2026-09-17 起）：规则在
    `tpc_toolkit.curves.contiguous_bands`，本函数只负责把 `ValueError`
    翻成 MCP 的 ``invalid_arguments``（错误**码**是协议层的事，规则不是）。

    :param freqs: 频率序列（GHz）
    :param values: 对应的 dB 序列
    :param threshold_db: 阈值（dB）
    :param criterion: ``'below'``（≤ 阈值合格，如回波损耗）或 ``'above'``
        （≥ 阈值合格，如插损）
    :param max_gap_ghz: float 可选, 相邻两点频差超过它就断开（默认只用采样相邻性）
    :return: list[dict], 每段含 ``fmin_ghz/fmax_ghz/bandwidth_ghz/n_points/
        best_db/best_freq_ghz/worst_db/worst_freq_ghz/margin_db``
    :raises ToolError: ``invalid_arguments``
    """
    try:
        return library_contiguous_bands(freqs, values, threshold_db=threshold_db,
                                        criterion=criterion,
                                        max_gap_ghz=max_gap_ghz)
    except ValueError as exc:
        raise ToolError('invalid_arguments', str(exc)) from exc


def find_resonances(freqs: Sequence[float], values: Sequence[float], *,
                    kind: str = 'min', min_prominence_db: float = 0.0,
                    band: Optional[Tuple[float, float]] = None) -> List[Dict[str, Any]]:
    """
    找局部极值（谷/峰），**相邻三点比较**。

    ⚠️ **规则只有一份**（2026-09-17 起）：实现在 `tpc_toolkit.curves.find_resonances`，
    MCP 层不再自己写一套（库层 `topo_modeler.ResultReader.resonances()` 用的是同一个函数）。

    :param freqs: 频率序列（GHz）
    :param values: dB 序列
    :param kind: ``'min'``（谷，如 S11 谐振）或 ``'max'``
    :param min_prominence_db: float, 幅度低于此值的不算（过滤数值毛刺）
    :param band: tuple 可选, ``(fmin, fmax)`` 只在带内找
    :return: list[dict], ``{'freq_ghz','db','kind','prominence_db'}``
    :raises ToolError: ``invalid_arguments``
    """
    try:
        return library_find_resonances(freqs, values, kind=kind,
                                       min_prominence_db=min_prominence_db,
                                       band=band)
    except ValueError as exc:
        raise ToolError('invalid_arguments', str(exc), kind=kind) from exc


def analyze_series(freqs: Sequence[float], values: Sequence[float], *,
                   metric: str, threshold_db: float, criterion: str = 'below',
                   band: Optional[Tuple[float, float]] = None,
                   max_gap_ghz: Optional[float] = None,
                   resonance_kind: Optional[str] = None,
                   min_prominence_db: float = 0.0,
                   data_source: Optional[Dict[str, Any]] = None,
                   series_reference: Optional[Dict[str, Any]] = None
                   ) -> Dict[str, Any]:
    """
    分析一条 S 参数曲线：连续合格区间 + （可选）谐振位置。

    :param freqs: 频率（GHz）
    :param values: dB 值
    :param metric: str, 曲线名（如 ``'S2,1'``），会带回结果里
    :param threshold_db: float, 阈值（dB）
    :param criterion: ``'below'`` / ``'above'``
    :param band: tuple 可选, 分析频段 ``(fmin, fmax)``
    :param max_gap_ghz: float 可选, 见 :func:`contiguous_bands`
    :param resonance_kind: ``'min'`` / ``'max'`` / None（不找）
    :param min_prominence_db: float, 谐振最小幅度
    :param data_source: dict 可选, 数据来自哪里（必填项，调用方给）
    :param series_reference: dict 可选, 完整曲线的产物引用
    :return: dict, 结构化分析结果（含单位、频段、阈值、判据与数据来源）
    :raises ToolError: ``analysis_failed``（频段内没有数据）
    """
    pairs = [(float(f), float(v)) for f, v in zip(freqs, values) if v == v]
    if band is not None:
        pairs = [p for p in pairs if band[0] <= p[0] <= band[1]]
    if not pairs:
        raise ToolError('analysis_failed',
                        f'{metric} 在频段 {band} 内没有可用数据点',
                        metric=metric, band=list(band) if band else None)
    pairs.sort(key=lambda item: item[0])
    freqs_sorted = [p[0] for p in pairs]
    values_sorted = [p[1] for p in pairs]

    bands = contiguous_bands(freqs_sorted, values_sorted,
                             threshold_db=threshold_db, criterion=criterion,
                             max_gap_ghz=max_gap_ghz)
    total = sum(b['bandwidth_ghz'] for b in bands)
    payload: Dict[str, Any] = {
        'metric': metric,
        'conventions': conventions(),
        'criterion': {'threshold_db': threshold_db, 'mode': criterion,
                      'rule': ("value <= threshold 为合格" if criterion == 'below'
                               else "value >= threshold 为合格")},
        'analysis_band_ghz': [freqs_sorted[0], freqs_sorted[-1]],
        'requested_band_ghz': list(band) if band else None,
        'n_points': len(freqs_sorted),
        'value_range_db': [min(values_sorted), max(values_sorted)],
        'n_bands': len(bands),
        'bands': bands,
        'total_bandwidth_ghz': total,
        'total_bandwidth_definition': (
            '各段带宽之和（**不是**一段连续带宽）；相邻不合格点会把区间断开，'
            '本模块从不合并不相连的合格区间'),
        'data_source': dict(data_source or {'note': '未提供数据来源'}),
    }
    if resonance_kind:
        resonances = find_resonances(freqs_sorted, values_sorted,
                                     kind=resonance_kind,
                                     min_prominence_db=min_prominence_db,
                                     band=band)
        payload['resonances'] = resonances
        payload['resonance_definition'] = (
            '相邻三点比较的局部极值（采样点级，不做抛物线插值）；'
            'prominence_db 为相对两侧较不利一方的幅度')
        payload['n_resonances'] = len(resonances)
    if series_reference:
        payload['series_reference'] = dict(series_reference)
    return payload
