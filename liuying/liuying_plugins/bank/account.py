import asyncio
from datetime import datetime, timedelta
import json
import random

from liuying.models._log.bank_log import BankLog
from liuying.models._user.bank_user import BankUser
from liuying.models._user.user_info import UserInfo
from liuying.models.treasury import Treasury
from liuying.utils.enum import BankHandleType

from .constants import (
    CURRENCY_DISPLAY,
    FIXED_PERIOD_MULTIPLIERS,
    TREASURY_NAMES,
    base_config,
)
from .wallet import WalletService


class AccountService:
    """账户服务：存款、取款、定期存款"""

    @staticmethod
    async def random_event(favor_level: int) -> float | None:
        """随机事件，根据好感度等级触发利率变化

        参数:
            favor_level: 用户好感度等级

        返回:
            float | None: 随机利率变化值
        """
        impression_event = base_config.get("impression_event", 25)
        impression_event_prop = base_config.get("impression_event_prop", 0.3)
        impression_event_range = base_config.get(
            "impression_event_range", [0.00001, 0.0003]
        )
        if (
            favor_level >= impression_event
            and random.random() < impression_event_prop
        ):
            return random.uniform(
                impression_event_range[0], impression_event_range[1]
            )
        return None

    @staticmethod
    def get_deposit_limit(currency: str, favor_value: int) -> int:
        """获取指定货币的存款上限

        参数:
            currency: 货币类型
            favor_value: 用户好感度等级

        返回:
            int: 存款上限金额
        """
        match currency:
            case "gold":
                multiplier = base_config.get("sign_max_deposit", 100)
                return max(favor_value * multiplier, 100)
            case "silver":
                multiplier = base_config.get("sign_max_silver_deposit", 100000)
                return max(favor_value * multiplier, 10000)
            case "copper":
                multiplier = base_config.get("sign_max_copper_deposit", 10000000)
                return max(favor_value * multiplier, 100000)
            case _:
                return 0

    @staticmethod
    def get_rate_range(currency: str) -> list[float]:
        """获取指定币种的利率范围

        参数:
            currency: 货币类型 (gold/silver/copper)

        返回:
            list[float]: 利率范围 [最低, 最高]
        """
        match currency:
            case "gold":
                return base_config.get("rate_range", [0.0005, 0.001])
            case "silver":
                return base_config.get("silver_rate_range", [0.0003, 0.0006])
            case "copper":
                return base_config.get("copper_rate_range", [0.0001, 0.0003])
            case _:
                return [0.0005, 0.001]

    @staticmethod
    def apply_interest_tax(
        interest: int,
        total_deposit: int,
        tax_rate: float,
        tax_threshold: int,
    ) -> int:
        """计算扣除利息税后的净利息

        参数:
            interest: 原始利息
            total_deposit: 用户总存款价值
            tax_rate: 利息税率
            tax_threshold: 利息税起征点

        返回:
            int: 扣税后净利息
        """
        if total_deposit > tax_threshold and tax_rate > 0:
            tax = int(interest * tax_rate)
            return max(interest - tax, 0)
        return interest

    @staticmethod
    def get_total_deposit_value(bank_user: BankUser) -> int:
        """计算用户总存款价值（金币等价）

        参数:
            bank_user: 银行用户实例

        返回:
            int: 总存款价值（金币等价）
        """
        gold_to_silver: int = base_config.get("gold_to_silver_rate", 64)
        silver_to_copper: int = base_config.get("silver_to_copper_rate", 64)
        return (
            bank_user.amount
            + bank_user.silver_amount // gold_to_silver
            + bank_user.copper_amount // (gold_to_silver * silver_to_copper)
        )

    @staticmethod
    async def deposit_check(
        user_id: str, amount: int, currency: str = "gold"
    ) -> str | None:
        """检查存款是否合法

        参数:
            user_id: 用户id
            amount: 存款金额
            currency: 货币类型

        返回:
            str | None: 错误信息，如果合法则返回None
        """
        if amount <= 0:
            return "存款数量必须大于 0 啊笨蛋！"

        user, today_deposit = await asyncio.gather(
            UserInfo.get_user(user_id),
            BankLog.get_user_today_deposit(user_id, currency),
        )

        display = CURRENCY_DISPLAY.get(currency, "金币")
        max_daily_count: int = base_config.get("max_daily_deposit_count", 3)
        if len(today_deposit) >= max_daily_count:
            return (
                f"存款次数超过上限，每日{display}存款次数上限为："
                f"{max_daily_count}。"
            )

        wallet_bal, current_deposit = await asyncio.gather(
            WalletService.get_balance(user_id, currency),
            BankUser.get_balance(user_id, currency),
        )

        if wallet_bal < amount:
            return f"{display}数量不足，当前你的{display}为：" f"{wallet_bal}。"

        max_deposit = AccountService.get_deposit_limit(currency, user.favor_value)
        if current_deposit + amount > max_deposit:
            remaining = max_deposit - current_deposit
            return (
                f"{display}存款超过上限，存款上限为：{max_deposit}，"
                f"当前你还可以存款金额：{remaining}。"
            )

        return None

    @staticmethod
    async def deposit(
        user_id: str,
        amount: int,
        favor_level: int,
        currency: str = "gold",
    ) -> tuple[BankUser, float, float | None]:
        """存款操作

        参数:
            user_id: 用户id
            amount: 存款金额
            favor_level: 用户好感度等级
            currency: 货币类型

        返回:
            tuple[BankUser, float, float | None]:
                银行用户实例，利率，额外利率
        """
        rate = 0.0
        random_add_rate = None
        effective_hour = 0

        rate_range = AccountService.get_rate_range(currency)
        rate = random.uniform(rate_range[0], rate_range[1])

        if currency == "gold":
            random_add_rate = await AccountService.random_event(favor_level)
            if random_add_rate:
                rate += random_add_rate
            effective_hour = 24 - datetime.now().hour

        await WalletService.reduce(user_id, currency, amount, "bank")
        bank_user = await BankUser.deposit(user_id, amount, rate, currency)

        treasury_name = TREASURY_NAMES.get(currency, "gold_treasury")
        await Treasury.increase_treasury_money(amount, treasury_name)

        await BankLog.create(
            user_id=user_id,
            amount=amount,
            rate=rate,
            handle_type=BankHandleType.DEPOSIT.value,
            effective_hour=effective_hour,
            currency_type=currency,
        )

        return bank_user, rate, random_add_rate

    @staticmethod
    async def fixed_deposit(
        user_id: str,
        amount: int,
        currency: str,
        period_days: int,
    ) -> tuple[BankUser, float, int]:
        """定期存款操作

        参数:
            user_id: 用户id
            amount: 存款金额
            currency: 货币类型 (gold/silver/copper)
            period_days: 存款期限（7/30/90天）

        返回:
            tuple[BankUser, float, int]:
                银行用户实例，定期利率，预计利息
        """
        if period_days not in FIXED_PERIOD_MULTIPLIERS:
            raise ValueError(
                f"不支持的存款期限：{period_days}天，" f"支持期限：7、30、90天"
            )

        rate_range = AccountService.get_rate_range(currency)
        base_rate = random.uniform(rate_range[0], rate_range[1])
        multiplier = FIXED_PERIOD_MULTIPLIERS[period_days]
        enhanced_rate = base_rate * multiplier
        total_interest = int(amount * enhanced_rate * period_days)

        await WalletService.reduce(user_id, currency, amount, "fixed_deposit")

        bank_user = await BankUser.get_user(user_id)
        deposits: dict = json.loads(bank_user.fixed_deposits or "{}")

        now = datetime.now()
        end_time = now + timedelta(days=period_days)
        deposit_id = (
            f"{now.strftime('%Y%m%d%H%M%S')}" f"_{random.randint(1000, 9999)}"
        )

        deposits[deposit_id] = {
            "amount": amount,
            "currency": currency,
            "rate": enhanced_rate,
            "start_time": now.isoformat(),
            "end_time": end_time.isoformat(),
            "period_days": period_days,
        }

        bank_user.fixed_deposits = json.dumps(deposits)
        bank_user.update_time = datetime.now()
        await bank_user.save()

        treasury_name = TREASURY_NAMES.get(currency, "gold_treasury")
        await Treasury.increase_treasury_money(amount, treasury_name)

        await BankLog.create(
            user_id=user_id,
            amount=amount,
            rate=enhanced_rate,
            handle_type="FIXED_DEPOSIT",
            effective_hour=period_days * 24,
            currency_type=currency,
        )

        return bank_user, enhanced_rate, total_interest

    @staticmethod
    async def settle_fixed_deposits(
        user_data: dict[str, dict] | None = None,
    ) -> None:
        """处理到期的定期存款

        参数:
            user_data: 用户数据字典，为None时重新查询
        """
        now = datetime.now()
        if user_data is None:
            bank_users = await BankUser.filter().all()
            user_data = {}
            for bank_user in bank_users:
                user_data[bank_user.user_id] = {
                    "bank_user": bank_user,
                }

        for uid, data in user_data.items():
            bank_user = data["bank_user"]
            deposits_str = bank_user.fixed_deposits or "{}"
            deposits: dict = json.loads(deposits_str)
            if not deposits:
                continue

            matured_ids: list[str] = []
            for dep_id, dep_info in deposits.items():
                end_time = datetime.fromisoformat(dep_info["end_time"])
                if end_time <= now:
                    principal = dep_info["amount"]
                    currency = dep_info["currency"]
                    rate = dep_info["rate"]
                    period_days = dep_info["period_days"]
                    interest = int(principal * rate * period_days)

                    await WalletService.add(
                        uid, currency, principal, "fixed_deposit"
                    )
                    if interest > 0:
                        await WalletService.add(
                            uid, currency, interest, "bank_interest"
                        )
                    await BankLog.create(
                        user_id=uid,
                        amount=principal + interest,
                        rate=rate,
                        handle_type=BankHandleType.INTEREST.value,
                        is_completed=True,
                        currency_type=currency,
                    )

                    treasury_name = TREASURY_NAMES.get(currency, "gold_treasury")
                    await Treasury.decrease_treasury_money(principal, treasury_name)

                    matured_ids.append(dep_id)

            if matured_ids:
                for dep_id in matured_ids:
                    del deposits[dep_id]
                bank_user.fixed_deposits = json.dumps(deposits)
                bank_user.update_time = datetime.now()
                await bank_user.save()

    @staticmethod
    async def get_fixed_deposits_info(user_id: str) -> list[dict]:
        """获取用户定期存款信息

        参数:
            user_id: 用户id

        返回:
            list[dict]: 定期存款列表
        """
        bank_user = await BankUser.get_user(user_id)
        deposits: dict = json.loads(bank_user.fixed_deposits or "{}")
        result = []
        for dep_id, dep_info in deposits.items():
            display = CURRENCY_DISPLAY.get(dep_info["currency"], "金币")
            result.append(
                {
                    "id": dep_id,
                    "amount": dep_info["amount"],
                    "currency": dep_info["currency"],
                    "currency_display": display,
                    "rate": dep_info["rate"],
                    "start_time": dep_info["start_time"],
                    "end_time": dep_info["end_time"],
                    "period_days": dep_info["period_days"],
                }
            )
        return result

    @staticmethod
    async def withdraw_check(
        user_id: str, amount: int, currency: str = "gold"
    ) -> str | None:
        """检查取款是否合法

        参数:
            user_id: 用户id
            amount: 取款金额
            currency: 货币类型

        返回:
            str | None: 错误信息，如果合法则返回None
        """
        if amount <= 0:
            return "取款数量必须大于 0 啊笨蛋！"

        display = CURRENCY_DISPLAY.get(currency, "金币")
        balance = await BankUser.get_balance(user_id, currency)

        if currency == "gold":
            today_deposit = await BankLog.get_user_today_deposit(user_id, "gold")
            lock_amount = sum(
                log.amount for log in today_deposit if not log.is_completed
            )
            available = balance - lock_amount
            if available < amount:
                lock_info = f"（{lock_amount}已被锁定）" if lock_amount > 0 else ""
                return (
                    f"取款金额不足，当前你的{display}存款为："
                    f"{available}{lock_info}！"
                )
        elif balance < amount:
            return (
                f"{display}存款不足，当前你的{display}存款为：" f"{balance}。"
            )

        treasury_min_reserve: int = base_config.get("treasury_min_reserve", 100000)
        treasury_name = TREASURY_NAMES.get(currency, "gold_treasury")
        treasury_money = await Treasury.get_treasury_money(treasury_name)
        if treasury_money < treasury_min_reserve:
            max_withdraw = max(int(treasury_money * 0.1), 1)
            if amount > max_withdraw:
                return (
                    f"银行储备不足，当前单次取款上限为："
                    f"{max_withdraw}{display}。"
                )

        return None

    @staticmethod
    async def withdraw(
        user_id: str, amount: int, currency: str = "gold"
    ) -> tuple[BankUser, int]:
        """取款操作

        参数:
            user_id: 用户id
            amount: 取款金额
            currency: 货币类型

        返回:
            tuple[BankUser, int]: 银行用户实例，实际取款金额
        """
        treasury_name = TREASURY_NAMES.get(currency, "gold_treasury")
        treasury_money = await Treasury.get_treasury_money(treasury_name)

        treasury_min_reserve: int = base_config.get("treasury_min_reserve", 100000)
        if treasury_money < treasury_min_reserve:
            max_withdraw = max(int(treasury_money * 0.1), 1)
            actual_amount = min(amount, max_withdraw, treasury_money)
        else:
            actual_amount = min(amount, treasury_money)

        if actual_amount <= 0:
            return await BankUser.get_user(user_id), 0

        await WalletService.add(user_id, currency, actual_amount, "bank")
        bank_user = await BankUser.withdraw(user_id, actual_amount, currency)

        await Treasury.decrease_treasury_money(actual_amount, treasury_name)

        await BankLog.create(
            user_id=user_id,
            amount=actual_amount,
            rate=bank_user.rate if currency == "gold" else 0.0,
            handle_type=BankHandleType.WITHDRAW.value,
            currency_type=currency,
        )

        return bank_user, actual_amount
