# -*- coding: utf-8 -*-
r"""
报告引擎（阶段 7 §3.2）—— 自包含 HTML，零 CDN / 零 JS 依赖
=========================================================

为什么是「自包含 HTML」而不是截图
--------------------------------
项目的验收判据是「S 参数谐振峰 < 1 GHz」「远场主瓣 < 5°」这类**要对着图看**的结论。
截图的三个毛病：看不出数值、改不了字号、**过几天就找不到是哪次跑的**。
自包含 HTML 把数据与图放在同一个文件里，随手发给别人也能打开。

「自包含」的含义（**硬约定**）
-----------------------------
生成的 HTML **不引用任何外部资源**：没有 CDN、没有 `<script>`、没有外链 CSS/字体。
所有图形都是**内联 SVG**（浏览器原生渲染，不需要 JS）。这样：

- 断网也能打开；
- 十年后还能打开（不依赖任何服务活着）；
- 可直接进 git / 邮件 / 报告附件，不会变成一个「打不开的壳」。

**明确没做的**：计划里提到「3D 远场（WebGL）」。手写 WebGL 需要内联 JS，
既违背上面的零 JS 约定、又无法离线验收，所以**不做** —— 远场用**二维极坐标/直角坐标**
呈现（`add_polar` / 后续的 `plot_farfield_cartesian`），已足够看主瓣与旁瓣。

用法::

    from topo_modeler.report import HtmlReport, report_from_s_parameters_csv

    rep = HtmlReport(title='直波导 AB · 验收报告', meta={'模型': 'wg_AB'})
    rep.add_s_parameters_csv('s_params.csv', note='时域求解，关自适应 + 稳态 -20 dB')
    rep.add_heatmap(matrix, x_labels, y_labels, title='扫描热力图')
    rep.add_note('S11 在反射低谷附近对微小差异极其敏感', level='warn')
    rep.write('report.html')

@author: PC
"""

import csv
import html
import math
import os
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

__all__ = [
    'HtmlReport',
    'report_from_s_parameters',
    'report_from_s_parameters_csv',
    'svg_line_chart',
    'svg_heatmap',
    'svg_polar',
    'svg_timeline',
]

#: 系列配色（避免依赖任何外部调色板）
PALETTE = ('#2563eb', '#dc2626', '#059669', '#d97706', '#7c3aed',
           '#0891b2', '#be185d', '#4d7c0f', '#a16207', '#475569')

_FONT = ('-apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", '
         'Roboto, "Helvetica Neue", Arial, sans-serif')


# ============================================================
# 小工具
# ============================================================

def _esc(text) -> str:
    """HTML 转义（含引号）。"""
    return html.escape(str(text), quote=True)


def _fmt(value, digits: int = 3) -> str:
    """数值格式化：整数不拖小数点，浮点保留有效位。"""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            return '—'
        if value == 0:
            return '0'
        mag = abs(value)
        if mag >= 1e5 or mag < 1e-3:
            return f'{value:.2e}'
        return f'{value:.{digits}f}'.rstrip('0').rstrip('.')
    return str(value)


def _finite(values: Iterable[float]) -> List[float]:
    return [float(v) for v in values if v is not None and math.isfinite(float(v))]


def _nice_ticks(lo: float, hi: float, count: int = 5) -> List[float]:
    """给一组「好看」的刻度（1/2/5 × 10^k）。"""
    if not math.isfinite(lo) or not math.isfinite(hi) or hi <= lo:
        return [lo]
    raw = (hi - lo) / max(count, 1)
    exp = math.floor(math.log10(raw))
    best = None
    for mult in (1, 2, 2.5, 5, 10):
        step = mult * (10 ** exp)
        n = int(math.ceil((hi - lo) / step))
        if best is None or abs(n - count) < abs(best[1] - count):
            best = (step, n)
    step = best[0]
    first = math.ceil(lo / step) * step
    out, v = [], first
    while v <= hi + step * 1e-9:
        out.append(0.0 if abs(v) < step * 1e-9 else v)
        v += step
    return out


class _Box:
    """SVG 里的绘图区：把数据坐标映射到像素坐标。"""

    def __init__(self, width, height, xlim, ylim, pad_l=64, pad_r=18,
                 pad_t=16, pad_b=44):
        self.w, self.h = width, height
        self.x0, self.x1 = xlim
        self.y0, self.y1 = ylim
        self.pl, self.pr, self.pt, self.pb = pad_l, pad_r, pad_t, pad_b

    @property
    def px0(self):
        return self.pl

    @property
    def px1(self):
        return self.w - self.pr

    @property
    def py0(self):
        """y 轴底（数据 y 的最小值）。"""
        return self.h - self.pb

    @property
    def py1(self):
        return self.pt

    def x(self, v: float) -> float:
        span = (self.x1 - self.x0) or 1.0
        return self.px0 + (float(v) - self.x0) / span * (self.px1 - self.px0)

    def y(self, v: float) -> float:
        span = (self.y1 - self.y0) or 1.0
        return self.py0 - (float(v) - self.y0) / span * (self.py0 - self.py1)


# ============================================================
# 内联 SVG 图元
# ============================================================

def svg_line_chart(series: Sequence[Tuple[str, Sequence[float], Sequence[float]]],
                   title: str = '', xlabel: str = '', ylabel: str = '',
                   width: int = 900, height: int = 420,
                   xlim: Optional[Tuple[float, float]] = None,
                   ylim: Optional[Tuple[float, float]] = None,
                   highlight: Optional[Sequence[Tuple[float, str]]] = None) -> str:
    """
    折线图（多迹叠加），返回**内联 SVG 字符串**。

    :param series: 序列，每个元素 ``(名字, xs, ys)``
    :param title: str, 图标题
    :param xlabel: str, x 轴标题
    :param ylabel: str, y 轴标题
    :param width: int, 像素宽
    :param height: int, 像素高
    :param xlim: tuple 可选, (min, max)，不给则按数据取
    :param ylim: tuple 可选, 同上
    :param highlight: 可选, ``[(x 值, 标注文字), …]`` —— 画竖直参考线（如谐振频点）
    :return: str, ``<svg>…</svg>``
    """
    clean = [(str(name), [float(v) for v in xs], [float(v) for v in ys])
             for name, xs, ys in series if len(xs)]
    if not clean:
        return '<p class="empty">（没有数据）</p>'

    all_x = _finite(v for _n, xs, _y in clean for v in xs)
    all_y = _finite(v for _n, _x, ys in clean for v in ys)
    if xlim is None:
        xlim = (min(all_x), max(all_x))
    if ylim is None:
        lo, hi = min(all_y), max(all_y)
        pad = (hi - lo) * 0.08 or 1.0
        ylim = (lo - pad, hi + pad)
    box = _Box(width, height, xlim, ylim)

    parts = [f'<svg viewBox="0 0 {width} {height}" width="100%" '
             f'preserveAspectRatio="xMidYMid meet" role="img" '
             f'aria-label="{_esc(title or "折线图")}">']
    parts.append(f'<rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff"/>')
    if title:
        parts.append(f'<text x="{width / 2:.1f}" y="14" text-anchor="middle" '
                     f'font-size="14" font-weight="600" fill="#111827">{_esc(title)}</text>')

    # 网格 + 刻度
    for tick in _nice_ticks(xlim[0], xlim[1]):
        gx = box.x(tick)
        parts.append(f'<line x1="{gx:.1f}" y1="{box.py1}" x2="{gx:.1f}" '
                     f'y2="{box.py0}" stroke="#e5e7eb" stroke-width="1"/>')
        parts.append(f'<text x="{gx:.1f}" y="{box.py0 + 16}" text-anchor="middle" '
                     f'font-size="11" fill="#4b5563">{_fmt(tick)}</text>')
    for tick in _nice_ticks(ylim[0], ylim[1]):
        gy = box.y(tick)
        parts.append(f'<line x1="{box.px0}" y1="{gy:.1f}" x2="{box.px1}" '
                     f'y2="{gy:.1f}" stroke="#e5e7eb" stroke-width="1"/>')
        parts.append(f'<text x="{box.px0 - 8}" y="{gy + 4:.1f}" text-anchor="end" '
                     f'font-size="11" fill="#4b5563">{_fmt(tick)}</text>')
    parts.append(f'<rect x="{box.px0}" y="{box.py1}" width="{box.px1 - box.px0}" '
                 f'height="{box.py0 - box.py1}" fill="none" stroke="#9ca3af"/>')

    # 参考竖线
    for hx, label in (highlight or ()):
        if math.isfinite(float(hx)):
            gx = box.x(float(hx))
            parts.append(f'<line x1="{gx:.1f}" y1="{box.py1}" x2="{gx:.1f}" '
                         f'y2="{box.py0}" stroke="#f59e0b" stroke-width="1" '
                         f'stroke-dasharray="4 3"/>')
            if label:
                parts.append(f'<text x="{gx + 4:.1f}" y="{box.py1 + 12}" '
                             f'font-size="10" fill="#b45309">{_esc(label)}</text>')

    # 曲线
    for idx, (name, xs, ys) in enumerate(clean):
        pts = ' '.join(f'{box.x(x):.1f},{box.y(y):.1f}' for x, y in zip(xs, ys))
        parts.append(f'<polyline points="{pts}" fill="none" '
                     f'stroke="{PALETTE[idx % len(PALETTE)]}" stroke-width="1.8" '
                     f'stroke-linejoin="round"/>')

    # 图例
    lx, ly = box.px0 + 8, box.py1 + 16
    for idx, (name, _x, _y) in enumerate(clean[:10]):
        px = lx + idx * 150
        parts.append(f'<line x1="{px}" y1="{ly - 4}" x2="{px + 22}" y2="{ly - 4}" '
                     f'stroke="{PALETTE[idx % len(PALETTE)]}" stroke-width="2.4"/>')
        parts.append(f'<text x="{px + 27}" y="{ly}" font-size="11" '
                     f'fill="#374151">{_esc(name)}</text>')

    if xlabel:
        parts.append(f'<text x="{(box.px0 + box.px1) / 2:.1f}" y="{height - 6}" '
                     f'text-anchor="middle" font-size="12" fill="#374151">'
                     f'{_esc(xlabel)}</text>')
    if ylabel:
        cx, cy = 16, (box.py0 + box.py1) / 2
        parts.append(f'<text x="{cx}" y="{cy:.1f}" text-anchor="middle" '
                     f'font-size="12" fill="#374151" '
                     f'transform="rotate(-90 {cx} {cy:.1f})">{_esc(ylabel)}</text>')
    parts.append('</svg>')
    return '\n'.join(parts)


def _heat_color(t: float) -> str:
    """把 ``t ∈ [0,1]`` 映射成蓝→青→黄→红（无外部调色板）。"""
    t = max(0.0, min(1.0, t))
    stops = ((0.0, (37, 99, 235)), (0.35, (8, 145, 178)),
             (0.65, (217, 119, 6)), (1.0, (220, 38, 38)))
    for (a, ca), (b, cb) in zip(stops, stops[1:]):
        if a <= t <= b:
            k = 0.0 if b == a else (t - a) / (b - a)
            rgb = tuple(round(ca[i] + (cb[i] - ca[i]) * k) for i in range(3))
            return '#%02x%02x%02x' % rgb
    return '#dc2626'


def svg_heatmap(matrix: Sequence[Sequence[float]], x_labels: Sequence[Any],
                y_labels: Sequence[Any], title: str = '',
                xlabel: str = '', ylabel: str = '',
                cell: int = 42, digits: int = 1) -> str:
    """
    热力图（每个格子一个数值），返回内联 SVG。

    :param matrix: 二维序列，``matrix[i][j]`` 对应 ``y_labels[i]``、``x_labels[j]``
    :param x_labels: 横轴标签
    :param y_labels: 纵轴标签
    :param title: str, 标题
    :param cell: int, 单元格边长（像素）
    :param digits: int, 格子里数值的小数位
    :return: str, ``<svg>…</svg>``
    """
    rows = [list(map(float, r)) for r in matrix if r is not None]
    if not rows or not rows[0]:
        return '<p class="empty">（没有数据）</p>'
    ny, nx = len(rows), len(rows[0])
    vals = _finite(v for r in rows for v in r)
    lo, hi = (min(vals), max(vals)) if vals else (0.0, 1.0)
    span = (hi - lo) or 1.0

    pad_l, pad_t, pad_r, pad_b = 76, (34 if title else 14), 110, 54
    w = pad_l + nx * cell + pad_r
    h = pad_t + ny * cell + pad_b
    parts = [f'<svg viewBox="0 0 {w} {h}" width="100%" preserveAspectRatio="xMidYMid meet" '
             f'role="img" aria-label="{_esc(title or "热力图")}">',
             f'<rect x="0" y="0" width="{w}" height="{h}" fill="#ffffff"/>']
    if title:
        parts.append(f'<text x="{w / 2:.1f}" y="18" text-anchor="middle" font-size="14" '
                     f'font-weight="600" fill="#111827">{_esc(title)}</text>')

    for i in range(ny):
        for j in range(nx):
            x = pad_l + j * cell
            y = pad_t + i * cell
            color = _heat_color((rows[i][j] - lo) / span)
            parts.append(f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" '
                         f'fill="{color}" stroke="#ffffff" stroke-width="1"/>')
            parts.append(f'<text x="{x + cell / 2:.1f}" y="{y + cell / 2 + 4:.1f}" '
                         f'text-anchor="middle" font-size="10" fill="#ffffff">'
                         f'{rows[i][j]:.{digits}f}</text>')

    for j, lab in enumerate(x_labels[:nx]):
        x = pad_l + j * cell + cell / 2
        parts.append(f'<text x="{x:.1f}" y="{pad_t + ny * cell + 16}" '
                     f'text-anchor="middle" font-size="11" fill="#374151">{_esc(lab)}</text>')
    for i, lab in enumerate(y_labels[:ny]):
        y = pad_t + i * cell + cell / 2 + 4
        parts.append(f'<text x="{pad_l - 8}" y="{y:.1f}" text-anchor="end" '
                     f'font-size="11" fill="#374151">{_esc(lab)}</text>')

    # 色标
    cb_x = pad_l + nx * cell + 26
    cb_h = ny * cell
    steps = 40
    for s in range(steps):
        t = s / (steps - 1)
        parts.append(f'<rect x="{cb_x}" y="{pad_t + cb_h * (1 - t) - cb_h / steps:.2f}" '
                     f'width="14" height="{cb_h / steps + 0.5:.2f}" fill="{_heat_color(t)}"/>')
    parts.append(f'<text x="{cb_x + 20}" y="{pad_t + 10}" font-size="10" fill="#374151">'
                 f'{_fmt(hi, digits)}</text>')
    parts.append(f'<text x="{cb_x + 20}" y="{pad_t + cb_h}" font-size="10" fill="#374151">'
                 f'{_fmt(lo, digits)}</text>')

    if xlabel:
        parts.append(f'<text x="{pad_l + nx * cell / 2:.1f}" y="{h - 8}" '
                     f'text-anchor="middle" font-size="12" fill="#374151">'
                     f'{_esc(xlabel)}</text>')
    if ylabel:
        cx, cy = 14, pad_t + ny * cell / 2
        parts.append(f'<text x="{cx}" y="{cy:.1f}" text-anchor="middle" font-size="12" '
                     f'fill="#374151" transform="rotate(-90 {cx} {cy:.1f})">'
                     f'{_esc(ylabel)}</text>')
    parts.append('</svg>')
    return '\n'.join(parts)


def svg_polar(theta_deg: Sequence[float], values: Sequence[float],
              title: str = '', rlabel: str = 'dB', size: int = 420,
              zero_at: str = 'top', series: Optional[Sequence[Tuple[str, Sequence[float], Sequence[float]]]] = None,
              peak_marker: bool = True) -> str:
    """
    极坐标方向图（远场主瓣/旁瓣用），返回内联 SVG。

    :param theta_deg: 角度序列（度）
    :param values: 对应的数值（通常 dB）
    :param title: str, 标题
    :param rlabel: str, 半径方向的量纲
    :param size: int, 画布边长
    :param zero_at: str, ``'top'`` 表示 0° 朝上（远场方向图惯例）
    :param series: 可选, ``[(名字, theta, values), …]``；给了就忽略前两个参数
    :param peak_marker: bool, 是否标出主瓣峰值方向
    :return: str, ``<svg>…</svg>``
    """
    data = list(series) if series else [('', theta_deg, values)]
    data = [(str(n), [float(t) for t in th], [float(v) for v in vs])
            for n, th, vs in data if len(th)]
    if not data:
        return '<p class="empty">（没有数据）</p>'

    allv = _finite(v for _n, _t, vs in data for v in vs)
    vmin, vmax = min(allv), max(allv)
    if vmax - vmin < 1e-9:
        vmax = vmin + 1.0
    cx = cy = size / 2
    radius = size / 2 - 42

    def to_xy(theta, value):
        frac = (value - vmin) / (vmax - vmin)
        r = max(0.0, min(1.0, frac)) * radius
        rad = math.radians(theta)
        if zero_at == 'top':
            return cx + r * math.sin(rad), cy - r * math.cos(rad)
        return cx + r * math.cos(rad), cy + r * math.sin(rad)

    parts = [f'<svg viewBox="0 0 {size} {size}" width="100%" '
             f'preserveAspectRatio="xMidYMid meet" role="img" '
             f'aria-label="{_esc(title or "极坐标方向图")}">',
             f'<rect x="0" y="0" width="{size}" height="{size}" fill="#ffffff"/>']
    if title:
        parts.append(f'<text x="{cx}" y="16" text-anchor="middle" font-size="13" '
                     f'font-weight="600" fill="#111827">{_esc(title)}</text>')

    for frac in (0.25, 0.5, 0.75, 1.0):
        rr = radius * frac
        parts.append(f'<circle cx="{cx}" cy="{cy}" r="{rr:.1f}" fill="none" '
                     f'stroke="#e5e7eb" stroke-width="1"/>')
        val = vmin + (vmax - vmin) * frac
        parts.append(f'<text x="{cx + 3}" y="{cy - rr + 11:.1f}" font-size="9" '
                     f'fill="#9ca3af">{_fmt(val)}</text>')
    for ang in range(0, 360, 30):
        rad = math.radians(ang)
        if zero_at == 'top':
            ex, ey = cx + radius * math.sin(rad), cy - radius * math.cos(rad)
            tx, ty = cx + (radius + 16) * math.sin(rad), cy - (radius + 16) * math.cos(rad)
        else:
            ex, ey = cx + radius * math.cos(rad), cy + radius * math.sin(rad)
            tx, ty = cx + (radius + 16) * math.cos(rad), cy + (radius + 16) * math.sin(rad)
        parts.append(f'<line x1="{cx}" y1="{cy}" x2="{ex:.1f}" y2="{ey:.1f}" '
                     f'stroke="#f3f4f6" stroke-width="1"/>')
        parts.append(f'<text x="{tx:.1f}" y="{ty + 3:.1f}" text-anchor="middle" '
                     f'font-size="9" fill="#6b7280">{ang}°</text>')

    for idx, (_name, th, vs) in enumerate(data):
        pts = ' '.join(f'{x:.1f},{y:.1f}' for x, y in (to_xy(t, v) for t, v in zip(th, vs)))
        parts.append(f'<polyline points="{pts}" fill="none" '
                     f'stroke="{PALETTE[idx % len(PALETTE)]}" stroke-width="2"/>')

    if peak_marker and data:
        name, th, vs = data[0]
        best = max(range(len(vs)), key=lambda i: vs[i])
        px, py = to_xy(th[best], vs[best])
        parts.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="4" fill="#dc2626"/>')
        parts.append(f'<text x="{px + 7:.1f}" y="{py - 5:.1f}" font-size="10" '
                     f'fill="#b91c1c">峰值 {_fmt(th[best], 1)}° / {_fmt(vs[best])} {_esc(rlabel)}</text>')

    parts.append(f'<text x="{cx}" y="{size - 10}" text-anchor="middle" font-size="11" '
                 f'fill="#6b7280">径向：{_esc(rlabel)}（{_fmt(vmin)} → {_fmt(vmax)}）</text>')
    parts.append('</svg>')
    return '\n'.join(parts)


def svg_timeline(records: Sequence[Dict[str, Any]], title: str = '步骤时间线',
                 width: int = 900, bar_h: int = 16) -> str:
    """
    步骤时间线（按耗时画横条），从审计记录生成。

    :param records: ``[{'tool':…, 'duration_s':…, 'status':…}, …]``
    :param title: str, 标题
    :param width: int, 像素宽
    :param bar_h: int, 每根条的高度
    :return: str, ``<svg>…</svg>``
    """
    rows = [r for r in records if r.get('duration_s') is not None]
    if not rows:
        return '<p class="empty">（没有带耗时的记录）</p>'
    rows = sorted(rows, key=lambda r: r['duration_s'], reverse=True)[:25]
    # 所有步骤都短于计时精度（常见于纯内存操作）时，不要误报「没有数据」——
    # 照画，条宽统一用最小值，并在图下注明。
    total = max(r['duration_s'] for r in rows)
    degenerate = total <= 0
    scale = total if total > 0 else 1.0
    label_w = 220
    h = 30 + len(rows) * bar_h + (40 if degenerate else 24)
    parts = [f'<svg viewBox="0 0 {width} {h}" width="100%" '
             f'preserveAspectRatio="xMidYMid meet" role="img" '
             f'aria-label="{_esc(title)}">',
             f'<rect x="0" y="0" width="{width}" height="{h}" fill="#ffffff"/>',
             f'<text x="{width / 2:.1f}" y="16" text-anchor="middle" font-size="13" '
             f'font-weight="600" fill="#111827">{_esc(title)}</text>']
    for i, rec in enumerate(rows):
        y = 26 + i * bar_h
        bw = (width - label_w - 90) * (rec['duration_s'] / scale)
        ok = rec.get('status') != 'error'
        color = '#2563eb' if ok else '#dc2626'
        parts.append(f'<text x="{label_w - 8}" y="{y + 11}" text-anchor="end" '
                     f'font-size="11" fill="#374151">{_esc(str(rec.get("tool"))[:28])}</text>')
        parts.append(f'<rect x="{label_w}" y="{y + 2}" width="{max(bw, 1):.1f}" '
                     f'height="{bar_h - 6}" fill="{color}" rx="2"/>')
        parts.append(f'<text x="{label_w + max(bw, 1) + 6:.1f}" y="{y + 11}" '
                     f'font-size="10" fill="#6b7280">{rec["duration_s"]:.3f}s</text>')
    if degenerate:
        parts.append(f'<text x="{width / 2:.1f}" y="{h - 10}" text-anchor="middle" '
                     f'font-size="10" fill="#9ca3af">'
                     f'所有步骤耗时都低于 1 ms（条宽用最小值表示）</text>')
    parts.append('</svg>')
    return '\n'.join(parts)


# ============================================================
# 报告
# ============================================================

_CSS = """
:root { color-scheme: light; }
body { font-family: %(font)s; margin: 0; padding: 28px 32px 64px;
       background: #f9fafb; color: #111827; line-height: 1.6; }
h1 { font-size: 22px; margin: 0 0 4px; }
h2 { font-size: 16px; margin: 28px 0 10px; padding-bottom: 6px;
     border-bottom: 1px solid #e5e7eb; }
.sub { color: #6b7280; font-size: 13px; margin-bottom: 18px; }
.card { background: #fff; border: 1px solid #e5e7eb; border-radius: 8px;
        padding: 14px 16px; margin: 12px 0; }
.meta { display: grid; grid-template-columns: max-content 1fr;
        gap: 4px 16px; font-size: 13px; }
.meta dt { color: #6b7280; }
.meta dd { margin: 0; }
table { border-collapse: collapse; font-size: 13px; width: 100%%; }
th, td { border: 1px solid #e5e7eb; padding: 5px 9px; text-align: right; }
th { background: #f3f4f6; font-weight: 600; }
th:first-child, td:first-child { text-align: left; }
.note { border-left: 3px solid #2563eb; background: #eff6ff; padding: 9px 13px;
        margin: 10px 0; font-size: 13px; border-radius: 0 6px 6px 0; }
.note.warn { border-color: #d97706; background: #fffbeb; }
.note.error { border-color: #dc2626; background: #fef2f2; }
.note.ok { border-color: #059669; background: #ecfdf5; }
.empty { color: #9ca3af; font-size: 13px; }
footer { margin-top: 32px; color: #9ca3af; font-size: 12px; }
code { background: #f3f4f6; padding: 1px 4px; border-radius: 3px; font-size: 12px; }
""" % {'font': _FONT}


class HtmlReport:
    """
    自包含 HTML 报告（零 CDN / 零 JS）。

    :param title: str, 报告标题
    :param meta: dict 可选, 顶部元信息（模型、拓扑、时间、参数…）
    :param subtitle: str 可选, 副标题
    """

    def __init__(self, title: str = 'TPC 仿真报告', meta: Optional[Dict[str, Any]] = None,
                 subtitle: str = ''):
        self.title = title
        self.subtitle = subtitle
        self.meta: Dict[str, Any] = dict(meta or {})
        self._blocks: List[str] = []
        self._footnotes: List[str] = []

    # ---- 通用块 ----

    def add_section(self, heading: str, body_html: str = '') -> 'HtmlReport':
        """加一个带标题的小节。"""
        self._blocks.append(
            f'<h2>{_esc(heading)}</h2>\n<div class="card">{body_html}</div>')
        return self

    def add_html(self, raw_html: str) -> 'HtmlReport':
        """直接塞一段 HTML（调用方自负转义责任）。"""
        self._blocks.append(raw_html)
        return self

    def add_note(self, text: str, level: str = 'info') -> 'HtmlReport':
        """
        加一条提示。

        :param text: str, 内容
        :param level: str, ``'info'`` / ``'ok'`` / ``'warn'`` / ``'error'``
        """
        cls = level if level in ('info', 'ok', 'warn', 'error') else 'info'
        self._blocks.append(f'<div class="note {cls}">{_esc(text)}</div>')
        return self

    def add_table(self, header: Sequence[Any], rows: Sequence[Sequence[Any]],
                  caption: str = '') -> 'HtmlReport':
        """加一个表格。"""
        head = ''.join(f'<th>{_esc(h)}</th>' for h in header)
        body = '\n'.join(
            '<tr>' + ''.join(f'<td>{_esc(_fmt(c)) if not isinstance(c, str) else _esc(c)}</td>'
                             for c in row) + '</tr>'
            for row in rows)
        cap = f'<h2>{_esc(caption)}</h2>' if caption else ''
        self._blocks.append(
            f'{cap}<div class="card"><table><thead><tr>{head}</tr></thead>'
            f'<tbody>{body}</tbody></table></div>')
        return self

    # ---- 图 ----

    def add_s_parameters(self, data: Dict[str, Any],
                         note: str = '', highlight: Optional[Sequence[Tuple[float, str]]] = None,
                         in_db: bool = True) -> 'HtmlReport':
        """
        加 S 参数曲线（多迹叠加）。

        :param data: dict, ``{名称: ndarray/序列 (n,2)}``，第 0 列频率、第 1 列 S 值；
            也接受 ``{名称: (freqs, values)}``
        :param note: str, 图下附注
        :param highlight: 可选, ``[(频点, 标注), …]``
        :param in_db: bool, True 时把复数/线性幅度转成 dB
        :return: self
        """
        series = []
        for name, arr in sorted(data.items()):
            xs, ys = _split_xy(arr)
            vals = _to_db(ys) if in_db else [float(v) for v in ys]
            series.append((name, xs, vals))
        self.add_section('S 参数', svg_line_chart(
            series, xlabel='频率 [GHz]', ylabel='|S| [dB]' if in_db else '|S|',
            highlight=highlight))
        if note:
            self.add_note(note)
        return self

    def add_s_parameters_csv(self, csv_path: str, note: str = '',
                             highlight: Optional[Sequence[Tuple[float, str]]] = None
                             ) -> 'HtmlReport':
        """
        从 `cst_solver.Result.export_s_parameters_csv()` 写出的 CSV 读数据并画图。

        （阶段 5 的导出 → 阶段 7 的报告，一条链打通。）

        :param csv_path: str, CSV 路径（第一列频率、其余列 S 参数，值为 dB）
        :param note: str, 附注
        :param highlight: 可选, 竖直参考线
        :return: self
        """
        with open(csv_path, encoding='utf-8-sig', newline='') as fh:
            reader = csv.reader(fh)
            header = next(reader, None)
            if not header:
                raise ValueError(f'CSV 为空：{csv_path}')
            cols = [list() for _ in header]
            for row in reader:
                if not row:
                    continue
                for i, cell in enumerate(row[:len(cols)]):
                    try:
                        cols[i].append(float(cell))
                    except ValueError:
                        cols[i].append(float('nan'))
        freqs = cols[0]
        series = [(header[j], freqs, cols[j]) for j in range(1, len(cols))]
        self.add_section('S 参数（来自 ' + os.path.basename(csv_path) + '）',
                         svg_line_chart(series, xlabel='频率 [GHz]', ylabel='|S| [dB]',
                                        highlight=highlight))
        if note:
            self.add_note(note)
        return self

    def add_heatmap(self, matrix, x_labels, y_labels, title: str = '热力图',
                    xlabel: str = '', ylabel: str = '', note: str = '',
                    digits: int = 1) -> 'HtmlReport':
        """加热力图（如参数扫描结果）。"""
        self.add_section(title, svg_heatmap(matrix, x_labels, y_labels,
                                            xlabel=xlabel, ylabel=ylabel,
                                            digits=digits))
        if note:
            self.add_note(note)
        return self

    def add_polar(self, theta_deg, values, title: str = '远场方向图',
                  rlabel: str = 'dB', note: str = '',
                  series=None) -> 'HtmlReport':
        """加远场极坐标方向图（标出峰值方向）。"""
        self.add_section(title, svg_polar(theta_deg, values, rlabel=rlabel,
                                          series=series))
        if note:
            self.add_note(note)
        return self

    def add_timeline(self, records, title: str = '步骤时间线',
                     note: str = '') -> 'HtmlReport':
        """加步骤时间线（通常直接喂审计记录）。"""
        self.add_section(title, svg_timeline(records))
        if note:
            self.add_note(note)
        return self

    def add_audit(self, audit, title: str = '审计与耗时') -> 'HtmlReport':
        """
        从 `AuditLog` 直接生成审计小节（事件表 + 时间线 + 失败步骤）。

        :param audit: AuditLog 实例
        :param title: str, 小节标题
        :return: self
        """
        records = audit.read() if hasattr(audit, 'read') else list(audit)
        errors = [r for r in records if r.get('status') == 'error']
        self.add_section(title, svg_timeline(records, title='各步骤耗时'))
        if errors:
            for rec in errors:
                self.add_note(f"失败步骤 {rec.get('tool')}：{rec.get('error', '')}",
                              level='error')
        else:
            self.add_note(f'共 {len(records)} 条记录，无失败步骤。', level='ok')
        skip = {'ts', 'epoch', 'status', 'error'}
        rows = [[r.get('tool'), r.get('ts'), r.get('status'),
                 r.get('duration_s') if r.get('duration_s') is not None else '',
                 ', '.join(f'{k}={v}' for k, v in r.items() if k not in skip)]
                for r in records]
        if rows:
            self.add_table(['步骤', '时间', '状态', '耗时 (s)', '字段'], rows)
        return self

    # ---- 输出 ----

    def to_html(self) -> str:
        """渲染成完整 HTML 字符串。"""
        meta_rows = '\n'.join(
            f'<dt>{_esc(k)}</dt><dd>{_esc(v)}</dd>' for k, v in self.meta.items())
        meta_html = f'<div class="card"><dl class="meta">{meta_rows}</dl></div>' \
            if meta_rows else ''
        sub = f'<div class="sub">{_esc(self.subtitle)}</div>' if self.subtitle else ''
        foot = ('<footer>由 <code>topo_modeler/report.py</code> 生成 · '
                '自包含 HTML（无 CDN / 无 JS）· '
                f'{_esc(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))}</footer>')
        return (
            '<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n'
            '<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f'<title>{_esc(self.title)}</title>\n'
            f'<style>{_CSS}</style>\n</head>\n<body>\n'
            f'<h1>{_esc(self.title)}</h1>\n{sub}\n{meta_html}\n'
            + '\n'.join(self._blocks) + '\n' + foot + '\n</body>\n</html>\n')

    def write(self, path: str) -> str:
        """
        写出 HTML 文件。

        :param path: str, 输出路径
        :return: str, 写出的绝对路径
        """
        path = os.path.abspath(path)
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(self.to_html())
        return path

    def __repr__(self):
        return f"HtmlReport(title={self.title!r}, blocks={len(self._blocks)})"


# ============================================================
# 便捷构造
# ============================================================

def _split_xy(arr) -> Tuple[List[float], List[Any]]:
    """
    把 ``(n,2)`` 数组或 ``(xs, ys)`` 对拆成 ``(频率, 值)`` 两个 list。

    ⚠️ **第二列不做 `float()`** —— CST 返回的 S 参数是**复数**
    （阶段 4 T6 踩过：CST 的 xdata/ydata 是 complex，强转会触发
    `ComplexWarning: Casting complex values to real discards the imaginary part`，
    直接 `float()` 更会 `TypeError`）。复数交给 `_to_db()` 取模值处理。
    """
    if isinstance(arr, tuple) and len(arr) == 2:
        return ([complex(v).real for v in arr[0]], list(arr[1]))
    rows = list(arr)
    if rows and isinstance(rows[0], (list, tuple)) and len(rows[0]) >= 2:
        return ([complex(r[0]).real for r in rows], [r[1] for r in rows])
    raise ValueError('S 参数数据应为 (n,2) 数组或 (xs, ys) 二元组')


def _to_db(values) -> List[float]:
    """复数/线性幅度 → dB（20·log10|v|）。"""
    out = []
    for v in values:
        try:
            mag = abs(complex(v))
        except (TypeError, ValueError):
            mag = float(v)
        out.append(20 * math.log10(mag) if mag > 0 else -300.0)
    return out


def report_from_s_parameters(data: Dict[str, Any], title: str = 'S 参数报告',
                             meta: Optional[Dict[str, Any]] = None,
                             note: str = '') -> HtmlReport:
    """
    从 ``{名称: (n,2) 数组}`` 快速生成一份只含 S 参数曲线的报告。

    :param data: dict, 见 :meth:`HtmlReport.add_s_parameters`
    :param title: str, 标题
    :param meta: dict 可选, 顶部元信息
    :param note: str, 附注
    :return: HtmlReport
    """
    rep = HtmlReport(title=title, meta=meta)
    rep.add_s_parameters(data, note=note)
    return rep


def report_from_s_parameters_csv(csv_path: str, title: str = 'S 参数报告',
                                 meta: Optional[Dict[str, Any]] = None,
                                 note: str = '') -> HtmlReport:
    """
    从阶段 5 导出的 S 参数 CSV 快速生成报告。

    :param csv_path: str, CSV 路径
    :param title: str, 标题
    :param meta: dict 可选, 顶部元信息
    :param note: str, 附注
    :return: HtmlReport
    """
    rep = HtmlReport(title=title, meta=meta)
    rep.add_s_parameters_csv(csv_path, note=note)
    return rep
