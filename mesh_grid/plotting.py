# -*- coding: utf-8 -*-
"""跨平台中文绘图字体配置；不在导入时修改全局样式。"""

from contextlib import contextmanager
from functools import lru_cache
import os
from pathlib import Path
import warnings

import matplotlib as mpl
from matplotlib import font_manager
from matplotlib.ft2font import FT2Font

__all__ = ['configure_chinese_font', 'chinese_plot_style']

_SAMPLE = '中文频率透射反射参数增益波导天线仿真结果'
_PREFERRED = ('Microsoft YaHei', 'SimHei', 'Noto Sans CJK SC',
              'Source Han Sans SC', 'PingFang SC', 'WenQuanYi Micro Hei',
              'SimSun', 'Arial Unicode MS')


@lru_cache(maxsize=128)
def _covers(path, text):
    """检查实际字形，避免只检查字体名称却仍然缺字。"""
    try:
        charmap = FT2Font(path).get_charmap()
        return all(ord(char) in charmap for char in text if not char.isspace())
    except (OSError, RuntimeError):
        return False


def configure_chinese_font(*, font_path=None, text=_SAMPLE, strict=False):
    """选择有中文字形的字体并配置后续绘图，返回字体族名或 None。

    参数：font_path 指定本机字体文件，也可设置 TPC_CJK_FONT；text 为需校验的
    中文文本；strict=True 时找不到字体就抛 RuntimeError，不产出缺字图。
    说明：在创建图形前调用；不下载字体、不强制切换 backend。负号使用 ASCII；
    PDF 嵌入 TrueType，SVG 文字转路径，使导出文件不依赖查看机器安装字体。
    """
    path = font_path or os.environ.get('TPC_CJK_FONT')
    required = ''.join(sorted(set(_SAMPLE + text)))
    family = None
    if path:
        path = str(Path(path).expanduser().resolve())
        if not Path(path).is_file():
            raise FileNotFoundError(f'中文字体文件不存在: {path}')
        if not _covers(path, required):
            raise ValueError(f'指定字体不能覆盖所需中文字符: {path}')
        font_manager.fontManager.addfont(path)
        family = font_manager.FontProperties(fname=path).get_name()
    else:
        entries = list(font_manager.fontManager.ttflist)
        current = [name for name in mpl.rcParams['font.family'] if name != 'sans-serif']
        names = tuple(dict.fromkeys(current + list(_PREFERRED)))
        priority = {name: i for i, name in enumerate(names)}
        entries.sort(key=lambda item: (priority.get(item.name, len(priority)), item.name))
        seen = set()
        for entry in entries:
            if entry.name in seen:
                continue
            seen.add(entry.name)
            # 校验 Matplotlib 真正会选中的常规字体，而非同名字体的某个粗体条目。
            try:
                resolved = font_manager.findfont(font_manager.FontProperties(family=[entry.name]),
                                                 fallback_to_default=False)
            except ValueError:
                continue
            if _covers(resolved, required):
                family = entry.name
                break
    if family is None:
        message = ('未找到覆盖中文的 Matplotlib 字体；请安装 Noto Sans CJK SC/微软雅黑，'
                   '或设置 TPC_CJK_FONT 为字体文件路径。无法安装时改用英文标签；'
                   '不要忽略 Glyph missing 警告后发布图片。')
        if strict:
            raise RuntimeError(message)
        warnings.warn(message, UserWarning, stacklevel=2)
        return None
    mpl.rcParams.update({'font.family': [family],
                         'font.sans-serif': [family, 'DejaVu Sans'],
                         'axes.unicode_minus': False,
                         'pdf.fonttype': 42, 'ps.fonttype': 42, 'svg.fonttype': 'path'})
    return family


@contextmanager
def chinese_plot_style(*, font_path=None, text=_SAMPLE, strict=False):
    """局部中文绘图样式；在上下文内创建并保存图，退出后恢复原 rcParams。

    参数与 configure_chinese_font 相同；上下文返回选中的字体族名。
    """
    with mpl.rc_context():
        yield configure_chinese_font(font_path=font_path, text=text, strict=strict)
