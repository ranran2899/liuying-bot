"""安全数学计算实现

用 AST 白名单求值替代 eval，杜绝任意代码执行。
LLM 自行心算长表达式容易出错，本技能提供确定性算术能力。
"""

import ast
import math
import operator
from typing import Any

from liuying.liuying_plugins.AI.agent.runtime.constants import (
    EVIDENCE_KIND_TOOL,
    INTENT_TAG_LOCAL,
    LATENCY_CLASS_FAST,
)
from liuying.liuying_plugins.AI.agent.tools import AgentTool

_MAX_EXPR_LENGTH = 200
"""表达式最大长度，防御超长输入"""

_MAX_POWER_EXPONENT = 64
"""幂运算指数上限，防御 9**9**9 类算力炸弹"""

_BIN_OPS: dict[type[ast.operator], Any] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
"""允许的二元运算符映射"""

_UNARY_OPS: dict[type[ast.unaryop], Any] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}
"""允许的一元运算符映射"""

_FUNCS: dict[str, Any] = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sum": sum,
    "pow": pow,
    "sqrt": math.sqrt,
    "log": math.log,
    "log2": math.log2,
    "log10": math.log10,
    "exp": math.exp,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "floor": math.floor,
    "ceil": math.ceil,
    "factorial": math.factorial,
    "gcd": math.gcd,
    "hypot": math.hypot,
}
"""允许调用的数学函数白名单"""

_CONSTS: dict[str, float] = {
    "pi": math.pi,
    "e": math.e,
    "tau": math.tau,
}
"""允许引用的数学常量"""


class CalcError(ValueError):
    """表达式非法或求值失败"""


def _eval_node(node: ast.AST) -> Any:
    """递归求值AST节点

    只放行字面量、括号、白名单运算符与白名单函数调用，
    其余节点类型（属性访问、下标、推导式等）一律拒绝。

    参数:
        node: AST节点

    返回:
        Any: 求值结果

    异常:
        CalcError: 节点类型不被允许或求值越界
    """
    match node:
        case ast.Constant(value=int() | float() as value):
            return value
        case ast.Name(id=name) if name in _CONSTS:
            return _CONSTS[name]
        case ast.UnaryOp(op=op) if type(op) in _UNARY_OPS:
            return _UNARY_OPS[type(op)](_eval_node(node.operand))
        case ast.BinOp(op=op) if type(op) in _BIN_OPS:
            left = _eval_node(node.left)
            right = _eval_node(node.right)
            if isinstance(op, ast.Pow) and (
                abs(right) > _MAX_POWER_EXPONENT
            ):
                raise CalcError("幂运算指数过大")
            return _BIN_OPS[type(op)](left, right)
        case ast.Call(func=ast.Name(id=fname)) if fname in _FUNCS:
            if node.keywords:
                raise CalcError("不支持关键字参数")
            args = [_eval_node(arg) for arg in node.args]
            return _FUNCS[fname](*args)
        case ast.Tuple(elts=elts) | ast.List(elts=elts):
            return [_eval_node(e) for e in elts]
        case _:
            raise CalcError(
                f"不支持的表达式成分: {type(node).__name__}"
            )


def calculate(expression: str) -> str:
    """安全求值数学表达式

    参数:
        expression: 数学表达式，如 "(1+2)*3/7"

    返回:
        str: 计算结果文本，非法表达式返回原因说明
    """
    expr = (expression or "").strip()
    if not expr:
        return "请提供要计算的表达式"
    if len(expr) > _MAX_EXPR_LENGTH:
        return f"表达式过长，最多{_MAX_EXPR_LENGTH}字符"

    # 表达式来自模型生成，语法与数值异常属预期输入错误，
    # 需转为可读提示回传给模型自我纠正，不向上抛出。
    try:
        tree = ast.parse(expr, mode="eval")
        value = _eval_node(tree.body)
    except CalcError as e:
        return f"表达式不合法: {e}"
    except SyntaxError:
        return "表达式语法错误"
    except (ArithmeticError, ValueError, TypeError) as e:
        return f"计算失败: {e}"

    return f"{expr} = {_format_value(value)}"


def _format_value(value: Any) -> str:
    """格式化计算结果

    浮点数去掉无意义的尾随零，整数原样输出。

    参数:
        value: 计算结果

    返回:
        str: 结果文本
    """
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return f"{value:.10g}"
    return str(value)


def build_calculator_tool(runtime: Any) -> AgentTool:
    """构建计算工具

    参数:
        runtime: SkillRuntime 实例，本技能不依赖其服务

    返回:
        AgentTool: 计算工具
    """

    async def _handler(expression: str) -> str:
        """计算handler

        参数:
            expression: 数学表达式

        返回:
            str: 计算结果
        """
        return calculate(expression)

    return AgentTool(
        name="calculate",
        description=(
            "精确计算数学表达式，支持四则运算、幂、开方、对数、"
            "三角函数、阶乘。涉及数字运算时必须调用本工具而非心算"
        ),
        parameters={
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": (
                        "数学表达式，如 (1+2)*3/7、sqrt(2)、"
                        "factorial(10)"
                    ),
                },
            },
            "required": ["expression"],
        },
        func=_handler,
        intent_tags=[INTENT_TAG_LOCAL],
        latency_class=LATENCY_CLASS_FAST,
        evidence_kind=EVIDENCE_KIND_TOOL,
    )
