# -*- coding: utf-8 -*-
r"""
YAML 配置驱动（阶段 7 模块 5.2）
===============================
用一个 YAML 文件描述整个模型，notebook 只负责「加载配置 → 建实例 → 跑」。

为什么要有这一层
----------------
手写 `StraightWaveguide(topology='AB', length=18, ...)` 有两个问题：

1. **参数散落在 notebook 里**，跑过的模型无法原样复现；
2. **取值域一直没补齐** —— 计划原文只写了
   `type: straight_waveguide / unit_antenna / grin_lens_antenna / ...` 加省略号。
   省略号意味着**没有**可执行的校验，写错要等 CST 报错才知道。

本模块把取值域补成**可执行**的：`validate_config()` 在任何 CST 调用之前就把
非法取值、未知字段、类型错误、量纲越界全部挡下来。

设计要点
--------
- **接受的字段从模板构造签名自动推导**（`inspect.signature`），不维护第二张清单 ——
  加一个模板参数不用来这里改代码，也不会出现「表里写 A、签名里是 B」的漂移；
- **取值域**（枚举 / 正数 / 区间 / 单位）另用显式表 :data:`FIELD_SPECS` 声明，
  因为它无法从签名推出来；表里同时写明**每个 YAML 字段对应哪个构造参数**
  （`FieldSpec.ctor`），于是两套命名之间的映射也只有一处定义；
- `load_config` / `validate_config` / `example_config` / `dump_config`
  **完全不碰 CST**，没有 CST 的机器也能用；只有 `template_from_config` /
  `modeler_from_config` 需要 CST（它们会真的建实例）。

取值域（计划的 §14.3 缺口，这里补齐）
-------------------------------------
**`model.type` 的完整枚举**（与 `topo_templates/` 的类名一一对应）::

    已实现:  straight_waveguide | unit_antenna
    计划中:  grin_lens_antenna | multiport_antenna | power_divider | mzi_switch

计划中的取值**语法上合法**，但会在 `template_from_config()` 里明确抛「尚未实现」
（属于哪个阶段、对应哪个类名都会说清），不会静默变成别的模型。

其余字段的合法取值见 :data:`FIELD_SPECS` / `field_help()`。

YAML 示例::

    model:
      type: straight_waveguide
    geometry:
      lattice_constant: 0.2425     # mm
      topology: AB                 # AB | BA
      length: 18                   # 晶格数
      width: 14                    # 晶格数
      height: 0.25                 # mm
    feed:
      type: ab_elliptical
      x0: 4
      wf1: 0.2
    waveguide:
      wg_a: 0.7312
      wg_b: 0.3756
      wg_t: 0.2
    solver:
      fmin: 300                    # GHz
      fmax: 380                    # GHz
      monitors: [E]                # E | H | Farfield
    output:
      path: D:\output\wg.cst
      template_cst: tmp.cst

@author: PC
"""

import inspect
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

__all__ = [
    'ConfigError',
    'FieldSpec',
    'FIELD_SPECS',
    'SECTIONS',
    'IMPLEMENTED_MODEL_TYPES',
    'PLANNED_MODEL_TYPES',
    'ALL_MODEL_TYPES',
    'MONITOR_CHOICES',
    'load_config',
    'validate_config',
    'accepted_fields',
    'field_help',
    'example_config',
    'dump_config',
    'template_from_config',
    'modeler_from_config',
    'available_model_types',
]


class ConfigError(ValueError):
    """配置非法（未知字段 / 类型错误 / 取值越界 / 与模板签名不符）。"""


# ============================================================
# 模型类型枚举
# ============================================================

#: 已实现（`topo_templates` 里有对应类）
IMPLEMENTED_MODEL_TYPES = ('straight_waveguide', 'unit_antenna')

#: 计划中（类还不存在）；语法上合法，但 factory 会明确报「未实现」
PLANNED_MODEL_TYPES = ('grin_lens_antenna', 'multiport_antenna',
                       'power_divider', 'mzi_switch')

#: 全部合法取值
ALL_MODEL_TYPES = IMPLEMENTED_MODEL_TYPES + PLANNED_MODEL_TYPES

#: 模型类型 → `topo_templates` 里的类名 + 它属于哪个阶段
_MODEL_TYPE_INFO = {
    'straight_waveguide': ('StraightWaveguide', '阶段 3'),
    'unit_antenna': ('UnitAntenna', '阶段 3'),
    'grin_lens_antenna': ('GRINLensAntenna', '阶段 6（几何层已就绪，模板待建）'),
    'multiport_antenna': ('MultiPortAntenna', '阶段 8'),
    'power_divider': ('PowerDivider', '阶段 8'),
    'mzi_switch': ('MZISwitch', '阶段 8'),
}

#: YAML 允许出现的顶层小节
SECTIONS = ('model', 'geometry', 'feed', 'waveguide', 'solver', 'output')

#: 监视器合法取值（来自 `cst_solver/simulation/monitors.py` 的 `_FIELD_CONFIG`）
MONITOR_CHOICES = ('E', 'H', 'Farfield')


# ============================================================
# 字段取值域
# ============================================================

@dataclass(frozen=True)
class FieldSpec:
    """
    一个可配置字段：**取值域 + 它对应哪个构造参数**。

    :param section: str, 所在 YAML 小节
    :param name: str, YAML 里的键名
    :param kind: str, ``'float'`` / ``'int'`` / ``'str'`` / ``'enum'`` /
        ``'pair'`` / ``'str_list'``
    :param ctor: str, 对应的模板**构造参数名**；``''`` 表示不直接透传
        （由本模块合成，如 ``fmin``/``fmax`` → ``freq_range``）
    :param unit: str, 单位（空串 = 无量纲）；会写进报错信息
    :param doc: str, 一句话说明
    :param choices: tuple, ``kind='enum'`` 时的合法取值
    :param min_value: float 可选, 数值下界
    :param max_value: float 可选, 数值上界
    :param exclusive_min: bool, 下界是否开区间（``>`` 而非 ``>=``）
    :param default: 默认值（用于生成示例配置）
    """

    section: str
    name: str
    kind: str
    ctor: str = ''
    unit: str = ''
    doc: str = ''
    choices: Tuple[Any, ...] = ()
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    exclusive_min: bool = False
    default: Any = None

    @property
    def dotted(self) -> str:
        """``section.name``。"""
        return f'{self.section}.{self.name}'

    def describe(self) -> str:
        """人类可读的取值域说明。"""
        bits = [self.kind]
        if self.unit:
            bits.append(f'[{self.unit}]')
        if self.choices:
            bits.append('∈ {' + ' | '.join(map(str, self.choices)) + '}')
        if self.min_value is not None and self.max_value is not None:
            bits.append(f'∈ [{self.min_value}, {self.max_value}]')
        elif self.min_value is not None:
            bits.append(('>' if self.exclusive_min else '≥') + f' {self.min_value}')
        elif self.max_value is not None:
            bits.append(f'≤ {self.max_value}')
        if self.ctor and self.ctor != self.name:
            bits.append(f'→ 构造参数 {self.ctor}')
        if self.doc:
            bits.append('— ' + self.doc)
        return ' '.join(bits)

    def check(self, value, dotted: Optional[str] = None):
        """
        校验单个值，返回**规范化后**的值。

        :raises ConfigError: 类型 / 范围 / 枚举任一项不符
        """
        dotted = dotted or self.dotted
        if self.kind == 'enum':
            if value not in self.choices:
                raise ConfigError(
                    f"{dotted} = {value!r} 非法；合法取值："
                    f"{' | '.join(map(str, self.choices))}")
            return value

        if self.kind in ('float', 'int'):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ConfigError(
                    f"{dotted} 应为{'整数' if self.kind == 'int' else '数值'}，"
                    f"收到 {type(value).__name__}（{value!r}）")
            if self.kind == 'int' and float(value) != int(value):
                raise ConfigError(f"{dotted} 应为整数，收到 {value!r}")
            num = int(value) if self.kind == 'int' else float(value)
            if self.min_value is not None:
                bad = (num <= self.min_value if self.exclusive_min
                       else num < self.min_value)
                if bad:
                    op = '>' if self.exclusive_min else '≥'
                    unit = f' {self.unit}' if self.unit else ''
                    raise ConfigError(
                        f"{dotted} 必须 {op} {self.min_value}{unit}，收到 {num}")
            if self.max_value is not None and num > self.max_value:
                unit = f' {self.unit}' if self.unit else ''
                raise ConfigError(
                    f"{dotted} 必须 ≤ {self.max_value}{unit}，收到 {num}")
            return num

        if self.kind == 'pair':
            if not isinstance(value, (list, tuple)) or len(value) != 2:
                raise ConfigError(
                    f"{dotted} 应为长度 2 的序列（如 [300, 380]），收到 {value!r}")
            return tuple(value)

        if self.kind == 'str':
            if not isinstance(value, str):
                raise ConfigError(
                    f"{dotted} 应为字符串，收到 {type(value).__name__}（{value!r}）")
            return value

        if self.kind == 'str_list':
            if isinstance(value, str):
                raise ConfigError(
                    f"{dotted} 应为列表（如 [E] 或 [E, Farfield]），收到字符串 "
                    f"{value!r}；YAML 里写 `monitors: [E]` 而不是 `monitors: E`")
            if not isinstance(value, (list, tuple)):
                raise ConfigError(
                    f"{dotted} 应为列表，收到 {type(value).__name__}")
            return list(value)

        raise ConfigError(f"字段 {dotted} 的 kind={self.kind!r} 未实现（内部错误）")


def _f(section, name, kind, **kw):
    return FieldSpec(section=section, name=name, kind=kind, **kw)


#: 全部可配置字段 —— **取值域与「YAML 名 → 构造参数名」映射的唯一权威**
FIELD_SPECS: Tuple[FieldSpec, ...] = (
    # ---- model ----
    _f('model', 'type', 'enum', choices=ALL_MODEL_TYPES,
       doc='器件类型，与 topo_templates 的类名一一对应', default='straight_waveguide'),

    # ---- geometry ----
    _f('geometry', 'lattice_constant', 'float', ctor='lattice_constant',
       unit='mm', exclusive_min=True, doc='三角晶格常数 a', default=0.2425),
    _f('geometry', 'height', 'float', ctor='height',
       unit='mm', exclusive_min=True, doc='硅片厚度 h', default=0.25),
    _f('geometry', 'topology', 'enum', ctor='topology', choices=('AB', 'BA'),
       doc='拓扑相', default='AB'),
    _f('geometry', 'large_hole_ratio', 'float', ctor='large_hole_ratio',
       min_value=0.0, max_value=1.0, exclusive_min=True,
       doc='大孔比例 l1 = ratio * a', default=0.65),
    _f('geometry', 'small_hole_ratio', 'float', ctor='small_hole_ratio',
       min_value=0.0, max_value=1.0, exclusive_min=True,
       doc='小孔比例 l2 = ratio * a', default=0.35),
    _f('geometry', 'length', 'int', ctor='length', min_value=1, unit='格',
       doc='波导长度（晶格数，不含起点偏移）—— 仅 straight_waveguide', default=18),
    _f('geometry', 'width', 'int', ctor='width', min_value=1, unit='格',
       doc='波导/VPC 半宽（晶格数）；同时决定阵列范围 yup/ydn', default=14),
    _f('geometry', 'bend_angle', 'enum', ctor='bend_angle',
       choices=(60, 120, 180, 240, 300),
       doc='拐弯角（60° 的整数倍）—— 仅 unit_antenna', default=120),
    _f('geometry', 'straight_length', 'int', ctor='straight_length',
       min_value=1, unit='格', doc='直段长度（晶格数）—— 仅 unit_antenna', default=18),
    _f('geometry', 'arm_length', 'int', ctor='arm_length',
       min_value=1, unit='格', doc='拐弯后臂长（晶格数）—— 仅 unit_antenna', default=14),

    # ---- feed ----
    _f('feed', 'type', 'enum', ctor='feed_type',
       choices=('ab_elliptical', 'ba_tapered', 'cylinder'),
       doc='馈源类型（模板构造参数名是 feed_type）'),
    _f('feed', 'x0', 'float', ctor='x0', unit='格',
       doc='探针起点（晶格数）', default=4),
    _f('feed', 'wf1', 'float', ctor='wf1', unit='mm', exclusive_min=True,
       doc='探针宽度', default=0.2),
    _f('feed', 'lf1', 'float', ctor='lf1', unit='mm', exclusive_min=True,
       doc='探针长度 1', default=0.2),
    _f('feed', 'lf2', 'float', ctor='lf2', unit='mm', exclusive_min=True,
       doc='椭圆过渡半轴', default=3.0),
    _f('feed', 'lf3', 'float', ctor='lf3', unit='mm', exclusive_min=True,
       doc='探针长度 3', default=0.2),
    _f('feed', 'radiator', 'enum', ctor='radiator', choices=(None, 'cylinder'),
       default=None, doc='末端辐射体类型（仅 unit_antenna）；None 表示不建'),
    _f('feed', 'radiator_radius', 'float', ctor='radiator_radius',
       unit='mm', exclusive_min=True,
       doc='圆柱辐射体半径（仅 radiator=cylinder 时生效）', default=0.3),

    # ---- waveguide ----
    _f('waveguide', 'wg_a', 'float', ctor='wg_a', unit='mm', exclusive_min=True,
       doc='空心波导内腔 z 向高度', default=0.7312),
    _f('waveguide', 'wg_b', 'float', ctor='wg_b', unit='mm', exclusive_min=True,
       doc='空心波导内腔 y 向宽度', default=0.3756),
    _f('waveguide', 'wg_t', 'float', ctor='wg_t', unit='mm', exclusive_min=True,
       doc='波导壁厚', default=0.2),

    # ---- solver ----
    _f('solver', 'fmin', 'float', ctor='', unit='GHz', exclusive_min=True,
       doc='扫频下限（与 fmax 合成构造参数 freq_range）', default=300.0),
    _f('solver', 'fmax', 'float', ctor='', unit='GHz', exclusive_min=True,
       doc='扫频上限，必须大于 fmin', default=380.0),
    _f('solver', 'monitors', 'str_list', ctor='monitors',
       doc='监视器列表，取值 E | H | Farfield', default=('E',)),

    # ---- output ----
    _f('output', 'path', 'str', ctor='output_path',
       doc='.cst 输出路径（构造参数名是 output_path）'),
    _f('output', 'template_cst', 'str', ctor='template_cst',
       doc='CST 模板工程路径', default='tmp.cst'),
)

FIELD_INDEX: Dict[Tuple[str, str], FieldSpec] = {
    (s.section, s.name): s for s in FIELD_SPECS}

#: 有哪些 YAML 字段名（跨小节）重名 —— 用于给出更准的报错
_DUPLICATE_NAMES = {}


def _build_name_index():
    index: Dict[str, List[FieldSpec]] = {}
    for spec in FIELD_SPECS:
        index.setdefault(spec.name, []).append(spec)
    return index


_NAME_INDEX = _build_name_index()


# ============================================================
# 读取与校验
# ============================================================

def _require_yaml():
    """惰性导入 PyYAML —— 它是可选依赖，不该让 import 本模块就需要它。"""
    try:
        import yaml
    except ImportError as exc:                     # pragma: no cover
        raise ConfigError(
            "读/写 YAML 需要 PyYAML（pip install pyyaml）；"
            "也可以直接把 dict 传给 load_config()") from exc
    return yaml


def load_config(source) -> Dict[str, Any]:
    """
    读取配置。

    :param source: str（YAML 路径）或 dict（直接给已解析的配置）
    :return: dict, 原始配置（**未校验**；校验用 `validate_config`）
    :raises ConfigError: 文件不存在 / YAML 语法错 / 顶层不是映射
    """
    if isinstance(source, dict):
        return dict(source)
    if not isinstance(source, str):
        raise ConfigError(f"配置应为 YAML 路径或 dict，收到 {type(source).__name__}")
    if not os.path.exists(source):
        raise ConfigError(f"配置文件不存在：{source}")
    yaml = _require_yaml()
    try:
        with open(source, encoding='utf-8') as fh:
            data = yaml.safe_load(fh)
    except Exception as exc:
        raise ConfigError(f"YAML 解析失败（{source}）：{exc}") from exc
    if data is None:
        raise ConfigError(f"配置文件为空：{source}")
    if not isinstance(data, dict):
        raise ConfigError(f"配置顶层应为映射（key: value），收到 {type(data).__name__}")
    return data


def _flatten(cfg: Dict[str, Any]) -> Dict[Tuple[str, str], Any]:
    """把嵌套配置摊平成 ``{(section, name): value}``，同时做结构校验。"""
    flat: Dict[Tuple[str, str], Any] = {}
    for key, value in cfg.items():
        if key.startswith('_'):
            continue                                # 本模块自己写的注记
        if key not in SECTIONS:
            raise ConfigError(
                f"未知的顶层小节 {key!r}；合法小节：{' | '.join(SECTIONS)}"
                f"（不要把小节名写错，也不要把字段提到顶层）")
        if value is None:
            continue
        if not isinstance(value, dict):
            raise ConfigError(f"小节 {key!r} 应为映射，收到 {type(value).__name__}")
        for sub, sub_value in value.items():
            flat[(key, sub)] = sub_value
    return flat


def validate_config(cfg, model_type: Optional[str] = None,
                    strict: bool = True) -> Dict[str, Any]:
    """
    校验并规范化配置（**不碰 CST**）。

    做四件事：

    1. **结构**：顶层小节必须是 :data:`SECTIONS` 之一；
    2. **字段**：每个键必须在该小节里有取值域定义，否则报错并列出合法字段；
    3. **取值**：类型、单位、范围、枚举逐项检查；
    4. **与模板匹配**：把 YAML 名映射成构造参数名后，和模板签名对一遍 ——
       该类型不接受的字段（例如给直波导写 `bend_angle`）在这里就报错，
       而不是等建到一半才 `TypeError`。

    :param cfg: dict 或 YAML 路径
    :param model_type: str 可选, 覆盖 `model.type`（便于「同一份几何换器件」）
    :param strict: bool, True 时未知字段报错；False 时记进 `_warnings` 并丢弃
    :return: dict, 规范化后的配置（结构不变、值已转成正确类型）；
        `strict=False` 时可能带 `_warnings` / `_dropped` 两个下划线键
    :raises ConfigError: 任一项非法
    """
    raw = load_config(cfg)
    flat = _flatten(raw)

    mtype = model_type or flat.get(('model', 'type'))
    if mtype is None:
        raise ConfigError("缺少 model.type；合法取值：" + ' | '.join(ALL_MODEL_TYPES))
    if mtype not in ALL_MODEL_TYPES:
        raise ConfigError(
            f"model.type = {mtype!r} 非法；合法取值：" + ' | '.join(ALL_MODEL_TYPES))

    warnings_list: List[str] = []
    dropped: Dict[str, Any] = {}
    clean: Dict[Tuple[str, str], Any] = {}

    for pair, value in flat.items():
        spec = FIELD_INDEX.get(pair)
        if spec is None:
            legal = sorted(n for (s, n) in FIELD_INDEX if s == pair[0])
            msg = (f"未知字段 {pair[0]}.{pair[1]}；"
                   f"`{pair[0]}` 小节的合法字段："
                   f"{', '.join(legal) if legal else '（该小节无字段）'}")
            if strict:
                raise ConfigError(msg)
            warnings_list.append(msg + '（已忽略）')
            dropped[f'{pair[0]}.{pair[1]}'] = value
            continue
        if value is None:
            continue                                # 显式 null = 不设置
        clean[pair] = spec.check(value)

    # 监视器取值
    if ('solver', 'monitors') in clean:
        monitors = clean[('solver', 'monitors')]
        if not monitors:
            raise ConfigError("solver.monitors 不能为空列表（至少要一个监视器）")
        for mon in monitors:
            if mon not in MONITOR_CHOICES:
                raise ConfigError(
                    f"solver.monitors 里的 {mon!r} 非法；合法取值："
                    f"{' | '.join(MONITOR_CHOICES)}"
                    f"（见 cst_solver/simulation/monitors.py 的 _FIELD_CONFIG）")

    # 频率区间
    if ('solver', 'fmin') in clean and ('solver', 'fmax') in clean:
        if clean[('solver', 'fmax')] <= clean[('solver', 'fmin')]:
            raise ConfigError(
                f"solver.fmax ({clean[('solver', 'fmax')]}) 必须大于 "
                f"solver.fmin ({clean[('solver', 'fmin')]})")

    # 与模板签名对表（不要求 CST：只读签名）
    if mtype in PLANNED_MODEL_TYPES:
        # 类还不存在 ⇒ 没有签名可对。**语法上放行**，但明确标注「字段未核对」，
        # 真正的「未实现」由 template_from_config() 抛出（那里能说清属于哪个阶段）。
        _, stage = _MODEL_TYPE_INFO[mtype]
        warnings_list.append(
            f"model.type={mtype!r} 尚未实现（属于{stage}），"
            f"字段未与模板签名核对；建实例时会明确报错")
    else:
        ok = set(accepted_fields(mtype))
        unknown = sorted(f'{s}.{n}' for (s, n) in clean
                         if s != 'model' and n not in ok)
        if unknown:
            raise ConfigError(
                f"model.type={mtype!r} 的模板不接受这些字段：{', '.join(unknown)}\n"
                f"  它接受的是：{', '.join(sorted(ok))}\n"
                f"  （例如直波导没有 bend_angle / straight_length / arm_length，"
                f"那是 unit_antenna 的字段）")

    result: Dict[str, Any] = {'model': {'type': mtype}}
    for (section, name), value in sorted(clean.items()):
        if section == 'model':
            continue
        result.setdefault(section, {})[name] = value
    if warnings_list:
        result['_warnings'] = warnings_list
    if dropped:
        result['_dropped'] = dropped
    return result


# ============================================================
# 与模板签名对表
# ============================================================

def _ctor_params(model_type: str) -> set:
    """模板构造签名里的参数名（不含 `self`）。惰性导入 `topo_templates`。"""
    cls = _template_class(model_type)
    return set(inspect.signature(cls.__init__).parameters) - {'self'}


def _template_class(model_type: str):
    """取模板类（惰性导入 `topo_templates`，因此本模块导入时不碰 CST）。"""
    info = _MODEL_TYPE_INFO.get(model_type)
    if info is None:
        raise ConfigError(f"未知 model.type: {model_type!r}")
    name, stage = info
    import topo_templates
    cls = getattr(topo_templates, name, None)
    if cls is None:
        raise ConfigError(
            f"model.type={model_type!r} 需要模板类 topo_templates.{name}，"
            f"但它还不存在（属于{stage}）。\n"
            f"  现在能用的类型：{' | '.join(IMPLEMENTED_MODEL_TYPES)}\n"
            f"  尚未实现的类型：{' | '.join(PLANNED_MODEL_TYPES)}"
            f"（见 docs/next_plan/README.md 的阶段表）")
    return cls


def accepted_fields(model_type: str) -> Tuple[str, ...]:
    """
    该模型类型**可写的 YAML 字段名**（从模板构造签名自动推导）。

    `solver.fmin` / `solver.fmax` 由本模块合成 `freq_range`，所以它们也在这里返回。

    :param model_type: str, 模型类型
    :return: tuple[str, ...], 排好序的字段名（裸名，不含小节前缀）
    :raises ConfigError: 模型类型未实现
    """
    params = _ctor_params(model_type)
    ok = set()
    for spec in FIELD_SPECS:
        if spec.section == 'model':
            continue
        if spec.ctor:
            if spec.ctor in params:
                ok.add(spec.name)
        elif spec.name in ('fmin', 'fmax') and 'freq_range' in params:
            ok.add(spec.name)
    return tuple(sorted(ok))


def field_help(model_type: Optional[str] = None) -> List[str]:
    """
    逐行列出可配置字段及其取值域（供文档生成 / 报错自省 / 手工查阅）。

    :param model_type: str 可选, 只列该类型接受的字段
    :return: list[str]
    """
    ok = set(accepted_fields(model_type)) if model_type else None
    lines = []
    current = None
    for spec in FIELD_SPECS:
        if spec.section == 'model':
            continue
        if ok is not None and spec.name not in ok:
            continue
        if spec.section != current:
            current = spec.section
            lines.append(f'[{spec.section}]')
        lines.append(f'  {spec.name:<20} {spec.describe()}')
    return lines


# ============================================================
# 配置 → 构造参数
# ============================================================

def _to_ctor_kwargs(clean: Dict[str, Any]) -> Dict[str, Any]:
    """
    把规范化后的配置摊成模板构造参数。

    三处不是同名直通的地方，全部由 :data:`FIELD_SPECS` 的 ``ctor`` 字段说明：

    - ``feed.type`` → ``feed_type``
    - ``output.path`` → ``output_path``
    - ``solver.fmin`` + ``solver.fmax`` → ``freq_range=(fmin, fmax)``
    """
    kwargs: Dict[str, Any] = {}
    for section, values in clean.items():
        if section.startswith('_') or section == 'model':
            continue
        if not isinstance(values, dict):
            continue
        for key, value in values.items():
            spec = FIELD_INDEX.get((section, key))
            if spec is None or not spec.ctor:
                continue                            # fmin/fmax 单独合成
            kwargs[spec.ctor] = value
    solver = clean.get('solver') or {}
    if 'fmin' in solver and 'fmax' in solver:
        kwargs['freq_range'] = (solver['fmin'], solver['fmax'])
    elif 'fmin' in solver:
        kwargs['freq_range'] = (solver['fmin'], FIELD_INDEX[('solver', 'fmax')].default)
    elif 'fmax' in solver:
        kwargs['freq_range'] = (FIELD_INDEX[('solver', 'fmin')].default, solver['fmax'])
    return kwargs


# ============================================================
# 工厂（需要 CST）
# ============================================================

def template_from_config(cfg, model_type: Optional[str] = None,
                         validate_only: bool = False, **overrides):
    """
    按配置建模板实例（**需要 CST** —— 模板构造会打开 `template_cst`）。

    :param cfg: dict 或 YAML 路径
    :param model_type: str 可选, 覆盖 `model.type`
    :param validate_only: bool, True 时只校验并返回构造参数字典，**不建实例**
        （因此在没有 CST 的机器上也能用；测试与预检都靠它）
    :param overrides: 直接覆盖若干构造参数（不进 YAML，便于临时试参）
    :return: 模板实例，或 `validate_only=True` 时的构造参数字典
    :raises ConfigError: 配置非法，或该模型类型尚未实现
    """
    clean = validate_config(cfg, model_type=model_type)
    mtype = clean['model']['type']
    cls = _template_class(mtype)                    # 未实现会抛带阶段的说明
    kwargs = _to_ctor_kwargs(clean)
    kwargs.update(overrides)
    if validate_only:
        kwargs['_model_type'] = mtype
        kwargs['_class'] = cls.__name__
        return kwargs
    return cls(**kwargs)


def modeler_from_config(cfg, model_type: Optional[str] = None,
                        build_path: bool = True, **overrides):
    """
    按配置建 `TopoModeler` 实例（**需要 CST**）。

    只做「路径 + 参数 + 拓扑相」三件事，**不执行任何 builder** ——
    真要建模型请用 `template_from_config()`。

    :param cfg: dict 或 YAML 路径
    :param model_type: str 可选, 覆盖 `model.type`
    :param build_path: bool, 是否顺便建好 `TopoPath`（False 则只设参数）
    :param overrides: 透传给 `TopoModeler`（如 `template_cst=`）
    :return: TopoModeler
    :raises ConfigError: 配置非法
    """
    from topo_modeler.modeler import TopoModeler
    from mesh_grid.tri_grid import TopoPath

    clean = validate_config(cfg, model_type=model_type)
    mtype = clean['model']['type']
    geo = clean.get('geometry') or {}
    out = clean.get('output') or {}

    kwargs = {'template_cst': out.get('template_cst', 'tmp.cst')}
    kwargs.update(overrides)
    modeler = TopoModeler(**kwargs)

    if build_path:
        a = geo.get('lattice_constant', 0.2425)
        if mtype == 'unit_antenna':
            bend = geo.get('bend_angle', 120)
            path = (TopoPath.builder(a, name='p')
                    .start(0, 0).move(geo.get('straight_length', 18), 'c')
                    .turn(bend).move(geo.get('arm_length', 14), 'along').build())
        else:
            path = (TopoPath.builder(a, name='p')
                    .start(0, 0).move(geo.get('length', 18), 'c').build())
        modeler.set_path(path)
    if 'topology' in geo:
        modeler.set_topology(geo['topology'])
    return modeler


# ============================================================
# 示例配置与落盘
# ============================================================

def _yaml_safe(value):
    """把 tuple 等转成 YAML 友好的纯量。"""
    if isinstance(value, tuple):
        return list(value)
    return value


def example_config(model_type: str = 'straight_waveguide') -> Dict[str, Any]:
    """
    生成一份**可直接跑**的示例配置（取值优先取模板签名的默认值）。

    :param model_type: str, 模型类型
    :return: dict
    :raises ConfigError: 未知类型
    """
    if model_type not in ALL_MODEL_TYPES:
        raise ConfigError(
            f"未知 model.type={model_type!r}；合法取值：{' | '.join(ALL_MODEL_TYPES)}")

    sig_defaults = {}
    if model_type in IMPLEMENTED_MODEL_TYPES:
        for name, p in inspect.signature(
                _template_class(model_type).__init__).parameters.items():
            if name != 'self' and p.default is not inspect.Parameter.empty:
                sig_defaults[name] = p.default

    out: Dict[str, Any] = {'model': {'type': model_type}}
    ok = set(accepted_fields(model_type)) if model_type in IMPLEMENTED_MODEL_TYPES \
        else {s.name for s in FIELD_SPECS if s.section != 'model'}
    for spec in FIELD_SPECS:
        if spec.section == 'model' or spec.name not in ok:
            continue
        value = None
        if spec.ctor and spec.ctor in sig_defaults:
            value = sig_defaults[spec.ctor]
        elif spec.name in ('fmin', 'fmax') and 'freq_range' in sig_defaults:
            value = float(sig_defaults['freq_range'][0 if spec.name == 'fmin' else 1])
        elif spec.default is not None and spec.section != 'output':
            value = spec.default
        if value is None:
            continue                                # path 之类无默认值的不写出来
        out.setdefault(spec.section, {})[spec.name] = _yaml_safe(value)
    return out


def dump_config(cfg, path, header: str = '') -> str:
    """
    把配置写成 YAML（**需要 PyYAML**）。

    :param cfg: dict
    :param path: str, 输出路径
    :param header: str, 写在文件开头的注释
    :return: str, 写出的绝对路径
    """
    yaml = _require_yaml()
    path = os.path.abspath(path)
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        if header:
            for line in header.splitlines():
                fh.write(f'# {line}\n')
        yaml.safe_dump(cfg, fh, allow_unicode=True, sort_keys=False,
                       default_flow_style=False)
    return path


def available_model_types(implemented_only: bool = False) -> Tuple[str, ...]:
    """
    可用模型类型。

    :param implemented_only: bool, True 只返回现在真能建的类型
    :return: tuple[str, ...]
    """
    return IMPLEMENTED_MODEL_TYPES if implemented_only else ALL_MODEL_TYPES
