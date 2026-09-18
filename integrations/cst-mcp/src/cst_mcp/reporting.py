# -*- coding: utf-8 -*-
r"""
报告导出（P3）
==============

复用 `topo_modeler.report`（自包含 HTML：零 CDN、零 JS）与 CSV 直写，
**不另造一套图表**。产物一律写进服务工作目录（`tpc_service.store.ensure_within`
约束在 P2 已实现），回报给客户端的是**产物路径**而不是整份 HTML 文本 ——
大结果走产物引用、小摘要留结构化字段（`cst_mcp.md` §5）。
"""

import csv
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from cst_mcp.errors import ToolError

__all__ = ['export_report', 'analysis_csv_rows']


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _unique_stamp(out_dir: str, stamp: str, wanted: Sequence[tuple],
                  limit: int = 1000) -> str:
    """
    给同一份报告的**所有**产物找一个互不冲突的文件名后缀。

    为什么需要（2026-09-17 实测发现）：文件名原本是 ``sparams-<时间戳>.csv`` /
    ``report-<时间戳>.html``，时间戳只精确到**秒** —— 同一秒内生成两份报告时，
    第二份会**静默覆盖**第一份，而两次调用返回的产物路径还都一样（调用方以为两份都在）。
    长驻的 MCP 服务里（按频段/指标连续出报告）这属于静默数据丢失。

    规则：先试无后缀；被占用就依次试 ``-2``、``-3``…；极端情况下退化成随机 token。
    CSV 与 HTML **用同一个后缀**，保证它们仍然是配对的同一份报告。

    :param out_dir: str, 产物目录
    :param stamp: str, 时间戳（``YYYYmmdd-HHMMSS``）
    :param wanted: 序列, ``[(前缀, 扩展名), …]``
    :param limit: int, 最多试多少个后缀
    :return: str, 可安全使用的后缀（``''`` 或 ``'-2'`` …）
    """
    for index in range(limit):
        suffix = '' if index == 0 else f'-{index + 1}'
        if all(not os.path.exists(os.path.join(out_dir, f'{prefix}-{stamp}{suffix}.{ext}'))
               for prefix, ext in wanted):
            return suffix
    import uuid
    return f'-{uuid.uuid4().hex[:8]}'


def _db_to_magnitude(value: float) -> float:
    """dB → 线性幅度（供 `HtmlReport.add_s_parameters(in_db=True)` 复用绘图）。"""
    if value != value:                       # NaN
        return float('nan')
    return 10.0 ** (float(value) / 20.0)


def analysis_csv_rows(series: Dict[str, Any]) -> List[List[Any]]:
    """
    把曲线数据摊成 CSV 行（第一列频率 GHz，其余列为 dB 值）。

    :param series: dict, ``{'freqs': [...], 'columns': {名称: [dB, ...]}}``
    :return: list[list], 含表头
    """
    freqs = list(series.get('freqs') or [])
    columns = dict(series.get('columns') or {})
    names = list(columns)
    rows: List[List[Any]] = [['freq_GHz'] + names]
    for index, frequency in enumerate(freqs):
        row: List[Any] = [frequency]
        for name in names:
            values = columns[name]
            row.append(values[index] if index < len(values) else '')
        rows.append(row)
    return rows


def export_report(*, analysis: Dict[str, Any], workdir: str, out_dir: str,
                  title: str = 'TPC S 参数报告',
                  formats: Sequence[str] = ('html', 'csv'),
                  series: Optional[Dict[str, Any]] = None,
                  meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    生成报告产物（HTML / CSV）。

    :param analysis: dict, :func:`cst_mcp.analysis.analyze_series` 的结果
    :param workdir: str, 服务工作目录（产物必须落在它里面）
    :param out_dir: str, 产物目录
    :param title: str, 报告标题
    :param formats: 序列, ``'html'`` / ``'csv'``
    :param series: dict 可选, 原始曲线（``{'freqs', 'columns'}``），有则画图/写全量数据
    :param meta: dict 可选, 额外元信息（模型参数、工程路径…）
    :return: dict, ``{'artifacts': [...], 'summary': {...}}``
    :raises ToolError: ``report_failed``
    """
    from tpc_service.store import ensure_within

    wanted = [str(f).lower() for f in formats]
    for fmt in wanted:
        if fmt not in ('html', 'csv'):
            raise ToolError('invalid_arguments',
                            f"formats 只支持 'html' / 'csv'，收到 {fmt!r}",
                            formats=list(formats))
    os.makedirs(out_dir, exist_ok=True)
    ensure_within(workdir, out_dir)
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    # 同一秒内出两份报告不能互相覆盖（见 `_unique_stamp` 的说明）
    wanted_artifacts = [(prefix, ext) for prefix, ext, fmt in
                        (('sparams', 'csv', 'csv'), ('report', 'html', 'html'))
                        if fmt in wanted]
    suffix = _unique_stamp(out_dir, stamp, wanted_artifacts)
    name_stamp = f'{stamp}{suffix}'
    artifacts: List[Dict[str, Any]] = []
    summary: Dict[str, Any] = {'title': title, 'generated_at': _utcnow()}

    if 'csv' in wanted:
        csv_path = ensure_within(workdir, os.path.join(out_dir,
                                                       f'sparams-{name_stamp}.csv'))
        rows = analysis_csv_rows(series) if series else None
        try:
            with open(csv_path, 'w', newline='', encoding='utf-8-sig') as handle:
                writer = csv.writer(handle)
                if rows:
                    writer.writerows(rows)
                else:
                    # 没有原始曲线时，至少把分析结论写成表（不假装有全量数据）
                    writer.writerow(['metric', 'threshold_db', 'criterion',
                                     'n_bands', 'total_bandwidth_ghz'])
                    writer.writerow([analysis.get('metric'),
                                     analysis['criterion']['threshold_db'],
                                     analysis['criterion']['mode'],
                                     analysis.get('n_bands'),
                                     analysis.get('total_bandwidth_ghz')])
        except OSError as exc:
            raise ToolError('report_failed', f'写 CSV 失败：{exc}',
                            path=csv_path) from exc
        artifacts.append({'kind': 'csv', 'path': csv_path,
                          'note': 'S 参数全量数据（频率 GHz + dB）' if rows
                                  else '分析结论（无原始曲线）'})
        summary['csv_rows'] = len(rows or [])

    if 'html' in wanted:
        html_path = ensure_within(workdir, os.path.join(out_dir,
                                                        f'report-{name_stamp}.html'))
        try:
            html = _build_html(analysis, title=title, series=series, meta=meta)
            with open(html_path, 'w', encoding='utf-8') as handle:
                handle.write(html)
        except Exception as exc:                      # noqa: BLE001
            raise ToolError('report_failed', f'生成 HTML 失败：{exc}') from exc
        artifacts.append({'kind': 'html', 'path': html_path,
                          'note': '自包含 HTML 报告（无外部依赖）'})

    summary['artifacts'] = [a['path'] for a in artifacts]
    summary['n_bands'] = analysis.get('n_bands')
    summary['total_bandwidth_ghz'] = analysis.get('total_bandwidth_ghz')
    return {'artifacts': artifacts, 'summary': summary}


def _build_html(analysis: Dict[str, Any], *, title: str,
                series: Optional[Dict[str, Any]],
                meta: Optional[Dict[str, Any]]) -> str:
    """用 `topo_modeler.report.HtmlReport` 组装报告。"""
    from topo_modeler.report import HtmlReport

    criterion = analysis.get('criterion') or {}
    base_meta = {'生成时间': _utcnow(),
                 '曲线': analysis.get('metric', ''),
                 '判据': f"{criterion.get('mode')} {criterion.get('threshold_db')} dB",
                 '分析频段 (GHz)': analysis.get('analysis_band_ghz'),
                 '数据来源': (analysis.get('data_source') or {}).get('kind', '')}
    base_meta.update(meta or {})
    report = HtmlReport(title=title, meta=base_meta)

    if series and series.get('freqs') and series.get('columns'):
        # ⚠️ 曲线在分析后统一是 dB；这里转回幅度再交给 in_db=True 的既有绘图路径，
        #    这样 y 轴标签（|S| [dB]）由底层统一给出，不另写一套绘图。
        chart = {name: (list(series['freqs']),
                        [_db_to_magnitude(v) for v in values])
                 for name, values in series['columns'].items()}
        report.add_s_parameters(
            chart, in_db=True,
            note='曲线为 |S| 的 dB 值；零幅度记 −300 dB')
    else:
        report.add_note('本次未提供原始曲线数据，报告只含分析结论。', level='warn')

    conv = analysis.get('conventions') or {}
    report.add_table(
        ['项目', '值'],
        [['频率单位', conv.get('frequency_unit', 'GHz')],
         ['幅度口径', conv.get('s_db', '20*log10(abs(S))')],
         ['零值处理', f"{conv.get('zero_magnitude_db')} dB"],
         ['判据', f"{criterion.get('mode')} 阈值 {criterion.get('threshold_db')} dB"],
         ['合格区间段数', analysis.get('n_bands')],
         ['各段带宽之和 (GHz)', analysis.get('total_bandwidth_ghz')],
         ['数据点', analysis.get('n_points')]],
        caption='分析口径')

    bands = analysis.get('bands') or []
    if bands:
        report.add_table(
            ['#', 'fmin (GHz)', 'fmax (GHz)', '带宽 (GHz)', '点数',
             '最佳 (dB)', '@ (GHz)', '最差 (dB)', '余量 (dB)'],
            [[b['index'], b['fmin_ghz'], b['fmax_ghz'], b['bandwidth_ghz'],
              b['n_points'], b['best_db'], b['best_freq_ghz'], b['worst_db'],
              b['margin_db']] for b in bands],
            caption='连续合格区间（**分段列出，未合并**）')
        report.add_note(analysis.get('total_bandwidth_definition', ''),
                        level='info')

    resonances = analysis.get('resonances')
    if resonances:
        report.add_table(
            ['#', '频率 (GHz)', '值 (dB)', '类型', '幅度 (dB)'],
            [[i, r['freq_ghz'], r['db'], r['kind'], r['prominence_db']]
             for i, r in enumerate(resonances)],
            caption='谐振/极值位置')
        report.add_note(analysis.get('resonance_definition', ''), level='warn')
    return report.to_html()
