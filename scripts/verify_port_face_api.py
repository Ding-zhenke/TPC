# -*- coding: utf-8 -*-
"""
B0 事实核验：端口 Free 模式 与 面编号反查
=========================================

用途：在**装有 CST 的机器上**跑一次，逐项打印观测结果。
本脚本只做事实核验，不改库代码；结论需回填 ``docs/next_plan/``。

要核验的三件事
--------------
V2  ``Coordinates "Free"`` + ``Xrange/Yrange/Zrange`` 能否建出端口
    —— 决定"零拾取端口"方案是否成立。
V3  ``model3d.Pick`` 是否暴露；``GetFaceIdFromPoint`` /
    ``GetNumberOfPickedFaces`` 能否把值返回给 Python
    —— 决定 ``get_face_id_from_point()`` / ``get_picked_count()`` 是否可用。
V4  反查得到的面编号，喂回 ``pick_face()`` 后是否真的能选中面
    —— 决定"算点 → 反查 → 按编号拾取"这条链路能否闭环。

明确不在本脚本范围内
--------------------
V1  ``Port.Coordinates`` 的取值究竟认 ``"Picks"`` 还是 ``"Picked"``
    —— 按要求暂不核验。

用法
----
    python scripts/verify_port_face_api.py

注意
----
脚本使用 ``new_project()`` 新建**空白工程**，不打开、不修改任何既有工程。
核验结束会关闭工程与设计环境。
"""

import sys
import traceback
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 核验用实体：一个 1×1×1 的方块，坐标全部取整数，便于"点 → 面"心算核对
BOX = dict(x1=0, x2=1, y1=0, y2=1, z1=0, z2=1)
BOX_NAME = 'verify_box'
BOX_COMPONENT = 'component1'
# 上表面 (z=1) 的中心点
TOP_CENTER = (0.5, 0.5, 1.0)

_results = []
_app = None          # 模块级持有，供 __main__ 的 finally 统一清理


def record(item, status, detail):
    """记录一条核验结果。status 取 OK / FAIL / UNKNOWN。"""
    _results.append((item, status, detail))
    print(f'[{status:7s}] {item}')
    print(f'          {detail}')


def drain(app, label):
    """读取并清空 CST 消息（读后即清空），返回非空则说明有报错。"""
    msgs = app.cst_file.get_messages()
    if msgs:
        text = str(msgs).strip()
        print(f'    · {label} 的 CST 消息：{text[:400]}')
        return text
    print(f'    · {label} 的 CST 消息：空')
    return ''


def main():
    from cst_solver import setup

    print('=' * 70)
    print('B0 事实核验：端口 Free 模式 与 面编号反查')
    print('=' * 70)

    # ---- 建空白工程 + 一个方块 ----
    global _app
    app = setup()                 # 只初始化设计环境，不打开既有工程
    _app = app                    # 交给 __main__ 的 finally 清理
    app.new_project()             # 新建空白工程，避免污染任何正式工程

    app.square(BOX['x1'], BOX['x2'], BOX['y1'], BOX['y2'],
               BOX['z1'], BOX['z2'], BOX_NAME, BOX_COMPONENT, 'PEC')
    if drain(app, f'建方块 {BOX_NAME}'):
        record('前置：建方块', 'FAIL', '建方块就有报错，后续结论不可信')
        return

    # ================= V3 =================
    print('\n--- V3：model3d.Pick 是否暴露、能否返回值 ---')

    pick_obj = None
    try:
        pick_obj = app.cst_file.model3d.Pick
        record('V3.1 model3d.Pick 可用性', 'OK',
               f'已取到 Pick 对象：{type(pick_obj)!r}')
    except AttributeError as exc:
        record('V3.1 model3d.Pick 可用性', 'FAIL',
               f'model3d 未暴露 Pick（{exc}）。'
               f'→ get_face_id_from_point / get_picked_count 会抛 RuntimeError，'
               f'只能退回按坐标拾取 pick_face_at()')
    except Exception as exc:
        record('V3.1 model3d.Pick 可用性', 'UNKNOWN',
               f'取值时抛出非 AttributeError 异常：{exc!r}')

    # 库内的封装接口
    try:
        fid = app.get_face_id_from_point(BOX_NAME, *TOP_CENTER)
        if isinstance(fid, int):
            record('V3.2 get_face_id_from_point() 返回值', 'OK',
                   f'上表面中心 {TOP_CENTER} → 面编号 {fid}（类型 int）')
        elif fid is None:
            record('V3.2 get_face_id_from_point() 返回值', 'FAIL',
                   '返回 None —— 说明调用抛了异常被库内 except 吞掉，'
                   '需在 get_face_id_from_point 里临时打印异常定位')
        else:
            record('V3.2 get_face_id_from_point() 返回值', 'UNKNOWN',
                   f'返回非 int 也非 None：{fid!r}（类型 {type(fid).__name__}）')
    except Exception as exc:
        record('V3.2 get_face_id_from_point() 返回值', 'FAIL',
               f'抛出异常：{exc!r}\n{traceback.format_exc(limit=3)}')

    try:
        n_before = app.get_picked_count('face')
        record('V3.3 get_picked_count() 返回值', 'OK',
               f'未拾取时 get_picked_count("face") = {n_before!r}')
    except Exception as exc:
        record('V3.3 get_picked_count() 返回值', 'FAIL', f'抛出异常：{exc!r}')

    for bad_kind in ('face ', 'bogus'):
        try:
            app.get_picked_count(bad_kind)
            record(f'V3.4 kind 非法值 {bad_kind!r}', 'UNKNOWN',
                   '未抛 ValueError（文档声明应抛）')
        except ValueError:
            record(f'V3.4 kind 非法值 {bad_kind!r}', 'OK', '按文档抛出 ValueError')
        except Exception as exc:
            record(f'V3.4 kind 非法值 {bad_kind!r}', 'UNKNOWN',
                   f'抛的不是 ValueError 而是 {type(exc).__name__}：{exc!r}')
        break   # 只测一个非法值即可

    # ================= V4 =================
    print('\n--- V4：反查出的编号喂回 pick_face 能否闭环 ---')

    app.pick_clear()
    drain(app, 'pick_clear')
    try:
        fid2 = app.get_face_id_from_point(BOX_NAME, *TOP_CENTER)
    except Exception as exc:
        fid2 = None
        print(f'    · 反查失败：{exc!r}')

    if fid2 is None:
        record('V4 反查编号 → pick_face 闭环', 'FAIL',
               '反查未拿到编号，本项无法继续（先解决 V3.2）')
    else:
        app.pick_face(BOX_NAME, fid2)
        msg = drain(app, f'pick_face({fid2})')
        try:
            n_after = app.get_picked_count('face')
        except Exception as exc:
            n_after = None
            print(f'    · get_picked_count 失败：{exc!r}')

        if msg:
            record('V4 反查编号 → pick_face 闭环', 'FAIL',
                   f'按反查编号拾取后 CST 有报错 → 编号不可用（反查不可信）')
        elif n_after == 1:
            record('V4 反查编号 → pick_face 闭环', 'OK',
                   f'反查编号 {fid2} 喂回 pick_face 后已选面数 = 1，链路闭环')
        else:
            record('V4 反查编号 → pick_face 闭环', 'UNKNOWN',
                   f'无报错但已选面数为 {n_after!r}（期望 1），需人工判定')

    # ================= V2 =================
    print('\n--- V2：Coordinates "Free" + 坐标范围能否建出端口 ---')

    app.pick_clear()
    drain(app, 'pick_clear（建 Free 端口前）')
    try:
        app.create_waveguide_port_free(
            1, xrange=(BOX['x1'], BOX['x2']), yrange=(BOX['y1'], BOX['y2']))
        msg = drain(app, 'create_waveguide_port_free(1, xrange, yrange)')
        if msg:
            record('V2 Free 模式建端口', 'FAIL',
                   f'CST 有报错 → Free 模式方案不成立，需核对 Xrange/Yrange 写法与 Orientation 取值')
        else:
            record('V2 Free 模式建端口', 'OK',
                   '无报错。仍需人工确认：端口是否落在 z=1（或 z=0）面上、'
                   '形状尺寸是否等于给定范围')
    except Exception as exc:
        record('V2 Free 模式建端口', 'FAIL',
               f'抛出异常：{exc!r}\n{traceback.format_exc(limit=3)}')

    # 与"按拾取建端口"的现有链路做对照（同一次会话内）
    print('\n--- 对照：现有 Picks 链路（仅作基线，不判定 Picks/Picked 拼写）---')
    try:
        app.pick_clear()
        drain(app, 'pick_clear（建 Picks 端口前）')
        fid3 = app.get_face_id_from_point(BOX_NAME, *TOP_CENTER)
        if fid3 is not None:
            app.pick_face(BOX_NAME, fid3)
            drain(app, f'pick_face({fid3})')
        app.add_port(2)
        msg = drain(app, 'add_port(2)（Picks 链路）')
        record('对照 Picks 链路可用性', 'OK' if not msg else 'FAIL',
               '无报错' if not msg else '有报错 —— 现有端口链路本身可能不工作，'
                                        '这会让 V2 的对照失去意义')
    except Exception as exc:
        record('对照 Picks 链路可用性', 'FAIL', f'抛出异常：{exc!r}')

    # ================= 重放验收 =================
    print('\n--- 历史树重放（最能暴露问题的验收动作）---')
    try:
        app.cst_file.model3d.Rebuild()
        msg = drain(app, 'Rebuild()')
        record('Rebuild() 重放', 'OK' if not msg else 'FAIL',
               '历史树无错重放' if not msg else '重放有报错 —— 上述命令拼写或顺序有问题')
    except Exception as exc:
        record('Rebuild() 重放', 'FAIL', f'抛出异常：{exc!r}')

    # ================= 汇总 =================
    print('\n' + '=' * 70)
    print('汇总')
    print('=' * 70)
    for item, status, _ in _results:
        print(f'  {status:7s}  {item}')
    print('\n请把以上完整输出贴回，据此定稿后续实现。')
    print('判定要点：')
    print('  · V3.1 FAIL   → 反查编号这条路走不通，只能放弃 get_face_id_from_point')
    print('  · V2 OK       → §6.3 可以定为"轴对齐面用 Free 范围"')
    print('  · V4 OK       → 非轴对齐面可走"算点 → 反查 → 拾取"')
    print('  · Rebuild FAIL→ 上述 VBA 拼写必须修正后才能入库')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        traceback.print_exc()
    finally:
        # 清理：关闭工程与设计环境，避免留下悬挂的 CST 进程
        if _app is not None:
            try:
                _app.close()
                print('\n工程与设计环境已关闭。')
            except Exception as exc:
                print(f'\n关闭工程/设计环境时出错：{exc!r}')
