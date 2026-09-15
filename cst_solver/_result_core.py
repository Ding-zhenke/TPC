# -*- coding: utf-8 -*-
"""
CST 仿真结果读取类
====================
封装 cst.results.ProjectFile，提供导航树结果查询和数据读取接口

@author: PC
"""

import csv
import numpy as np
import cst.results


# ============================================================
# 复数/单位量归一化
#
# CST 的 xdata/ydata 返回的是 Quantity / ComplexQuantity，直接参与比较会触发
# ``ComplexWarning: Casting complex values to real discards the imaginary part``
# （实测于阶段 4 T6，见 docs/next_plan/README.md §4.5）。
# 这里的三个小函数负责把它们统一压成 numpy 数组。
# ============================================================

def _as_real(value):
    """把标量/数组压成 float 数组（复数的实部）。"""
    arr = np.asarray(value)
    if np.iscomplexobj(arr):
        arr = arr.real
    return arr.astype(float, copy=False)


def _as_complex(value):
    """把标量/数组压成 complex 数组（实数会被提升）。"""
    return np.asarray(value).astype(complex, copy=False)


def _to_db(value):
    """
    |S| 转 dB。

    :param value: complex 标量/数组，注意**不是**已经取过对数的值
    :return: float 数组；幅度为 0 时取 -300 dB（与 scripts/compare_s_parameters.py 一致）
    """
    mag = np.abs(_as_complex(value))
    with np.errstate(divide='ignore'):
        db = 20.0 * np.log10(mag)
    return np.where(mag > 0, db, -300.0)


class Result:
    """
    CST 仿真结果读取类
    用于从已完成的 CST 仿真工程中读取 S 参数、场数据等结果

    ``cst.results.ProjectFile(...)`` 是**离线读取**：只要工程里已经存有仿真结果，
    不需要设计环境（DE）也能读出数据（阶段 4 T6 的对比脚本就是这样用的）。

    用法示例:
        >>> app_result = Result("path/to/project.cst")
        >>> s21 = app_result.read_1D("S-Parameters\\S2,1")
        >>> s11 = app_result.read_1D("S-Parameters\\S1,1", run_id=0)
        >>> all_s = app_result.read_all_s_parameters()
        >>> app_result.export_s_parameters_csv("s_params.csv")
    """

    def __init__(self, cst_file):
        """初始化结果读取器
        :param cst_file: str, CST 工程文件路径（.cst）
        """
        self.app_result = cst.results.ProjectFile(cst_file, allow_interactive=True)
        self.result_module = self.app_result.get_3d()
        #: 最近一次批量读取/导出中失败的条目 {名称: 错误字符串}。
        #: 批量接口不因为个别条目失败就整体抛异常（CST 的结果树常常缺项），
        #: 但失败的事实必须能被看到，所以留在这里而不是静默丢弃。
        self.last_errors = {}

    def get_tree_items(self, tree_filter=None):
        """
        列出导航树中的结果项

        :param tree_filter: str 可选, 结果类型过滤。官方接口支持
            ``"0D/1D"``（1D 曲线）/ ``"colormap"``（2D 云图）/
            ``"farfields"`` / ``"s-parameter-CC"`` 等；不传则返回全部
        :return: list, 结果路径字符串（部分 CST 版本返回 ResultItem，见 ``_tree_paths``）
        """
        if tree_filter:
            return self.result_module.get_tree_items(tree_filter)
        return self.result_module.get_tree_items()

    def get_available_results(self):
        """获取所有可用的结果项（中文别名）"""
        return self.get_tree_items()

    def get_all_run_ids(self, max_mesh_passes_only: bool = True):
        """获取所有已存在的仿真运行 ID
        :param max_mesh_passes_only: True-仅最终结果 False-含中间结果
        :return: list[int], 运行 ID 列表
        """
        return self.result_module.get_all_run_ids(max_mesh_passes_only)

    def get_run_ids(self, treepath: str, skip_nonparametric: bool = False):
        """获取指定导航树项目的所有运行 ID
        :param treepath: str, 导航树路径
        :param skip_nonparametric: True-排除 run_id=0
        :return: list[int], 运行 ID 列表
        """
        return self.result_module.get_run_ids(treepath, skip_nonparametric)

    def get_result_item(self, treepath: str, run_id=0, load_impedances: bool = True):
        """获取指定导航树路径的结果项对象
        :param treepath: str, 导航树路径
        :param run_id: int, 运行 ID（0=最终结果）
        :param load_impedances: False-跳过自动加载参考阻抗
        :return: cst.results.ResultItem
        """
        return self.result_module.get_result_item(treepath, run_id, load_impedances)

    def read_1D(self, tree_path, run_id: int = 0):
        """读取 1D 结果数据（如 S 参数）
        :param tree_path: str, 导航树路径（相对 "1D Results\\\\"）
        :param run_id: int, 运行 ID
        :return: ndarray (n,2) [xdata, ydata]
        """
        data = self.result_module.get_result_item("1D Results\\" + tree_path, run_id)
        return np.asarray([data.get_xdata(), data.get_ydata()]).T

    def read_2d(self, tree_path, run_id: int = 0):
        """读取 2D 结果数据"""
        data = self.result_module.get_result_item("2D Results\\" + tree_path, run_id)
        return {
            'x': data.get_xdata(), 'y': data.get_ydata(),
            'z': data.get_zdata() if hasattr(data, 'get_zdata') else None,
            'values': data.get_data()
        }

    def read_s_parameter(self, s_param: str, run_id: int = 0):
        """直接读取 S 参数（便捷方法）
        :param s_param: str, 如 'S1,1', 'S2,1'
        :return: ndarray (n,2) [频率, S参数值]
        """
        return self.read_1D(f"S-Parameters\\{s_param}", run_id)

    def read_3d(self, tree_path, run_id: int = 0):
        """读取 3D 结果数据（电场/磁场/功率损耗等）"""
        for prefix in ["2D/3D Results\\"]:
            try:
                full_path = prefix + tree_path
                data = self.result_module.get_result_item(full_path, run_id)
                return {
                    'x': data.get_xdata(), 'y': data.get_ydata(),
                    'z': data.get_zdata() if hasattr(data, 'get_zdata') else None,
                    'values': data.get_data()
                }
            except Exception:
                continue
        raise ValueError(f"无法读取 3D 结果: {tree_path}")

    # ================================================================
    # 批量读取与 CSV 导出（阶段 5.5）
    #
    # 设计要点：**纯离线**。只读工程里已存的结果文件，不打开设计环境，
    # 不写任何东西回工程 —— 因此可以在没有空闲许可/不想占算力时随便跑。
    #
    # ⚠️ 未验证风险：本机目前没有"已存结果可读"的工程，S 参数批量读取的
    # S-Parameters 树路径格式取自 scripts/compare_s_parameters.py 的实测用法，
    # 但**列表发现逻辑（list_s_parameters）与远场导出尚未在真实工程上跑过**。
    # 这是阶段 5 明确登记的未验证风险，不是"已验证"。
    # ================================================================

    def _tree_paths(self, tree_filter=None):
        """
        取出结果树里的所有路径字符串。

        官方文档写 ``get_tree_items()`` 返回 ``list[str]``，但同一份资料的另一处
        又说实测返回 ``list[ResultItem]``。这里两种都兼容：
        有 ``treepath`` 属性就用它，否则把元素本身当字符串。
        """
        try:
            items = self.get_tree_items(tree_filter)
        except Exception:
            if tree_filter is None:
                raise
            items = self.get_tree_items()
        out = []
        for it in items or ():
            path = getattr(it, 'treepath', None)
            out.append(str(path) if path is not None else str(it))
        return out

    def list_s_parameters(self, tree_filter='0D/1D'):
        """
        列出工程里所有可读的 S 参数名。

        :param tree_filter: str, 结果树过滤类型，默认 ``'0D/1D'``（1D 曲线）
        :return: list[str], 如 ``['S1,1', 'S2,1']``（已排序去重）
        """
        names = []
        for path in self._tree_paths(tree_filter):
            if 'S-Parameter' not in path:
                continue
            leaf = path.replace('\\', '/').rstrip('/').split('/')[-1].strip()
            # 跳过文件夹节点本身（叶子名就是分类名）
            if not leaf or leaf in ('S-Parameters', 'S-Parameter'):
                continue
            if leaf not in names:
                names.append(leaf)
        return sorted(names)

    def read_all_s_parameters(self, run_id: int = 0, names=None):
        """
        一次读回工程里所有 S 参数。

        个别条目读失败**不会**让整体抛异常（CST 结果树常常缺项，
        比如单端口器件就没有 S2,1）；失败项记在 ``self.last_errors`` 里，
        调用方可以自己决定要不要因为缺项而失败。

        :param run_id: int, 运行 ID（0 = 当前/最新结果）
        :param names: list[str] 可选, 只读指定的 S 参数；不传则自动发现
        :return: dict, ``{名称: ndarray(n,2)}``，第 0 列为频率（**float**，
            已剥掉 CST 返回的复数外壳），第 1 列为复数 S 值
        """
        if names is None:
            names = self.list_s_parameters()
        data, errors = {}, {}
        for name in names:
            try:
                raw = self.read_s_parameter(name, run_id)
                arr = np.asarray(raw)
                data[name] = np.column_stack((_as_real(arr[:, 0]),
                                              _as_complex(arr[:, 1])))
            except Exception as exc:
                errors[name] = repr(exc)
        self.last_errors = errors
        return data

    def export_s_parameters_csv(self, save_path, run_id: int = 0,
                                names=None, in_db: bool = True,
                                delimiter=',', encoding='utf-8-sig'):
        """
        把工程里所有 S 参数导出成一张 CSV（**离线**，不需要设计环境）。

        每个 S 参数一列，第一列是频率。多个 S 参数的频点必须一致
        （同一个求解器的结果本来就是同一套频点）；不一致的条目会被跳过
        并记入 ``self.last_errors``。

        :param save_path: str, 输出 CSV 路径
        :param run_id: int, 运行 ID
        :param names: list[str] 可选, 只导出指定 S 参数
        :param in_db: bool, True 写 dB（20*log10|S|，S 参数最常用的口径）；
            False 写复数（列名加 ``_re`` / ``_im`` 后缀）
        :param delimiter: str, 分隔符
        :param encoding: str, 文件编码，默认 ``'utf-8-sig'``（带 BOM，
            Excel 打开中文列名不乱码）
        :return: str, 写出的文件绝对路径
        :raises ValueError: 一个 S 参数都没读到
        """
        import os
        all_s = self.read_all_s_parameters(run_id=run_id, names=names)
        if not all_s:
            raise ValueError(
                "没有读到任何 S 参数；请先用 list_s_parameters() 看结果树里有什么。"
                f"已知错误：{self.last_errors}")

        # 以第一个成功读到的频轴为准
        ref_name = sorted(all_s)[0]
        freq = _as_real(all_s[ref_name][:, 0])

        skipped = dict(self.last_errors)
        columns, matrix = [], []
        for name in sorted(all_s):
            arr = all_s[name]
            if len(arr) != len(freq):
                skipped[name] = (f'频点数与 {ref_name} 不一致：'
                                 f'{len(arr)} vs {len(freq)}')
                continue
            columns.append(name)
            matrix.append(arr[:, 1])

        if in_db:
            header = ['freq_GHz'] + columns
            rows = np.column_stack([freq] + [_to_db(m) for m in matrix])
        else:
            header = ['freq_GHz']
            for c in columns:
                header += [f'{c}_re', f'{c}_im']
            parts = [freq]
            for m in matrix:
                parts += [_as_complex(m).real, _as_complex(m).imag]
            rows = np.column_stack(parts)

        save_path = os.path.abspath(save_path)
        with open(save_path, 'w', newline='', encoding=encoding) as fh:
            writer = csv.writer(fh, delimiter=delimiter)
            writer.writerow(header)
            for row in rows:
                writer.writerow(['%.10g' % v for v in row])

        self.last_errors = skipped
        return save_path

    def export_farfield_csv(self, save_path, tree_path='Farfields',
                            run_id: int = 0, delimiter=',',
                            encoding='utf-8-sig'):
        """
        导出远场结果到 CSV（**离线**）。

        远场在结果树里是 2D 云图（``2D/3D Results\\Farfields\\...``），
        本方法把它拉平成 ``x, y, value`` 三列的长表，便于外部工具处理。

        ⚠️ 未验证：本机没有含远场结果的工程，这条路径**没有在真实工程上跑过**
        （见 ``stages/05`` 的未验证风险登记）。失败时本方法会抛出
        ``ValueError`` 并附上结果树里的候选路径，方便定位。

        :param save_path: str, 输出 CSV 路径
        :param tree_path: str, 远场结果在 ``2D/3D Results\\`` 下的路径；
            默认 ``'Farfields'``，具体分支名（如 ``'farfield (f=310)'``）需按工程实际填
        :param run_id: int, 运行 ID
        :param delimiter: str, 分隔符
        :param encoding: str, 文件编码
        :return: str, 写出的文件绝对路径
        :raises ValueError: 该路径下读不到结果
        """
        import os
        try:
            data = self.read_3d(tree_path, run_id)
        except Exception as exc:
            raise ValueError(
                f"读不到远场结果 '{tree_path}'（底层错误：{exc!r}）。"
                f"结果树里的候选路径：{self._tree_paths()[:20]}") from exc

        xs = _as_real(data['x'])
        ys = _as_real(data['y'])
        vals = np.asarray(data['values'])
        if np.iscomplexobj(vals):
            vals = np.abs(vals)

        xs = np.atleast_1d(xs).ravel()
        ys = np.atleast_1d(ys).ravel()
        vals = np.atleast_2d(vals)

        rows = []
        for i, x in enumerate(xs):
            for j, y in enumerate(ys):
                if i < vals.shape[0] and j < vals.shape[1]:
                    rows.append((x, y, vals[i, j]))

        save_path = os.path.abspath(save_path)
        with open(save_path, 'w', newline='', encoding=encoding) as fh:
            writer = csv.writer(fh, delimiter=delimiter)
            writer.writerow(['x', 'y', 'value'])
            for x, y, v in rows:
                writer.writerow(['%.10g' % x, '%.10g' % y, '%.10g' % v])
        return save_path


class result(Result):
    """CST 仿真结果读取类（旧名，向后兼容）"""
    pass
