from liuying.configs.config import Config

base_config = Config.get("bank")

CURRENCY_NAMES: dict[str, str] = {
    "金币": "gold",
    "银币": "silver",
    "铜币": "copper",
}

CURRENCY_DISPLAY: dict[str, str] = {
    "gold": "金币",
    "silver": "银币",
    "copper": "铜币",
}

TREASURY_NAMES: dict[str, str] = {
    "gold": "gold_treasury",
    "silver": "silver_treasury",
    "copper": "copper_treasury",
}

FIXED_PERIOD_MULTIPLIERS: dict[int, float] = {
    7: 1.5,
    30: 2.0,
    90: 3.0,
}

VALID_LOAN_PERIODS: list[int] = [7, 30, 90]

EXCHANGE_SOURCE: dict[str, str] = {
    "silver": "gold",
    "copper": "silver",
}


def parse_currency(currency_str: str | None) -> tuple[str, int | None]:
    """解析货币类型参数

    参数:
        currency_str: 货币类型字符串

    返回:
        tuple[str, int | None]: (货币类型, 数字金额或None)
    """
    if currency_str is None:
        return "gold", None
    if currency_str in CURRENCY_NAMES:
        return CURRENCY_NAMES[currency_str], None
    if currency_str.isdigit():
        return "gold", int(currency_str)
    return "gold", None
