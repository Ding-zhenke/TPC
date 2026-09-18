# -*- coding: utf-8 -*-
r"""
tpc-cst-mcp —— TPC 的 CST MCP 服务
==================================

把 Python 侧**已有的**能力暴露成 MCP 工具：AI 客户端按用户描述建模、仿真、
读结果、出报告。本包**不重写**几何、VBA 或数值逻辑（`cst_mcp.md` §2）：

* 契约与预检 → `topo_modeler.preflight`（P1）
* 执行与任务 → `tpc_service.RunService`（P2）
* 运行判定与单位口径 → `cst_solver.run_contract`（P1）
* S 参数曲线与报告 → `topo_modeler.result_reader` / `topo_modeler.report`

三层分工
--------
* :mod:`cst_mcp.tools` —— 纯函数式的工具实现（可离线单测，不依赖 MCP 协议）
* :mod:`cst_mcp.server` —— 协议装配（工具表 + 结构化结果 + stdout 隔离）
* :mod:`cst_mcp.runtime` —— 进程内单例：工作目录与 `RunService`

⚠️ 证据等级：本包目前只有**离线证据**（协议层用内存传输 + 假后端）。
真实 CST 上的端到端闭环属计划 P4/V9。
"""

__version__ = '0.1.0'

__all__ = ['__version__']
