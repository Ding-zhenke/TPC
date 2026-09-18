# Matplotlib 中文绘图

不要在各文件中写死 `SimHei` 或 `Microsoft YaHei`；同一个字体在不同机器上不一定存在。共用入口会检查已安装字体及实际中文字形，同时处理负号和导出字体。

建议在创建图形前调用，批处理时在上下文内完成保存：

```python
import matplotlib
matplotlib.use('Agg')  # 仅无界面批处理需要；必须放在 import pyplot 前
import matplotlib.pyplot as plt
from mesh_grid.plotting import chinese_plot_style

with chinese_plot_style(text='频率透射系数', strict=True) as font:
    fig, ax = plt.subplots()
    ax.plot([300, 320, 340], [-2, -3, -1])
    ax.set_xlabel('频率 (GHz)')
    ax.set_ylabel('透射系数 (dB)')
    fig.tight_layout()
    fig.savefig('s21.png', dpi=180, bbox_inches='tight')
    fig.savefig('s21.pdf', bbox_inches='tight')
    plt.close(fig)
```

交互式 notebook 若希望后续所有图使用中文字体，可调用 `configure_chinese_font(strict=True)`；它会更改当前 Matplotlib 的全局样式。`chinese_plot_style()` 退出后恢复原样式。

选择顺序：显式 `font_path` → 环境变量 `TPC_CJK_FONT` → 当前可用字体及常见中文字体 → 其他覆盖所需字形的字体。可优先使用微软雅黑、黑体、Noto Sans CJK SC、思源黑体、苹方或文泉驿；只设置名称而不检查字形不能保证成功。

自定义字体例子：

```powershell
$env:TPC_CJK_FONT = 'C:\Windows\Fonts\msyh.ttc'
```

指定文件必须真实存在并覆盖所需字符。检测样本文字加上 `text` 参数，罕见字请放入 `text` 中一起校验。没有合适字体时默认发明确警告；正式导出推荐 `strict=True` 直接阻止缺字图。不能安装字体时改用英文标题/坐标，不屏蔽 Glyph missing 警告。

PNG 固化字形；PDF 使用 TrueType 嵌入；SVG 将文字转为路径，查看机器无需额外装字体（代价是 SVG 文字不便编辑/搜索）。负刻度使用 ASCII 连字符，避免字体缺少 U+2212。

三角网格、六边形可视化器、TopoPath 预览、GRIN 预览、GA 个体图已接入自动配置。自己写的 Matplotlib 图仍需使用上述入口；已有 Figure 的文字不会因晚调用配置而全部自动更换。仅导入算法模块不再修改字体。

验收：保存一张含中文标题、坐标、图例和负数刻度的 PNG，确认无缺字警告并打开检查。库不自动下载字体，也不会替用户改全局 Matplotlib 配置文件。
