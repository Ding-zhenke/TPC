---
name: cst-solver-dev
description: '**维护 / 扩展 cst_solver 库** —— 为 CST Studio Suite 的 VBA API 增加 Python 封装、修封装层缺陷、统一 Mixin/命名/docstring 规范、重新生成 API 文档。USE FOR: 新增 app.xxx() 方法；修 cst_solver/ 内部 bug；核对 VBA 命令与 CST 帮助；更新 setup.pyi 存根与 docs。DO NOT USE FOR: 用 TPC 库建电磁模型 —— 那属于使用视角，读 ../../skills/user/tpc-usage.md。'
argument-hint: 描述要新增/修复的 CST VBA 功能（如「增加 EigenmodeSolver 的 … 封装」）
---

# cst_solver 库开发与维护

> **本文件是薄壳。完整内容在
> [`../../skills/developer/cst-solver-dev.md`](../../../skills/developer/cst-solver-dev.md)。**
> 开发前请先读 [`../../skills/developer/WORKFLOW.md`](../../../skills/developer/WORKFLOW.md)（开发宪法）。

**请现在就去读这两个文件**，本薄壳只保留最重要的几条，避免规则漂移：

## 不可违反的硬约定

1. `add_to_history` 是唯一执行通道；`log_flag=0` 时只拼字符串不下发
   （复合命令靠这个拼成**一条**历史）。
2. 失败有**两条通道**：`add_to_history()` 可能**直接抛 Python 异常**，也可能**只写消息**
   → 验收两条都要看：接异常 + 读 `app.cst_file.get_messages()`，
   并跑 `cst_file.model3d.Rebuild()` 阻塞式重放历史。
   ⚠️ `get_messages()` **不是「读一次就清空」**：历史里的失败会**反复报出**，
   在脏工程里「消息为空 = 成功」会一直判失败 —— 优先用**正向信号**
   （已选面数、实体存在性、结果指纹），取不到才退回消息判定。
3. `ExtrudeCurve` 沿多边形**法向**拉伸，法向由顶点**绕向**决定：
   **CCW(有向面积>0) → +z，CW → −z**。库内统一「多边形给 CCW + `translate -h/2`」。
4. 布尔语义：`Intersect "A","B"` → 结果留 A、B 被消耗；
   `Add/Subtract "A","B"` → 结果在 A、**B 被删除**；`Insert` 保留 B。
5. `cst_file.modeler` 已废弃 → 用 `cst_file.model3d`。
6. 新方法用 `snake_case` + 保留旧 VBA 名作为**别名**；改 API 必须同步 `cst_solver/setup.pyi`。
7. 相对路径按**当前工作目录**解析（模板 `tmp.cst` 必须放 notebook 同目录）。
8. **真机脚本必须检测 CST 弹窗**：模态对话框（未定义参数→「请输入变量值」、
   关项目/退出→「是否保存更改？」）**不抛异常也不写消息**，只会让下一次 CST 调用
   **永久阻塞**。能离线预检的先预检，建/关 DE 前后打窗口快照，重步骤套超时看门狗 ——
   工具是 `scripts/cst_dialog_guard.py`（`Get-Process.MainWindowTitle` 看不到对话框）。

## 相关的其它文件

- 使用视角（建模型、排错、验收）→ [`../../skills/user/tpc-usage.md`](../../../skills/user/tpc-usage.md)
- 栅格算法细节 → [`../../skills/user/tri-grid.md`](../../../skills/user/tri-grid.md)、
  [`../../skills/user/hex-grid.md`](../../../skills/user/hex-grid.md)
- 包结构总览 → [`../../docs/ARCHITECTURE.md`](../../../docs/ARCHITECTURE.md)
