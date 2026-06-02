# -*- coding: utf-8 -*-
"""
cst_solver API 文档生成器
==========================
扫描 cst_solver 包中的所有 Mixin 类，从 docstring 提取方法签名和说明，
生成一份综合的 HTML API 文档。

用法:
    python scripts/gen_docs.py

输出:
    cst_solver/docs/cst_solver_api.html

@author: PC
"""

import os
import sys
import inspect
import importlib
import html
from datetime import datetime

# 项目根目录
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# ============================================================
# 模块扫描配置 — 每个 Mixin 的分类和描述
# ============================================================
MODULE_SCAN_CONFIG = [
    # (模块路径, 分类名, 分类描述)
    ("cst_solver.project",          "项目操作",     "项目打开、关闭、保存、激活"),
    ("cst_solver.units",            "单位设置",     "频率、长度、时间等单位配置"),
    ("cst_solver.parameters",       "参数系统",     "参数、表达式、频率范围管理"),
    ("cst_solver.modeling.primitives", "基本体建模", "Brick, Cylinder, Sphere, Cone, Torus 等基本体"),
    ("cst_solver.modeling.curves",     "曲线建模",  "Polygon, Arc, Circle, Ellipse, Line, Spline 等曲线"),
    ("cst_solver.modeling.curves_ops", "曲线操作",  "ExtrudeCurve, LoftCurves, SweepCurve 等曲线操作"),
    ("cst_solver.modeling.booleans",   "布尔运算",  "Add, Subtract, Insert, Intersect, Blend 等布尔操作"),
    ("cst_solver.modeling.transforms", "变换操作",  "Translate, Rotate, Mirror, Align 等变换"),
    ("cst_solver.modeling.picks",      "选取操作",  "Pick edge/face/vertex，选取实体表面/边/点"),
    ("cst_solver.material.materials",  "材料与组件","材料定义、材料库、组件管理"),
    ("cst_solver.simulation.ports",    "端口",      "Port, DiscretePort, DiscreteFacePort, FloquetPort"),
    ("cst_solver.simulation.sources",  "激励源",    "PlaneWave, Coil, CurrentPath, VoltageWire 等"),
    ("cst_solver.simulation.monitors", "监视器",    "Monitor, Probe, 场监视器, 探针"),
    ("cst_solver.simulation.boundary", "边界条件",  "Boundary, Background, LayerStacking"),
    ("cst_solver.simulation.solver",   "求解器",    "Solver, FDSolver, EigenmodeSolver, IESolver 等"),
    ("cst_solver.mesh.mesh",          "网格设置",   "Mesh, MeshAdaption3D 自适应网格"),
    ("cst_solver.import_export.io",   "导入导出",   "SAT/DXF/STEP/IGES/STL 导入导出"),
    ("cst_solver.postprocessing.proc","后处理",     "QFactor, CombineResults, SAR, PostProcess1D"),
    ("cst_solver.postprocessing.farfield","远场分析","FarfieldPlot, 远场计算"),
    ("cst_solver.postprocessing.result_export","结果导出","ASCIIExport, 场数据导出"),
]

# FaceOpsMixin 定义在 cst_solver/__init__.py 中，单独处理
_FACE_OPS_MIXIN = ("cst_solver", "面操作", "旋转拉伸、表面拉伸、曲线走线等基于面的建模")


def _extract_from_module(module, mixin_suffix="Mixin"):
    """从模块中提取指定后缀类的公开方法"""
    methods = []
    for name, obj in inspect.getmembers(module):
        if not (inspect.isclass(obj) and name.endswith(mixin_suffix)):
            continue
        for method_name, method_obj in inspect.getmembers(obj):
            if method_name.startswith("_"):
                continue
            if not inspect.isfunction(method_obj) and not inspect.ismethod(method_obj):
                continue
            try:
                sig = str(inspect.signature(method_obj))
                if sig.startswith("(self"):
                    sig = sig[5:].lstrip(", ")
                sig = f"{method_name}{sig}"
            except (ValueError, TypeError):
                sig = f"{method_name}(...)"
            doc = inspect.getdoc(method_obj) or ""
            methods.append({
                "name": method_name,
                "signature": sig,
                "doc": doc,
                "class": name.replace("Mixin", ""),
            })
    return methods


def extract_mixin_methods(module_path):
    """导入模块并提取所有 Mixin 类的公开方法"""
    try:
        module = importlib.import_module(module_path)
    except Exception as e:
        return [], str(e)
    return _extract_from_module(module), None


def build_html():
    """构建完整的 HTML 文档"""
    all_categories = []
    total_count = 0

    for module_path, cat_name, cat_desc in MODULE_SCAN_CONFIG:
        methods, error = extract_mixin_methods(module_path)
        if error:
            methods = []
        all_categories.append({
            "name": cat_name,
            "description": cat_desc,
            "module": module_path,
            "methods": methods,
            "error": error,
        })
        total_count += len(methods)

    # 处理 FaceOpsMixin（定义在 cst_solver/__init__.py 中）
    try:
        import cst_solver
        face_methods, _ = _extract_from_module(cst_solver)
        if face_methods:
            all_categories.append({
                "name": _FACE_OPS_MIXIN[1],
                "description": _FACE_OPS_MIXIN[2],
                "module": _FACE_OPS_MIXIN[0],
                "methods": face_methods,
                "error": None,
            })
            total_count += len(face_methods)
    except Exception as e:
        pass  # FaceOpsMixin 不可用时不报错

    # ============================================================
    # CSS 样式
    # ============================================================
    css = """
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif;
    background: #f5f7fa; color: #2c3e50; line-height: 1.7;
    padding: 0;
}
.header {
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
    color: #fff; padding: 40px 0; text-align: center;
}
.header h1 { font-size: 32px; margin-bottom: 8px; letter-spacing: 1px; }
.header .subtitle { font-size: 15px; opacity: 0.85; }
.header .stats { margin-top: 15px; font-size: 14px; opacity: 0.75; }
.container { max-width: 1100px; margin: 0 auto; padding: 0 20px; }

/* 导航 */
.nav {
    position: sticky; top: 0; z-index: 100;
    background: #fff; border-bottom: 1px solid #e0e0e0;
    padding: 10px 0; overflow-x: auto; white-space: nowrap;
}
.nav-inner { max-width: 1100px; margin: 0 auto; padding: 0 20px; display: flex; gap: 6px; flex-wrap: wrap; }
.nav a {
    font-size: 12px; color: #3498db; text-decoration: none;
    padding: 3px 10px; border-radius: 12px; border: 1px solid #3498db;
    transition: all 0.2s;
}
.nav a:hover { background: #3498db; color: #fff; }

/* 搜索框 */
.search-box {
    max-width: 1100px; margin: 20px auto; padding: 0 20px;
}
.search-box input {
    width: 100%; padding: 12px 20px; font-size: 15px;
    border: 2px solid #ddd; border-radius: 8px; outline: none;
    transition: border-color 0.3s;
}
.search-box input:focus { border-color: #3498db; }

/* 分类卡片 */
.category {
    background: #fff; border-radius: 10px; margin: 16px auto;
    max-width: 1100px; box-shadow: 0 1px 4px rgba(0,0,0,0.06);
    overflow: hidden;
}
.category-header {
    background: #f8f9fa; padding: 16px 24px;
    border-bottom: 1px solid #eef0f2;
    cursor: pointer; user-select: none;
    display: flex; justify-content: space-between; align-items: center;
}
.category-header:hover { background: #f0f2f5; }
.category-title { font-size: 18px; font-weight: 600; color: #1a1a2e; }
.category-title .badge {
    font-size: 12px; background: #3498db; color: #fff;
    padding: 1px 8px; border-radius: 10px; margin-left: 8px;
    font-weight: 400;
}
.category-desc { font-size: 13px; color: #7f8c8d; margin-top: 2px; }
.category-toggle { color: #95a5a6; font-size: 14px; }
.category-body { padding: 0; }

/* 方法条目 */
.method {
    padding: 16px 24px; border-bottom: 1px solid #f0f2f5;
    transition: background 0.15s;
}
.method:last-child { border-bottom: none; }
.method:hover { background: #fafbfc; }
.method-name {
    font-family: 'Cascadia Code', 'Consolas', monospace;
    font-size: 14px; font-weight: 600; color: #2c3e50;
}
.method-signature {
    font-family: 'Cascadia Code', 'Consolas', monospace;
    font-size: 12px; color: #7f8c8d; margin-top: 2px;
    word-break: break-all;
}
.method-doc {
    margin-top: 8px; font-size: 13.5px; color: #444;
    white-space: pre-wrap; word-break: break-word;
}
.method-doc b { color: #2c3e50; }

/* 表格 */
.table-wrap { max-width: 1100px; margin: 20px auto; padding: 0 20px; }
table {
    width: 100%; border-collapse: collapse; background: #fff;
    border-radius: 10px; overflow: hidden; box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}
th {
    background: #f8f9fa; padding: 12px 16px; font-size: 13px;
    text-align: left; border-bottom: 2px solid #dee2e6;
    font-weight: 600; color: #1a1a2e;
}
td { padding: 10px 16px; border-bottom: 1px solid #f0f2f5; font-size: 13px; }
tr:hover td { background: #fafbfc; }
td a { color: #3498db; text-decoration: none; }
td a:hover { text-decoration: underline; }
.method-tag {
    display: inline-block; font-size: 10px; padding: 1px 6px;
    border-radius: 3px; color: #fff; font-weight: 500;
}

/* 页脚 */
.footer {
    text-align: center; padding: 30px; color: #95a5a6;
    font-size: 12px; margin-top: 30px;
}

/* 隐藏搜索不匹配 */
.hidden { display: none !important; }
"""

    # ============================================================
    # 构建 HTML 体
    # ============================================================
    # 导航链接
    nav_links = ""
    for cat in all_categories:
        anchor = cat["name"].replace(" ", "-")
        nav_links += f'<a href="#{anchor}">{cat["name"]}</a>\n'

    # 总览表格
    table_rows = ""
    emoji_map = {
        "项目操作": "📁", "单位设置": "📏", "参数系统": "⚙️",
        "基本体建模": "🧊", "曲线建模": "✏️", "曲线操作": "🔀",
        "布尔运算": "➕", "变换操作": "🔄", "选取操作": "👆",
        "材料与组件": "🧪", "端口": "🔌", "激励源": "⚡",
        "监视器": "📡", "边界条件": "🧱", "求解器": "🚀",
        "网格设置": "🔲", "导入导出": "📂", "后处理": "📊",
        "远场分析": "📡", "结果导出": "💾",
    }
    for cat in all_categories:
        emoji = emoji_map.get(cat["name"], "📦")
        for m in cat["methods"]:
            doc_first_line = m["doc"].split("\n")[0] if m["doc"] else ""
            table_rows += (
                f'<tr><td>{emoji}</td>'
                f'<td>{cat["name"]}</td>'
                f'<td><a href="#{cat["name"].replace(" ", "-")}-{m["name"]}">{m["name"]}</a></td>'
                f'<td>{html.escape(doc_first_line[:80])}</td></tr>\n'
            )

    # 分类卡片
    categories_html = ""
    for cat in all_categories:
        anchor = cat["name"].replace(" ", "-")
        count = len(cat["methods"])
        error_html = f'<div style="color:#e74c3c;padding:16px;">⚠ 加载失败: {html.escape(cat["error"] or "")}</div>' if cat["error"] else ""

        methods_html = ""
        for m in cat["methods"]:
            doc_html = html.escape(m["doc"]).replace("\n", "<br>")
            doc_html = doc_html.replace("Args:", "<b>Args:</b>")
            doc_html = doc_html.replace("Returns:", "<b>Returns:</b>")
            doc_html = doc_html.replace("Raises:", "<b>Raises:</b>")
            doc_html = doc_html.replace("Parameters:", "<b>Parameters:</b>")
            doc_html = doc_html.replace("----------", "")
            doc_html = doc_html.replace("    - ", "&emsp;- ")
            doc_html = doc_html.replace(":param ", "<b>· </b>")
            doc_html = doc_html.replace(":type ", "&emsp;类型: ")
            doc_html = doc_html.replace(":return:", "<b>返回:</b>")
            doc_html = doc_html.replace(":rtype:", "&emsp;类型: ")

            methods_html += f"""
            <div class="method" id="{anchor}-{m['name']}">
                <div class="method-name">{html.escape(m['name'])}</div>
                <div class="method-signature">{html.escape(m['signature'])}</div>
                <div class="method-doc">{doc_html}</div>
            </div>
            """

        categories_html += f"""
        <div class="category" data-category="{cat['name']}">
            <div class="category-header" onclick="toggleCategory(this)">
                <div>
                    <div class="category-title">{cat['name']} <span class="badge">{count}</span></div>
                    <div class="category-desc">{cat['description']}</div>
                </div>
                <div class="category-toggle">▼</div>
            </div>
            <div class="category-body">
                {error_html}
                {methods_html}
            </div>
        </div>
        """

    # ============================================================
    # 完整 HTML
    # ============================================================
    html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>cst_solver API 文档</title>
    <style>{css}</style>
</head>
<body>

<div class="header">
    <div class="container">
        <h1>📖 cst_solver API 文档</h1>
        <div class="subtitle">CST Studio Suite 自动化 Python 接口 — Mixin 多继承封装</div>
        <div class="stats">共 {total_count} 个公开方法 · {len(all_categories)} 个分类</div>
    </div>
</div>

<div class="nav">
    <div class="nav-inner">
        <a href="#summary">📋 总览</a>
        {nav_links}
    </div>
</div>

<div class="search-box">
    <input type="text" id="search" placeholder="🔍 搜索方法名..." oninput="filterMethods(this.value)">
</div>

<div class="table-wrap" id="summary">
    <table>
        <thead><tr><th></th><th>分类</th><th>方法名</th><th>描述</th></tr></thead>
        <tbody>{table_rows}</tbody>
    </table>
</div>

{categories_html}

<div class="footer">
    <p>自动生成于 {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
    <p>TPC Project — cst_solver API v2.0</p>
    <p>共 {total_count} 个方法，扫描自 {len(MODULE_SCAN_CONFIG)} 个模块</p>
</div>

<script>
function toggleCategory(header) {{
    var body = header.parentElement.querySelector('.category-body');
    var toggle = header.querySelector('.category-toggle');
    if (body.style.display === 'none' || body.style.display === '') {{
        body.style.display = 'block';
        toggle.textContent = '▼';
    }} else {{
        body.style.display = 'none';
        toggle.textContent = '▶';
    }}
}}
// 默认全部展开
document.querySelectorAll('.category-body').forEach(function(el) {{
    el.style.display = 'block';
}});

function filterMethods(query) {{
    var q = query.toLowerCase().trim();
    // 获取所有方法条目
    var methods = document.querySelectorAll('.method');
    var categoryBodies = document.querySelectorAll('.category-body');
    var categories = document.querySelectorAll('.category');

    methods.forEach(function(m) {{
        var name = m.querySelector('.method-name').textContent.toLowerCase();
        if (!q || name.includes(q)) {{
            m.classList.remove('hidden');
        }} else {{
            m.classList.add('hidden');
        }}
    }});

    // 显示/隐藏分类
    categories.forEach(function(c) {{
        var visible = c.querySelectorAll('.method:not(.hidden)').length > 0;
        if (!q || visible) {{
            c.classList.remove('hidden');
        }} else {{
            c.classList.add('hidden');
        }}
    }});
}}
</script>

</body>
</html>"""

    return html_content


def main():
    docs_dir = os.path.join(_PROJECT_ROOT, "cst_solver", "docs")
    os.makedirs(docs_dir, exist_ok=True)

    print(f"正在扫描 {len(MODULE_SCAN_CONFIG)} 个模块并生成文档...")
    html_content = build_html()
    output_path = os.path.join(docs_dir, "cst_solver_api.html")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"✅ 文档已生成: {output_path}")


if __name__ == "__main__":
    main()
