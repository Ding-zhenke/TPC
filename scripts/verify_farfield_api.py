# -*- coding: utf-8 -*-
"""真机回归：通过 cst_solver 新接口（attach/read/metrics/export/pattern_export）
验证远场读取与导出。不新建 DE（复用现有许可证）、不求解、不关闭 DE。"""
import os

import numpy as np

from cst_solver import setup

CST = r"D:\成电博士生涯\拓扑光子晶体模型\硅基\Leaky\ANT_LEAKY_EPC_GRID.cst"
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "docs", "next_plan", "farfield_regression")
os.makedirs(OUT, exist_ok=True)

app = setup.attach(pid=36472)
if app.cst_file is None or app.cst_file.filename() != CST:
    app.open(CST)
print("attach + 打开完成:", app.cst_file.filename())

# 1) 物理指标（f=314, step=1）
m = app.get_farfield_metrics("farfield (f=314) [1]", step=1.0)
print("\n[get_farfield_metrics f=314]")
print("  gain_max       =", round(m["gain_max"], 3), "dBi  (参考 10.509)")
print("  main_lobe θ/φ  =", round(m["main_lobe_theta"], 2),
      round(m["main_lobe_phi"], 2), " (参考 θ90/φ≈126.8)")

# 2) 完整读取
data = app.read_farfield("farfield (f=314) [1]", step=1.0)
i, j = np.unravel_index(np.argmax(data["gain"]), data["gain"].shape)
print("\n[read_farfield step=1]")
print("  网格 (nθ,nφ) =", data["gain"].shape)
print("  grid max     =", round(float(data["gain"][i, j]), 3),
      "dBi @ θ", data["theta"][i], "φ", data["phi"][j])

# 3) CSV 导出
csv_path = os.path.join(OUT, "farfield_314_step1.csv")
app.export_farfield_csv("farfield (f=314) [1]", csv_path, step=1.0)
print("\n[export_farfield_csv]", csv_path, os.path.getsize(csv_path), "bytes")

# 4) pattern_export（旧接口，step 修复回归）
pat_path = os.path.join(OUT, "pattern_314_ascii.txt")
app.pattern_export("farfield (f=314) [1]", pat_path, step=1.0)
print("[pattern_export]", pat_path, os.path.getsize(pat_path), "bytes")

# 5) 验收判据
err_g = abs(m["gain_max"] - 10.509)
dphi = abs(((m["main_lobe_phi"] - 126.76 + 180) % 360) - 180)
print("\n=== 验收 ===")
print(f"  增益误差 {err_g:.3f} dB  主瓣方向偏差 {dphi:.2f}°（<5°）")
assert err_g < 0.05 and dphi < 5.0
print("  PASS")
print("\nDE 保持打开不动")
