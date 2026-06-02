# -*- coding: utf-8 -*-
"""
CST Solver API 文档自动生成器
==============================
扫描 cst_solver/ 包中所有 Mixin 类的方法和 docstring，
自动生成结构化 HTML 文档到 docs/cst_solver_api.html

用法:
    python -m cst_solver.scripts.gen_docs
    或 cd cst_solver && python scripts/gen_docs.py

输出:
    cst_solver/docs/cst_solver_api.html

@author: PC
"""

import os
import sys
import ast
import inspect
import textwrap
from pathlib import Path

# 项目根目录：gen_docs.py 位于 cst_solver/scripts/，其父的父 = 项目根
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CST_SOLVER_DIR = PROJECT_ROOT  # 脚本已在 cst_solver/ 内
OUTPUT_DIR = PROJECT_ROOT / "docs"
OUTPUT_FILE = OUTPUT_DIR / "cst_solver_api.html"

# 确保可以导入 cst_solver
sys.path.insert(0, str(PROJECT_ROOT))

# ============================================================
# 类别定义与映射
# ============================================================

CATEGORIES = {
    "ProjectMixin": "项目操作",
    "ParametersMixin": "参数管理",
    "UnitsMixin": "单位设置",
    "ModelingPrimitivesMixin": "基本体建模",
    "CurvesMixin": "曲线绘制",
    "CurveOpsMixin": "曲线操作",
    "WCSMixin": "工作坐标系",
    "SolidOpsMixin": "布尔运算",
    "TransformMixin": "变换操作",
    "PickMixin": "选取操作",
    "FaceOpsMixin": "面操作",
    "MaterialMixin": "材料与组件",
    "PortMixin": "端口设置",
    "SourceMixin": "激励源",
    "MonitorMixin": "监视器",
    "BoundaryMixin": "边界条件",
    "SolverMixin": "求解器",
    "MeshMixin": "网格设置",
    "IOMixin": "导入导出",
    "PostProcMixin": "后处理",
    "FarfieldMixin": "远场分析",
    "PlotMixin": "绘图控制",
    "ExportMixin": "结果导出",
}

# 每个类别的图标（Font Awesome 图标名）
CATEGORY_ICONS = {
    "项目操作": "folder-open",
    "参数管理": "sliders-h",
    "基本体建模": "cube",
    "曲线绘制": "draw-polygon",
    "曲线操作": "bezier-curve",
    "布尔运算": "intersection",
    "变换操作": "arrows-alt",
    "选取操作": "hand-pointer",
    "面操作": "layer-group",
    "材料与组件": "flask",
    "端口设置": "plug",
    "激励源": "bolt",
    "监视器": "eye",
    "边界条件": "border-all",
    "求解器": "microchip",
    "网格设置": "th",
    "导入导出": "file-import",
    "后处理": "chart-line",
    "远场分析": "satellite-dish",
    "结果导出": "file-export",
}

# 别名方法映射（旧名 → 新名）
ALIAS_MAP = {
    "square": "create_brick",
    "cylinder": "create_cylinder",
    "polyline": "create_polygon",
    "arc": "create_arc",
    "ellipse": "create_ellipse",
    "extrude": "extrude_curve",
    "add": "boolean_add",
    "substract": "boolean_subtract",
    "insert": "boolean_insert",
    "intersect": "boolean_intersect",
    "blend": "blend_edge",
    "rotation": "rotate",
    "para": "set_parameter",
    "paras": "set_parameters",
    "expression": "set_expression",
    "freq_limit": "set_frequency_range",
    "new_material": "create_material",
    "new_componet": "create_component",
    "add_port": "create_waveguide_port",
    "discrete_port": "create_discrete_face_port",
    "define_monitor": "create_field_monitor",
    "T_solver": "configure_time_solver",
    "project_open": "open_project",
    "project_close": "close_project",
    "sat_import": "import_sat",
    "dxf_import": "import_dxf",
    "field_export": "export_field",
    "patten_export": "export_pattern",
    "export_data": "export_to_ascii",
    "rotation_face": "rotate_face",
    "exclude_simulation": "exclude_from_simulation",
    "triangle": "create_triangular_prism",
    "hexagon": "create_hexagonal_prism",
    "wcs_reset": "reset_wcs",
    "wcs_rotate": "rotate_wcs",
    "wcs_translate": "translate_wcs",
    "wcs_align": "align_wcs",
    "wcs_set_origin": "set_wcs_origin",
    "wcs_store": "store_wcs",
    "wcs_restore": "restore_wcs",
    "wcs_scale": "scale_wcs",
    "plot_reset": "reset_plot",
}

# ============================================================
# HTML 模板
# ============================================================

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CST Solver Python API 文档</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">
<style>
:root {{
    --primary: #2563eb;
    --primary-light: #3b82f6;
    --primary-dark: #1d4ed8;
    --bg: #f8fafc;
    --card-bg: #ffffff;
    --text: #1e293b;
    --text-light: #64748b;
    --border: #e2e8f0;
    --accent-green: #10b981;
    --accent-orange: #f59e0b;
    --accent-red: #ef4444;
    --shadow: 0 1px 3px rgba(0,0,0,0.1), 0 1px 2px rgba(0,0,0,0.06);
    --shadow-md: 0 4px 6px rgba(0,0,0,0.07), 0 2px 4px rgba(0,0,0,0.06);
}}

* {{ margin: 0; padding: 0; box-sizing: border-box; }}

body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.6;
}}

/* Header */
.header {{
    background: linear-gradient(135deg, var(--primary), var(--primary-dark));
    color: white;
    padding: 32px 48px;
    position: sticky;
    top: 0;
    z-index: 100;
    box-shadow: var(--shadow-md);
}}
.header h1 {{
    font-size: 28px;
    font-weight: 700;
    margin-bottom: 4px;
}}
.header p {{
    font-size: 14px;
    opacity: 0.85;
    margin-top: 4px;
}}
.header-stats {{
    display: flex;
    gap: 24px;
    margin-top: 12px;
    font-size: 13px;
}}
.header-stats span {{
    display: flex;
    align-items: center;
    gap: 6px;
    opacity: 0.9;
}}

/* Search */
.search-bar {{
    position: relative;
    margin-top: 16px;
    max-width: 600px;
}}
.search-bar input {{
    width: 100%;
    padding: 10px 16px 10px 40px;
    border: none;
    border-radius: 8px;
    font-size: 14px;
    background: rgba(255,255,255,0.15);
    color: white;
    outline: none;
    transition: background 0.2s;
}}
.search-bar input::placeholder {{ color: rgba(255,255,255,0.7); }}
.search-bar input:focus {{ background: rgba(255,255,255,0.25); }}
.search-bar i {{
    position: absolute;
    left: 14px;
    top: 50%;
    transform: translateY(-50%);
    opacity: 0.7;
}}

/* Layout */
.container {{
    display: flex;
    max-width: 1400px;
    margin: 0 auto;
    padding: 24px;
    gap: 24px;
}}

/* Sidebar */
.sidebar {{
    width: 260px;
    flex-shrink: 0;
    position: sticky;
    top: 160px;
    height: calc(100vh - 180px);
    overflow-y: auto;
    padding-right: 8px;
}}
.sidebar::-webkit-scrollbar {{ width: 4px; }}
.sidebar::-webkit-scrollbar-thumb {{ background: var(--border); border-radius: 2px; }}
.sidebar h3 {{
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: var(--text-light);
    margin-bottom: 12px;
}}
.sidebar a {{
    display: block;
    padding: 6px 12px;
    font-size: 13px;
    color: var(--text-light);
    text-decoration: none;
    border-radius: 6px;
    transition: all 0.15s;
    cursor: pointer;
}}
.sidebar a:hover {{
    background: #e2e8f0;
    color: var(--primary);
}}
.sidebar a i {{
    width: 18px;
    margin-right: 6px;
    font-size: 12px;
}}

/* Main content */
.main-content {{
    flex: 1;
    min-width: 0;
}}

/* Category section */
.category {{
    margin-bottom: 32px;
}}
.category-header {{
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 16px 20px;
    background: var(--card-bg);
    border-radius: 12px;
    box-shadow: var(--shadow);
    margin-bottom: 16px;
    cursor: pointer;
    user-select: none;
    transition: box-shadow 0.2s;
}}
.category-header:hover {{
    box-shadow: var(--shadow-md);
}}
.category-header h2 {{
    font-size: 18px;
    font-weight: 600;
    flex: 1;
}}
.category-header .count {{
    font-size: 13px;
    color: var(--text-light);
    background: var(--bg);
    padding: 2px 10px;
    border-radius: 12px;
}}
.category-header .icon {{
    width: 36px;
    height: 36px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 8px;
    font-size: 16px;
    color: white;
}}

/* Method card */
.method-card {{
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 10px;
    margin-bottom: 8px;
    overflow: hidden;
    transition: box-shadow 0.2s;
}}
.method-card:hover {{
    box-shadow: var(--shadow);
}}
.method-card-header {{
    display: flex;
    align-items: center;
    padding: 12px 20px;
    cursor: pointer;
    gap: 12px;
}}
.method-card-header .name {{
    font-family: 'SF Mono', 'Fira Code', 'Cascadia Code', monospace;
    font-size: 14px;
    font-weight: 600;
    color: var(--primary);
}}
.method-card-header .name.alias {{
    color: var(--accent-orange);
    font-weight: 400;
    font-size: 13px;
}}
.method-card-header .desc {{
    font-size: 13px;
    color: var(--text-light);
    flex: 1;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    margin-left: 8px;
}}
.method-card-header .badge {{
    font-size: 11px;
    padding: 2px 8px;
    border-radius: 4px;
    background: var(--bg);
    color: var(--text-light);
    white-space: nowrap;
}}
.method-card-header .expand-icon {{
    font-size: 12px;
    color: var(--text-light);
    transition: transform 0.2s;
}}
.method-card-header .expand-icon.open {{
    transform: rotate(90deg);
}}

/* Method details (collapsible) */
.method-details {{
    display: none;
    padding: 0 20px 16px 20px;
    border-top: 1px solid var(--border);
}}
.method-details.open {{
    display: block;
}}
.method-details .section {{
    margin-top: 12px;
}}
.method-details .section-title {{
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: var(--text-light);
    margin-bottom: 6px;
}}

/* Signature */
.signature {{
    background: #f1f5f9;
    padding: 8px 12px;
    border-radius: 6px;
    font-family: 'SF Mono', 'Fira Code', 'Cascadia Code', monospace;
    font-size: 13px;
    overflow-x: auto;
    white-space: pre-wrap;
    word-break: break-all;
}}

/* Parameter table */
.params-table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
}}
.params-table th {{
    text-align: left;
    padding: 6px 12px;
    background: #f8fafc;
    border-bottom: 2px solid var(--border);
    font-weight: 600;
    color: var(--text-light);
    font-size: 12px;
}}
.params-table td {{
    padding: 6px 12px;
    border-bottom: 1px solid var(--border);
    vertical-align: top;
}}
.params-table .param-name {{
    font-family: 'SF Mono', monospace;
    font-weight: 500;
    color: var(--primary);
    white-space: nowrap;
}}
.params-table .param-type {{
    color: var(--accent-green);
    font-size: 12px;
}}
.params-table .param-desc {{
    color: var(--text);
}}
.params-table tr:last-child td {{
    border-bottom: none;
}}

/* Alias info */
.alias-info {{
    background: #fffbeb;
    border: 1px solid #fde68a;
    border-radius: 6px;
    padding: 8px 12px;
    font-size: 13px;
    color: #92400e;
    margin-top: 8px;
}}
.alias-info i {{
    margin-right: 6px;
}}

/* Return section */
.return-section {{
    background: #f0fdf4;
    border: 1px solid #bbf7d0;
    border-radius: 6px;
    padding: 8px 12px;
    font-size: 13px;
    color: #166534;
}}

/* Source file */
.source-file {{
    font-size: 12px;
    color: var(--text-light);
    margin-top: 8px;
}}
.source-file code {{
    background: #f1f5f9;
    padding: 2px 6px;
    border-radius: 4px;
    font-family: 'SF Mono', monospace;
    font-size: 12px;
}}

/* Description text */
.desc-text {{
    font-size: 14px;
    line-height: 1.7;
    color: var(--text);
}}
.desc-text p {{ margin-bottom: 8px; }}

/* No results */
.no-results {{
    text-align: center;
    padding: 48px;
    color: var(--text-light);
    display: none;
}}
.no-results i {{
    font-size: 48px;
    margin-bottom: 16px;
    opacity: 0.5;
}}

/* Animations */
@keyframes fadeIn {{
    from {{ opacity: 0; transform: translateY(8px); }}
    to {{ opacity: 1; transform: translateY(0); }}
}}
.category {{
    animation: fadeIn 0.3s ease;
}}

/* Scroll to top */
.scroll-top {{
    position: fixed;
    bottom: 24px;
    right: 24px;
    width: 40px;
    height: 40px;
    background: var(--primary);
    color: white;
    border: none;
    border-radius: 50%;
    cursor: pointer;
    box-shadow: var(--shadow-md);
    display: none;
    align-items: center;
    justify-content: center;
    font-size: 16px;
    transition: all 0.2s;
    z-index: 99;
}}
.scroll-top:hover {{
    background: var(--primary-dark);
    transform: translateY(-2px);
}}

/* Responsive */
@media (max-width: 900px) {{
    .container {{ flex-direction: column; }}
    .sidebar {{ display: none; }}
    .header {{ padding: 20px; }}
}}
</style>
</head>
<body>

<div class="header">
    <h1><i class="fas fa-cubes"></i> CST Solver Python API 文档</h1>
    <p>cst_solver 包 — 基于 Mixin 多继承模式的 CST Studio Suite 自动化 Python 接口</p>
    <div class="header-stats">
        <span><i class="fas fa-code"></i> {total_methods} 个方法</span>
        <span><i class="fas fa-layer-group"></i> {total_categories} 个类别</span>
        <span><i class="fas fa-file-alt"></i> 生成时间: {gen_time}</span>
    </div>
    <div class="search-bar">
        <i class="fas fa-search"></i>
        <input type="text" id="search" placeholder="搜索方法名、参数、描述..." oninput="filterMethods()">
    </div>
</div>

<div class="container">
    <nav class="sidebar" id="sidebar">
        <h3>目录</h3>
        {sidebar_links}
    </nav>

    <div class="main-content" id="mainContent">
        {category_sections}
        <div class="no-results" id="noResults">
            <i class="fas fa-search"></i>
            <h3>未找到匹配结果</h3>
            <p>尝试使用其他关键词搜索</p>
        </div>
    </div>
</div>

<button class="scroll-top" id="scrollTop" onclick="window.scrollTo({{top:0,behavior:'smooth'}})">
    <i class="fas fa-arrow-up"></i>
</button>

<script>
// Show/hide scroll to top button
window.addEventListener('scroll', function() {{
    const btn = document.getElementById('scrollTop');
    btn.style.display = window.scrollY > 300 ? 'flex' : 'none';
}});

// Toggle method details
function toggleMethod(header) {{
    const card = header.closest('.method-card');
    const details = card.querySelector('.method-details');
    const icon = header.querySelector('.expand-icon');
    details.classList.toggle('open');
    icon.classList.toggle('open');
}}

// Close all open method details
function closeAllMethods() {{
    document.querySelectorAll('.method-details.open').forEach(d => d.classList.remove('open'));
    document.querySelectorAll('.expand-icon.open').forEach(i => i.classList.remove('open'));
}}

// Search/filter
function filterMethods() {{
    const q = document.getElementById('search').value.toLowerCase().trim();
    const cards = document.querySelectorAll('.method-card');
    const categories = document.querySelectorAll('.category');
    const noResults = document.getElementById('noResults');
    let anyVisible = false;

    cards.forEach(card => {{
        const text = card.textContent.toLowerCase();
        const match = !q || text.includes(q);
        card.style.display = match ? '' : 'none';
        if (match) anyVisible = true;
    }});

    categories.forEach(cat => {{
        const visibleCards = cat.querySelectorAll('.method-card[style*="display: none"]');
        const totalCards = cat.querySelectorAll('.method-card').length;
        const allHidden = visibleCards.length === totalCards;
        cat.style.display = allHidden && q ? 'none' : '';
        if (!allHidden && q) anyVisible = true;
    }});

    noResults.style.display = anyVisible ? 'none' : 'block';
    closeAllMethods();
}}

// Keyboard shortcut: Ctrl+F focuses search
document.addEventListener('keydown', function(e) {{
    if ((e.ctrlKey || e.metaKey) && e.key === 'f') {{
        document.getElementById('search').focus();
        e.preventDefault();
    }}
}});
</script>
</body>
</html>"""


# ============================================================
# 方法信息提取
# ============================================================

def get_class_source_file(cls):
    """
    获取类定义所在的源文件路径（相对于 cst_solver/）
    """
    try:
        filepath = inspect.getfile(cls)
        relpath = os.path.relpath(filepath, str(CST_SOLVER_DIR.parent))
        return relpath
    except (TypeError, OSError):
        return "unknown"


def parse_docstring(doc):
    """
    解析 docstring，返回 (short_desc, params, returns, full_desc)
    """
    if not doc:
        return "", [], "", ""

    lines = textwrap.dedent(doc).strip().split("\n")
    short_desc = lines[0] if lines else ""

    params = []
    returns = ""
    desc_lines = []
    in_params = False
    in_returns = False

    for line in lines[1:]:
        stripped = line.strip()

        if stripped.startswith(":param "):
            in_params = True
            in_returns = False
            # :param name: type, desc 或 :param name: desc
            rest = stripped[7:]
            parts = rest.split(":", 1)
            name = parts[0].strip()
            desc = parts[1].strip() if len(parts) > 1 else ""
            # 检查是否有类型标注
            param_type = ""
            if "," in name:
                name = name.split(",")[0].strip()
            params.append({"name": name, "type": param_type, "desc": desc})
            continue

        if stripped.startswith(":return:"):
            in_returns = True
            in_params = False
            returns = stripped[8:].strip()
            continue

        if stripped.startswith(":raises") or stripped.startswith(":raise"):
            in_params = False
            in_returns = False
            continue

        if stripped.startswith(":type ") or stripped.startswith(":param-type"):
            continue

        if in_params:
            # continuation of param desc
            if params:
                params[-1]["desc"] += " " + stripped
            continue

        if in_returns:
            returns += " " + stripped
            continue

        if stripped:
            desc_lines.append(stripped)

    full_desc = "\n".join(desc_lines).strip()
    return short_desc, params, returns, full_desc


def get_methods_from_mixin(mixin_cls, category_name, source_file):
    """
    从 Mixin 类中提取所有公开方法的信息
    """
    methods = []
    seen = set()

    for name, method in inspect.getmembers(mixin_cls, inspect.isfunction):
        if name.startswith("_"):
            continue  # 跳过私有/魔术方法

        if name in seen:
            continue
        seen.add(name)

        try:
            sig = inspect.signature(method)
        except (ValueError, TypeError):
            sig = ""

        doc = inspect.getdoc(method) or ""
        short_desc, params, returns, full_desc = parse_docstring(doc)

        # 从签名提取参数类型信息
        sig_params = []
        for p_name, p in sig.parameters.items():
            if p_name == "self":
                continue
            p_type = ""
            if p.annotation is not inspect.Parameter.empty:
                p_type = str(p.annotation).replace("<class '", "").replace("'>", "")
            p_default = ""
            if p.default is not inspect.Parameter.empty:
                p_default = str(p.default)
            sig_params.append({
                "name": p_name,
                "type": p_type,
                "default": p_default,
            })

        # 合并 docstring 中的参数描述
        doc_params_dict = {p["name"]: p["desc"] for p in params}
        for sp in sig_params:
            if sp["name"] in doc_params_dict:
                sp["desc"] = doc_params_dict[sp["name"]]
            else:
                sp["desc"] = ""

        # 是否是别名方法
        is_alias = name in ALIAS_MAP

        methods.append({
            "name": name,
            "signature": str(sig),
            "short_desc": short_desc,
            "full_desc": full_desc,
            "params": sig_params,
            "returns": returns,
            "category": category_name,
            "source_file": source_file,
            "is_alias": is_alias,
            "alias_for": ALIAS_MAP.get(name, ""),
        })

    return methods


def scrape_package():
    """
    扫描 cst_solver 包，提取所有 Mixin 类中的方法信息
    """
    import cst_solver
    import cst_solver.project
    import cst_solver.units
    import cst_solver.parameters
    import cst_solver.modeling.primitives
    import cst_solver.modeling.curves
    import cst_solver.modeling.curves_ops
    import cst_solver.modeling.wcs
    import cst_solver.modeling.booleans
    import cst_solver.modeling.transforms
    import cst_solver.modeling.picks
    import cst_solver.material.materials
    import cst_solver.simulation.ports
    import cst_solver.simulation.sources
    import cst_solver.simulation.monitors
    import cst_solver.simulation.boundary
    import cst_solver.simulation.solver
    import cst_solver.mesh.mesh
    import cst_solver.import_export.io
    import cst_solver.postprocessing.proc
    import cst_solver.postprocessing.farfield
    import cst_solver.postprocessing.plot
    import cst_solver.postprocessing.result_export

    all_methods = []

    modules = [
        ("ProjectMixin", cst_solver.project, cst_solver.project.ProjectMixin),
        ("UnitsMixin", cst_solver.units, cst_solver.units.UnitsMixin),
        ("ParametersMixin", cst_solver.parameters, cst_solver.parameters.ParametersMixin),
        ("ModelingPrimitivesMixin", cst_solver.modeling.primitives, cst_solver.modeling.primitives.ModelingPrimitivesMixin),
        ("CurvesMixin", cst_solver.modeling.curves, cst_solver.modeling.curves.CurvesMixin),
        ("CurveOpsMixin", cst_solver.modeling.curves_ops, cst_solver.modeling.curves_ops.CurveOpsMixin),
        ("WCSMixin", cst_solver.modeling.wcs, cst_solver.modeling.wcs.WCSMixin),
        ("SolidOpsMixin", cst_solver.modeling.booleans, cst_solver.modeling.booleans.SolidOpsMixin),
        ("TransformMixin", cst_solver.modeling.transforms, cst_solver.modeling.transforms.TransformMixin),
        ("PickMixin", cst_solver.modeling.picks, cst_solver.modeling.picks.PickMixin),
        ("FaceOpsMixin", cst_solver, cst_solver.FaceOpsMixin),  # FaceOpsMixin is in __init__.py
        ("MaterialMixin", cst_solver.material.materials, cst_solver.material.materials.MaterialMixin),
        ("PortMixin", cst_solver.simulation.ports, cst_solver.simulation.ports.PortMixin),
        ("SourceMixin", cst_solver.simulation.sources, cst_solver.simulation.sources.SourceMixin),
        ("MonitorMixin", cst_solver.simulation.monitors, cst_solver.simulation.monitors.MonitorMixin),
        ("BoundaryMixin", cst_solver.simulation.boundary, cst_solver.simulation.boundary.BoundaryMixin),
        ("SolverMixin", cst_solver.simulation.solver, cst_solver.simulation.solver.SolverMixin),
        ("MeshMixin", cst_solver.mesh.mesh, cst_solver.mesh.mesh.MeshMixin),
        ("IOMixin", cst_solver.import_export.io, cst_solver.import_export.io.IOMixin),
        ("PostProcMixin", cst_solver.postprocessing.proc, cst_solver.postprocessing.proc.PostProcMixin),
        ("FarfieldMixin", cst_solver.postprocessing.farfield, cst_solver.postprocessing.farfield.FarfieldMixin),
        ("PlotMixin", cst_solver.postprocessing.plot, cst_solver.postprocessing.plot.PlotMixin),
        ("ExportMixin", cst_solver.postprocessing.result_export, cst_solver.postprocessing.result_export.ExportMixin),
    ]

    for mixin_name, module, cls in modules:
        if cls is None:
            continue

        cat = CATEGORIES.get(mixin_name, mixin_name)
        src = get_class_source_file(cls)
        methods = get_methods_from_mixin(cls, cat, src)
        all_methods.extend(methods)

    # 去重（某些方法可能在多个 mixin 中出现）
    seen = set()
    unique = []
    for m in all_methods:
        if m["name"] not in seen:
            seen.add(m["name"])
            unique.append(m)

    return unique


# ============================================================
# HTML 生成
# ============================================================

def escape_html(text):
    """HTML 转义"""
    text = str(text)
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


def format_type_default(type_str, default_str):
    """格式化参数类型和默认值"""
    parts = []
    if type_str:
        parts.append(f'<span class="param-type">{escape_html(type_str)}</span>')
    if default_str:
        parts.append(f'<span style="color:#f59e0b;font-size:12px">= {escape_html(default_str)}</span>')
    return " ".join(parts)


def build_category_sections(all_methods):
    """
    构建所有类别区块的 HTML
    """
    # 按类别分组
    by_category = {}
    for m in all_methods:
        cat = m["category"]
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(m)

    sections_html = ""
    sidebar_html = ""

    icons = {
        cat: CATEGORY_ICONS.get(cat, "code")
        for cat in by_category
    }

    cat_colors = [
        "#2563eb", "#7c3aed", "#db2777", "#dc2626", "#ea580c",
        "#ca8a04", "#16a34a", "#0891b2", "#4f46e5", "#9333ea",
        "#c026d3", "#e11d48", "#0d9488", "#2563eb", "#65a30d",
        "#0ea5e9", "#8b5cf6", "#d946ef", "#f97316", "#22c55e",
    ]

    for idx, (cat, methods) in enumerate(sorted(by_category.items(), key=lambda x: len(x[1]), reverse=True)):
        color = cat_colors[idx % len(cat_colors)]
        icon = icons.get(cat, "code")
        alias_count = sum(1 for m in methods if m["is_alias"])
        primary_count = len(methods) - alias_count

        anchor = f"cat-{idx}"
        sidebar_html += (
            f'<a href="#{anchor}" onclick="document.getElementById(\'search\').value=\'\';filterMethods();setTimeout(()=>{{document.querySelector(\'#{anchor}\')?.scrollIntoView({{behavior:\'smooth\',block:\'start\'}});window.scrollBy(0,-80);}},50)">'
            f'<i class="fas fa-{icon}"></i>{cat}</a>\n'
        )

        methods_html = ""
        for m in methods:
            alias_badge = ""
            if m["is_alias"]:
                alias_badge = '<span class="badge" style="background:#fffbeb;color:#92400e;border:1px solid #fde68a">别名</span>'
            else:
                alias_badge = '<span class="badge">方法</span>'

            # 构建参数表
            params_html = ""
            if m["params"]:
                rows = ""
                for p in m["params"]:
                    pname = escape_html(p["name"])
                    ptype = format_type_default(p["type"], p["default"])
                    pdesc = escape_html(p.get("desc", ""))
                    rows += f'<tr><td class="param-name">{pname}</td><td>{ptype}</td><td class="param-desc">{pdesc}</td></tr>\n'
                params_html = f"""
                <div class="section">
                    <div class="section-title">参数</div>
                    <table class="params-table">
                        <thead><tr><th>名称</th><th>类型/默认值</th><th>说明</th></tr></thead>
                        <tbody>{rows}</tbody>
                    </table>
                </div>
                """

            # 返回值
            returns_html = ""
            if m["returns"]:
                returns_html = f"""
                <div class="section">
                    <div class="section-title">返回值</div>
                    <div class="return-section">{escape_html(m["returns"])}</div>
                </div>
                """

            # 描述
            desc_html = ""
            if m["short_desc"]:
                desc_html = f'<div class="desc-text"><p>{escape_html(m["short_desc"])}</p>'
                if m["full_desc"]:
                    desc_html += f'<p>{escape_html(m["full_desc"])}</p>'
                desc_html += "</div>"

            # 别名信息
            alias_html = ""
            if m["is_alias"] and m["alias_for"]:
                alias_html = f"""
                <div class="alias-info">
                    <i class="fas fa-info-circle"></i>
                    此函数是 <strong>{escape_html(m["alias_for"])}</strong> 的别名，保留以兼容旧代码。
                </div>
                """

            name_class = "name alias" if m["is_alias"] else "name"
            methods_html += f"""
            <div class="method-card">
                <div class="method-card-header" onclick="toggleMethod(this)">
                    <span class="{name_class}">{escape_html(m["name"])}</span>
                    {alias_badge}
                    <span class="desc">{escape_html(m["short_desc"][:80])}</span>
                    <span class="expand-icon"><i class="fas fa-chevron-right"></i></span>
                </div>
                <div class="method-details">
                    <div class="section">
                        <div class="section-title">签名</div>
                        <div class="signature">{escape_html(m["name"])}{escape_html(m["signature"])}</div>
                    </div>
                    {desc_html}
                    {alias_html}
                    {params_html}
                    {returns_html}
                    <div class="source-file">
                        源文件: <code>{escape_html(m["source_file"])}</code>
                    </div>
                </div>
            </div>
            """

        sections_html += f"""
        <div class="category" id="{anchor}">
            <div class="category-header" onclick="this.nextElementSibling.nextElementSibling.querySelector('input')?.focus()">
                <div class="icon" style="background:{color}"><i class="fas fa-{icon}"></i></div>
                <h2>{escape_html(cat)}</h2>
                <span class="count">{primary_count} 方法{alias_count and f' + {alias_count} 别名' or ''}</span>
            </div>
            {methods_html}
        </div>
        """

    return sections_html, sidebar_html


def generate():
    """
    主函数：扫描包并生成 HTML 文档
    """
    os.makedirs(str(OUTPUT_DIR), exist_ok=True)

    print("🔍 正在扫描 cst_solver 包...")
    all_methods = scrape_package()
    print(f"   找到 {len(all_methods)} 个方法")

    print("📝 正在生成 HTML...")
    sections, sidebar = build_category_sections(all_methods)

    from datetime import datetime
    gen_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    html = HTML_TEMPLATE.format(
        total_methods=len(all_methods),
        total_categories=len(CATEGORIES),
        gen_time=gen_time,
        sidebar_links=sidebar,
        category_sections=sections,
    )

    with open(str(OUTPUT_FILE), "w", encoding="utf-8") as f:
        f.write(html)

    file_size = os.path.getsize(str(OUTPUT_FILE)) / 1024
    print(f"✅ 文档已生成: {OUTPUT_FILE}")
    print(f"   文件大小: {file_size:.1f} KB")
    print(f"   包含 {len(all_methods)} 个方法，{len(CATEGORIES)} 个类别")


if __name__ == "__main__":
    generate()
