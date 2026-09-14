# -*- coding: utf-8 -*-
"""
mesh_grid API 文档生成器
=========================
从源代码的 docstring 中提取文档，生成 HTML 格式的 API 文档。

用法:
    python scripts/gen_mesh_docs.py

输出:
    docs/guides/api/hex_grid_api.html
    docs/guides/api/tri_grid_api.html

@author: PC
"""
import os
import sys
import inspect
import importlib
import html

# 确保项目根目录在路径中（本脚本位于 <root>/scripts/）
_script_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.abspath(os.path.join(_script_dir, ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


def extract_doc_from_module(module_name):
    """导入模块并提取所有公开函数/类的文档"""
    module = importlib.import_module(module_name)

    # 获取模块文档字符串
    module_doc = module.__doc__ or ""

    items = []
    for name, obj in inspect.getmembers(module):
        if name.startswith("_"):
            continue
        if inspect.isclass(obj) or inspect.isfunction(obj):
            doc = inspect.getdoc(obj) or ""
            # 获取签名
            try:
                sig = str(inspect.signature(obj))
            except (ValueError, TypeError):
                sig = "(...)"
            items.append({
                "name": name,
                "type": "class" if inspect.isclass(obj) else "function",
                "signature": f"{name}{sig}",
                "doc": doc,
            })
    return module_doc, sorted(items, key=lambda x: x["name"])


def render_html(title, module_doc, items, css=""):
    """渲染为 HTML 页面"""
    if not css:
        css = """
        body { font-family: 'Segoe UI', Arial, sans-serif; max-width: 960px;
               margin: 0 auto; padding: 20px; color: #333; line-height: 1.6; }
        h1 { color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; }
        h2 { color: #2980b9; margin-top: 30px; }
        .module-doc { background: #f8f9fa; padding: 15px; border-radius: 5px;
                      margin: 20px 0; border-left: 4px solid #3498db; }
        .item { background: #fff; border: 1px solid #ddd; border-radius: 5px;
                margin: 12px 0; padding: 15px; }
        .item:hover { box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
        .item-header { display: flex; align-items: baseline; gap: 10px; }
        .item-name { font-family: 'Consolas', monospace; font-size: 14px;
                     font-weight: bold; color: #2c3e50; }
        .item-type { font-size: 11px; padding: 2px 8px; border-radius: 3px;
                     color: #fff; }
        .type-class { background: #e74c3c; }
        .type-function { background: #27ae60; }
        .item-signature { font-family: 'Consolas', monospace; font-size: 13px;
                          color: #7f8c8d; margin: 5px 0; }
        .item-doc { margin-top: 8px; font-size: 14px; white-space: pre-wrap; }
        .summary { background: #eaf2f8; padding: 15px; border-radius: 5px;
                   margin: 20px 0; }
        .summary a { color: #2980b9; text-decoration: none; }
        .summary a:hover { text-decoration: underline; }
        table { width: 100%; border-collapse: collapse; margin: 10px 0; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background: #3498db; color: #fff; }
        tr:nth-child(even) { background: #f2f2f2; }
        footer { margin-top: 40px; color: #95a5a6; font-size: 12px;
                 text-align: center; border-top: 1px solid #ecf0f1;
                 padding-top: 10px; }
        .nav { position: sticky; top: 0; background: #fff; padding: 10px 0;
               border-bottom: 1px solid #ddd; margin-bottom: 20px; }
        .nav a { margin-right: 15px; }
        """

    # 构建表格行
    table_rows = []
    for item in items:
        icon = "📦" if item["type"] == "class" else "🔧"
        short_doc = item["doc"].split("\n")[0] if item["doc"] else ""
        table_rows.append(
            f"<tr><td>{icon}</td>"
            f"<td><a href='#{item['name']}'>{item['name']}</a></td>"
            f"<td>{short_doc}</td></tr>"
        )

    # 构建详细文档
    details = []
    for item in items:
        type_class = "type-class" if item["type"] == "class" else "type-function"
        doc_html = html.escape(item["doc"]).replace("\n", "<br>")
        # 将 docstring 中的 Args:/Returns: 等加粗
        doc_html = doc_html.replace("Args:", "<b>Args:</b>")
        doc_html = doc_html.replace("Returns:", "<b>Returns:</b>")
        doc_html = doc_html.replace("Raises:", "<b>Raises:</b>")
        doc_html = doc_html.replace("异常:", "<b>异常:</b>")
        doc_html = doc_html.replace("返回:", "<b>返回:</b>")
        doc_html = doc_html.replace("参数:", "<b>参数:</b>")
        doc_html = doc_html.replace("    - ", "&emsp;- ")

        details.append(f"""
        <div class="item" id="{item['name']}">
            <div class="item-header">
                <span class="item-name">{item['name']}</span>
                <span class="item-type {type_class}">{item['type']}</span>
            </div>
            <div class="item-signature">{html.escape(item['signature'])}</div>
            <div class="item-doc">{doc_html}</div>
        </div>
        """)

    # 构建完整 HTML
    quick_links = "".join(
        f"<a href='#{item['name']}'>{item['name']}</a>" for item in items
    )
    module_doc_html = html.escape(module_doc).replace("\n", "<br>")

    html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>{css}</style>
</head>
<body>
    <div class="nav">
        <strong>📖 {title}</strong> |
        {quick_links}
    </div>

    <h1>{title}</h1>

    <div class="module-doc">
        {module_doc_html}
    </div>

    <div class="summary">
        <h2>📋 API 总览</h2>
        <table>
            <tr><th>类型</th><th>名称</th><th>描述</th></tr>
            {''.join(table_rows)}
        </table>
        <p>共 <strong>{len(items)}</strong> 个公开符号</p>
    </div>

    <h2>📚 详细文档</h2>
    {''.join(details)}

    <footer>
        <p>自动生成于 {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
        <p>TPC Project — mesh_grid 文档</p>
    </footer>
</body>
</html>"""
    return html_content


def main():
    docs_dir = os.path.join(_project_root, "docs", "guides", "api")
    os.makedirs(docs_dir, exist_ok=True)

    # 生成 hex_grid API 文档
    print("正在生成 hex_grid API 文档...")
    module_doc, items = extract_doc_from_module("mesh_grid.hex_grid.core")
    html_content = render_html(
        "mesh_grid.hex_grid — 六边形网格 API 文档",
        module_doc, items
    )
    output_path = os.path.join(docs_dir, "hex_grid_api.html")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"✅ 已生成: {output_path}")

    # 生成 tri_grid API 文档
    print("正在生成 tri_grid API 文档...")
    module_doc, items = extract_doc_from_module("mesh_grid.tri_grid.core")
    html_content = render_html(
        "mesh_grid.tri_grid — 三角形网格 API 文档",
        module_doc, items
    )
    output_path = os.path.join(docs_dir, "tri_grid_api.html")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"✅ 已生成: {output_path}")

    print("\n🎉 文档生成完成！")


if __name__ == "__main__":
    main()
