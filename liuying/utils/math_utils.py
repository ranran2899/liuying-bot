"""数学/统计工具模块

提供概率计算、随机选择、统计等数学相关功能
"""
import math
import random
from typing import Any


class MathUtils:
    """数学/统计工具类"""

    @classmethod
    def weighted_random_choice(cls, items: list[Any], weights: list[float]) -> Any:
        """根据权重随机选择

        参数:
            items: 候选项列表
            weights: 权重列表

        返回:
            Any: 选中的项
        """
        if not items or not weights:
            raise ValueError("items 和 weights 不能为空")
        if len(items) != len(weights):
            raise ValueError("items 和 weights 长度必须一致")
        return random.choices(items, weights=weights, k=1)[0]

    @classmethod
    def probability_success(cls, probability: float) -> bool:
        """根据概率判断是否成功

        参数:
            probability: 成功概率（0.0-1.0）

        返回:
            bool: 是否成功
        """
        if not 0.0 <= probability <= 1.0:
            raise ValueError("概率必须在 0.0 到 1.0 之间")
        return random.random() < probability

    @classmethod
    def clamp(cls, value: float, min_value: float, max_value: float) -> float:
        """限制数值在指定范围内

        参数:
            value: 要限制的数值
            min_value: 最小值
            max_value: 最大值

        返回:
            float: 限制后的数值
        """
        return max(min_value, min(value, max_value))

    @classmethod
    def calculate_percentage(cls, part: float, whole: float) -> float:
        """计算百分比

        参数:
            part: 部分值
            whole: 总值

        返回:
            float: 百分比值
        """
        return (part / whole) * 100 if whole else 0.0

    @classmethod
    def calculate_average(cls, numbers: list[float]) -> float:
        """计算平均值

        参数:
            numbers: 数值列表

        返回:
            float: 平均值
        """
        return sum(numbers) / len(numbers) if numbers else 0.0

    @classmethod
    def calculate_median(cls, numbers: list[float]) -> float:
        """计算中位数

        参数:
            numbers: 数值列表

        返回:
            float: 中位数
        """
        if not numbers:
            return 0.0
        sorted_nums = sorted(numbers)
        n = len(sorted_nums)
        mid = n // 2
        if n % 2 == 0:
            return (sorted_nums[mid - 1] + sorted_nums[mid]) / 2
        return sorted_nums[mid]

    @classmethod
    def calculate_std_dev(cls, numbers: list[float]) -> float:
        """计算标准差

        参数:
            numbers: 数值列表

        返回:
            float: 标准差
        """
        if not numbers:
            return 0.0
        avg = cls.calculate_average(numbers)
        variance = sum((x - avg) ** 2 for x in numbers) / len(numbers)
        return variance**0.5

    @classmethod
    def format_number(cls, num: float, precision: int = 2) -> str:
        """格式化数值（添加千位分隔符）

        参数:
            num: 要格式化的数值
            precision: 小数位数

        返回:
            str: 格式化后的字符串
        """
        return f"{num:,.{precision}f}"

    @classmethod
    def format_large_number(cls, num: float) -> str:
        """格式化大数值（使用单位缩写）

        参数:
            num: 要格式化的数值

        返回:
            str: 格式化后的字符串
        """
        abs_num = abs(num)
        sign = "-" if num < 0 else ""

        thresholds = [
            (1_000_000_000_000, "T"),
            (1_000_000_000, "B"),
            (1_000_000, "M"),
            (1_000, "K"),
        ]
        for threshold, suffix in thresholds:
            if abs_num >= threshold:
                return f"{sign}{num / threshold:.1f}{suffix}"
        return f"{sign}{int(num)}"

    @classmethod
    def calculate_growth_rate(cls, old_value: float, new_value: float) -> float:
        """计算增长率

        参数:
            old_value: 旧值
            new_value: 新值

        返回:
            float: 增长率（百分比）
        """
        if old_value == 0:
            return 0.0 if new_value == 0 else float("inf")
        return ((new_value - old_value) / abs(old_value)) * 100

    @classmethod
    def random_range(cls, min_val: float, max_val: float) -> int | float:
        """随机范围数（整数范围返回整数，浮点范围返回浮点）

        参数:
            min_val: 最小值
            max_val: 最大值

        返回:
            int | float: 随机数
        """
        if isinstance(min_val, int) and isinstance(max_val, int):
            return random.randint(min_val, max_val)
        return random.uniform(min_val, max_val)

    @classmethod
    def calculate_variance(cls, numbers: list[float]) -> float:
        """计算方差

        参数:
            numbers: 数值列表

        返回:
            float: 方差
        """
        if not numbers:
            return 0.0
        avg = cls.calculate_average(numbers)
        return sum((x - avg) ** 2 for x in numbers) / len(numbers)

    @classmethod
    def calculate_combinations(cls, n: int, k: int) -> int:
        """计算组合数 C(n, k)

        参数:
            n: 总数
            k: 选择数

        返回:
            int: 组合数
        """
        if k > n or k < 0:
            return 0
        if k == 0 or k == n:
            return 1
        k = min(k, n - k)
        result = 1
        for i in range(k):
            result = result * (n - i) // (i + 1)
        return result

    @classmethod
    def calculate_factorial(cls, n: int) -> int:
        """计算阶乘

        参数:
            n: 数值

        返回:
            int: 阶乘结果
        """
        if n < 0:
            raise ValueError("阶乘不支持负数")
        return math.factorial(n)

    @classmethod
    def safe_divide(
        cls,
        numerator: float,
        denominator: float,
        default: float = 0.0,
    ) -> float:
        """安全除法，避免除零错误

        参数:
            numerator: 分子
            denominator: 分母
            default: 分母为零时的默认值

        返回:
            float: 除法结果
        """
        return numerator / denominator if denominator else default

    @classmethod
    def calculate_distance(cls, x1: float, y1: float, x2: float, y2: float) -> float:
        """计算两点间的欧几里得距离

        参数:
            x1: 第一个点的x坐标
            y1: 第一个点的y坐标
            x2: 第二个点的x坐标
            y2: 第二个点的y坐标

        返回:
            float: 两点间的距离
        """
        return math.hypot(x2 - x1, y2 - y1)

    @classmethod
    def interpolate(cls, start: float, end: float, t: float) -> float:
        """线性插值

        参数:
            start: 起始值
            end: 结束值
            t: 插值因子（0.0-1.0）

        返回:
            float: 插值结果
        """
        t = cls.clamp(t, 0.0, 1.0)
        return start + (end - start) * t
