"""基于 AST 白名单的安全数学表达式计算器。

不使用 eval，只允许数字、四则运算、幂、括号和少量常量，
并对指数与结果大小进行限制，防止资源耗尽类攻击。
"""

import ast
import math
import operator


_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_UNARY_OPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}

_CONSTANTS = {
    "pi": math.pi,
    "e": math.e,
}

MAX_EXPRESSION_LENGTH = 200
MAX_NODE_COUNT = 100
MAX_ABS_POW_EXPONENT = 1000
MAX_ABS_RESULT = 10 ** 15


class CalculationError(ValueError):
    """表达式不合法或超出计算限制。"""


def _check_magnitude(value):
    if not isinstance(value, (int, float)):
        raise CalculationError("计算结果不是数字")
    if isinstance(value, complex) or abs(value) > MAX_ABS_RESULT:
        raise CalculationError("计算结果超出允许范围")
    return value


def _eval_node(node, node_counter):
    node_counter["count"] += 1
    if node_counter["count"] > MAX_NODE_COUNT:
        raise CalculationError("表达式过于复杂")

    if isinstance(node, ast.Expression):
        return _eval_node(node.body, node_counter)

    if isinstance(node, ast.Constant) and isinstance(
        node.value, (int, float)
    ):
        return _check_magnitude(node.value)

    if isinstance(node, ast.Name) and node.id in _CONSTANTS:
        return _CONSTANTS[node.id]

    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        operand = _eval_node(node.operand, node_counter)
        return _check_magnitude(_UNARY_OPS[type(node.op)](operand))

    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        left = _eval_node(node.left, node_counter)
        right = _eval_node(node.right, node_counter)

        if isinstance(node.op, ast.Pow):
            if abs(right) > MAX_ABS_POW_EXPONENT:
                raise CalculationError("幂指数过大")
            if isinstance(right, float) and left < 0:
                raise CalculationError("不支持负数的分数次幂")

        if isinstance(node.op, (ast.Div, ast.FloorDiv, ast.Mod)):
            if right == 0:
                raise CalculationError("除数不能为 0")

        return _check_magnitude(_BINOPS[type(node.op)](left, right))

    raise CalculationError("表达式中包含不允许的语法")


def safe_calculate(expression: str) -> str:
    """计算数学表达式，返回字符串结果；非法表达式抛 CalculationError。"""
    if not isinstance(expression, str):
        raise CalculationError("表达式必须是字符串")

    expression = expression.strip()
    if not expression:
        raise CalculationError("表达式为空")
    if len(expression) > MAX_EXPRESSION_LENGTH:
        raise CalculationError("表达式过长")

    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise CalculationError(f"表达式语法错误：{exc.msg}") from exc

    result = _eval_node(tree, {"count": 0})
    if isinstance(result, float) and result.is_integer():
        result = int(result)
    return str(result)
