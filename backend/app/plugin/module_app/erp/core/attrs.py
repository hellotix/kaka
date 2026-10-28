"""扩展属性（JSON）的校验与过滤 —— 全工程唯一处理 attrs 的地方。

集中在此的原因
--------------
物品档案的动态属性存在 ``erp_item.attrs`` JSON 列上。JSON 过滤在 MySQL 上写不出来索引，
数据量一大就是全表扫。需求当前按「单家庭最多 1000 条」估算，先靠 ``family_id`` 索引把
行集收敛到千级再算 JSON 表达式，够用；将来涨到万级，只需把本文件的
``build_attr_conditions`` 换成生成列或 ES 查询，调用方（service 层）一行都不用改。

属性值的存储约定
----------------
落库前一律经 ``normalize_attrs`` 规范化，保证 JSON 里的类型是可预测的：

- number      → int 或 float（不带单位，单位在模板的 ``unit`` 字段上）
- bool        → true / false
- date        → "YYYY-MM-DD" 字符串
- select      → 候选项的 value 字符串
- multi_select→ 字符串数组
- text/textarea → 字符串（去除首尾空白）
"""

import json
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any

from sqlalchemy import func
from sqlalchemy.sql.elements import ColumnElement

from .constants import ErpAttrType

# 支持的过滤操作符；语义与 CRUDBase._resolve_condition 保持一致，降低前端理解成本
_FILTER_OPS: frozenset[str] = frozenset({"eq", "ne", "like", "in", "gt", "ge", "lt", "le", "between", "null", "not_null"})

_DATE_FORMAT = "%Y-%m-%d"


class AttrValidationError(ValueError):
    """属性值不符合模板定义。

    继承 ValueError 是为了让 FastAPI 的 RequestValidationError/自定义异常处理器之外，
    service 层可以捕获后转成 ``CustomException``，返回业务错误而不是 500。
    """


def _template_view(template: Any) -> dict[str, Any]:
    """把模板统一成 dict，兼容 ORM 对象与 dict 两种入参（便于单测）。"""
    if isinstance(template, Mapping):
        return dict(template)
    return {
        "code": template.code,
        "label": template.label,
        "type": template.type,
        "options": template.options,
        "unit": template.unit,
        "is_required": template.is_required,
        "default_value": template.default_value,
    }


def _option_values(options: Any) -> set[str]:
    """从 options 里取出全部合法 value，兼容 [{value,label}] 与 ["a","b"] 两种配法。"""
    if not options:
        return set()
    values: set[str] = set()
    for item in options:
        if isinstance(item, Mapping):
            if "value" in item:
                values.add(str(item["value"]))
        else:
            values.add(str(item))
    return values


def _coerce_number(label: str, raw: Any) -> int | float:
    """转数值；布尔值不接受（True 会被 int() 悄悄变成 1，属于录入错误）。"""
    if isinstance(raw, bool):
        raise AttrValidationError(f"属性「{label}」应为数值")
    if isinstance(raw, (int, float)):
        return raw
    text = str(raw).strip()
    if not text:
        raise AttrValidationError(f"属性「{label}」不能为空")
    try:
        number = float(text)
    except ValueError:
        raise AttrValidationError(f"属性「{label}」不是合法数值: {raw}") from None
    return int(number) if number.is_integer() else number


def _coerce_date(label: str, raw: Any) -> str:
    """转 YYYY-MM-DD 字符串；接受 date/datetime 与同格式字符串。"""
    if isinstance(raw, datetime):
        return raw.date().isoformat()
    if isinstance(raw, date):
        return raw.isoformat()
    text = str(raw).strip()
    if not text:
        raise AttrValidationError(f"属性「{label}」不能为空")
    try:
        return datetime.strptime(text, _DATE_FORMAT).date().isoformat()
    except ValueError:
        raise AttrValidationError(f"属性「{label}」日期格式应为 YYYY-MM-DD: {raw}") from None


def _coerce_bool(raw: Any) -> bool:
    """转布尔；字符串只认常见的真值写法，避免 "false" 被 truthy 判成 True。"""
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return raw != 0
    return str(raw).strip().lower() in ("1", "true", "yes", "on", "是")


def normalize_attrs(templates: Sequence[Any], attrs: Mapping[str, Any] | None) -> dict[str, Any]:
    """按模板校验并规范化属性值，返回可直接写入 JSON 列的 dict。

    参数:
    - templates (Sequence[Any]): 有效属性模板（ORM 对象或 dict），由调用方按分类收集好。
    - attrs (Mapping[str, Any] | None): 前端提交的原始属性值。

    返回:
    - dict[str, Any]: 规范化后的属性值；模板未定义的键会被丢弃，未提交的可选属性不补默认值
      （缺键与「值为 null」在 JSON 过滤里语义不同，缺键表示未填写）。

    异常:
    - AttrValidationError: 必填缺失、类型不合法、或 select 值不在候选项内。
    """
    submitted = dict(attrs or {})
    result: dict[str, Any] = {}

    for raw_template in templates:
        template = _template_view(raw_template)
        code = str(template.get("code") or "").strip()
        if not code:
            continue
        label = str(template.get("label") or code)
        attr_type = str(template.get("type") or ErpAttrType.TEXT.value)
        raw = submitted.get(code, None)

        # 未提交：必填则报错，可选则跳过（不写键）
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            if template.get("is_required"):
                raise AttrValidationError(f"属性「{label}」为必填项")
            continue

        if attr_type == ErpAttrType.NUMBER.value:
            result[code] = _coerce_number(label, raw)
        elif attr_type == ErpAttrType.DATE.value:
            result[code] = _coerce_date(label, raw)
        elif attr_type == ErpAttrType.BOOL.value:
            result[code] = _coerce_bool(raw)
        elif attr_type == ErpAttrType.SELECT.value:
            value = str(raw).strip()
            allowed = _option_values(template.get("options"))
            if allowed and value not in allowed:
                raise AttrValidationError(f"属性「{label}」取值不合法: {value}")
            result[code] = value
        elif attr_type == ErpAttrType.MULTI_SELECT.value:
            if isinstance(raw, str):
                values = [item.strip() for item in raw.split(",") if item.strip()]
            elif isinstance(raw, Sequence):
                values = [str(item).strip() for item in raw if str(item).strip()]
            else:
                raise AttrValidationError(f"属性「{label}」应为多选数组")
            allowed = _option_values(template.get("options"))
            if allowed:
                invalid = [item for item in values if item not in allowed]
                if invalid:
                    raise AttrValidationError(f"属性「{label}」取值不合法: {', '.join(invalid)}")
            # 去重且保持提交顺序，避免同一值重复导致 LIKE 过滤重复命中
            result[code] = list(dict.fromkeys(values))
        else:
            # text / textarea：统一按字符串存，超长由模板配置方在前端限制
            result[code] = str(raw).strip()

    # 只按 templates 遍历，模板之外的键天然不会进入 result：后台下线某个属性后，
    # 前端旧缓存仍可能带上它，直接丢弃可避免 JSON 列堆积无人能解释的脏数据。
    return result


def build_attr_conditions(column: Any, filters: Mapping[str, Any] | None) -> list[ColumnElement]:
    """把属性过滤参数翻译成 SQLAlchemy 条件列表。

    参数:
    - column (Any): 物品模型上的 JSON 列（如 ``ErpItemModel.attrs``）。
    - filters (Mapping[str, Any] | None): 过滤参数，两种写法等价::

          {"color": "红"}  # 等值
          {"price": {"op": "between", "value": [10, 20]}}  # 显式操作符

    返回:
    - list[ColumnElement]: 可直接传给 ``select().where(*conditions)`` 的条件。
      非法操作符或空值会被跳过，不抛异常（筛选面板传错一个键不该让整个列表 500）。

    实现说明:
    - 标量比较统一走 SQLAlchemy 的 JSON 访问器 ``as_string()`` / ``as_float()``，由方言各自渲染
      （下面是实测结果，不要凭想象改）::

          MySQL       CASE JSON_EXTRACT(c,'$."k"') WHEN 'null' THEN NULL
                      ELSE JSON_UNQUOTE(JSON_EXTRACT(c,'$."k"')) END = 'v'
                      CASE ... ELSE JSON_EXTRACT(c,'$."k"')+0.0000000000000000000000 END >= 10
          PostgreSQL  CAST((c ->> 'k') AS VARCHAR) = 'v'
                      CAST((c ->> 'k') AS FLOAT) >= 10
          SQLite      JSON_EXTRACT(c,'$."k"') = 'v'

      MySQL 的数值比较不是 ``CAST(... AS DECIMAL)``，而是「加一个高精度的 0」触发隐式转换；
      两种写法都能让 ``"500"`` 与 ``500`` 按数值比较。外层 ``CASE ... WHEN 'null'`` 是
      MySQL 特有的，用来把 JSON null 映射成 SQL NULL（否则 ``NULL`` 比较会静默不命中）。
    - ``null`` / ``not_null`` 刻意不走访问器，直接用 ``func.json_extract``：访问器包了
      ``CASE ... WHEN 'null' THEN NULL`` 之后 ``IS NOT NULL`` 语义会被 MySQL 的 JSON null
      与 SQL NULL 混淆，而 ``json_extract(...) IS NULL`` 在三种方言下都表示「键不存在或为 null」。
    - multi_select 存的是 JSON 数组，``like`` 直接按子串匹配序列化后的数组文本
      （``["红","蓝"]`` 能被 ``%红%`` 命中）。这是刻意的取舍：``JSON_CONTAINS`` 只有
      MySQL 支持，而 LIKE 在三方言下行为一致；代价是短值可能误命中长值
      （筛「红」会同时命中「大红」），候选项由后台配置时应避免这类包含关系。
    """
    if not filters:
        return []

    conditions: list[ColumnElement] = []
    for raw_code, raw_spec in filters.items():
        code = str(raw_code).strip()
        if not code:
            continue

        op, value = _parse_spec(raw_spec)
        if op not in _FILTER_OPS:
            continue

        path = column[code]
        json_path = f'$."{code}"'

        if op == "null":
            conditions.append(func.json_extract(column, json_path).is_(None))
            continue
        if op == "not_null":
            conditions.append(func.json_extract(column, json_path).isnot(None))
            continue
        if value is None or value == "":
            continue

        if op == "in":
            values = value if isinstance(value, Sequence) and not isinstance(value, str) else [value]
            values = [str(item) for item in values if str(item).strip()]
            if not values:
                continue
            conditions.append(path.as_string().in_(values))
            continue

        if op == "between":
            if not isinstance(value, Sequence) or isinstance(value, str) or len(value) != 2:
                continue
            low, high = value
            if low is None or high is None:
                continue
            if _is_number(low) and _is_number(high):
                conditions.append(path.as_float().between(float(low), float(high)))
            else:
                conditions.append(path.as_string().between(str(low), str(high)))
            continue

        if op == "like":
            conditions.append(path.as_string().like(f"%{value}%"))
            continue

        # 到这里 op 只可能是 eq/ne/gt/ge/lt/le（其余分支上面已处理完）
        if _is_number(value) and not isinstance(value, bool):
            conditions.append(_apply_compare(path.as_float(), op, float(value)))
            continue

        str_value = _bool_literal(value) if isinstance(value, bool) else str(value)
        conditions.append(_apply_compare(path.as_string(), op, str_value))

    return conditions


def _apply_compare(lhs: Any, op: str, rhs: Any) -> ColumnElement:
    """按操作符比较两个 SQL 表达式。``op`` 由调用方保证属于 ``_FILTER_OPS``。"""
    if op == "ne":
        return lhs != rhs
    if op == "gt":
        return lhs > rhs
    if op == "ge":
        return lhs >= rhs
    if op == "lt":
        return lhs < rhs
    if op == "le":
        return lhs <= rhs
    return lhs == rhs


def _parse_spec(raw_spec: Any) -> tuple[str, Any]:
    """把 ``"红"`` 或 ``{"op": "gt", "value": 3}`` 统一成 ``(op, value)``。"""
    if isinstance(raw_spec, Mapping):
        op = str(raw_spec.get("op") or "eq").strip().lower()
        return op, raw_spec.get("value", None)
    return "eq", raw_spec


def _is_number(value: Any) -> bool:
    """判断是否为可比较的数值（bool 是 int 的子类，需排除）。"""
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, str):
        try:
            float(value.strip())
            return True
        except ValueError:
            return False
    return False


def _bool_literal(value: Any) -> str:
    """布尔值在 JSON 里落库为 true/false，比较时需用同样的字面量。"""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str) and value.strip().lower() in ("true", "false", "1", "0", "yes", "no"):
        return "true" if value.strip().lower() in ("true", "1", "yes") else "false"
    return str(value)


def describe_filters(filters: Mapping[str, Any] | None) -> str:
    """把过滤参数序列化成短字符串，用于日志排查（避免出现不可 repr 的对象）。"""
    if not filters:
        return ""
    try:
        return json.dumps(dict(filters), ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(filters)
