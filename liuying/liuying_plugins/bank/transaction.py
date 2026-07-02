from liuying.models._log.bank_log import BankLog
from liuying.models._user.bank_user import BankUser
from liuying.models.treasury import Treasury
from liuying.utils.enum import BankHandleType

from .constants import CURRENCY_DISPLAY, EXCHANGE_SOURCE, TREASURY_NAMES, base_config
from .wallet import WalletService


class TransactionService:
    """交易服务：货币兑换、用户间转账"""

    @staticmethod
    async def exchange_check(
        user_id: str, target_currency: str, amount: int
    ) -> str | None:
        """检查兑换是否合法

        参数:
            user_id: 用户id
            target_currency: 目标货币类型 (silver/copper)
            amount: 兑换目标数量

        返回:
            str | None: 错误信息，如果合法则返回None
        """
        if target_currency not in EXCHANGE_SOURCE:
            return "只能兑换银币或铜币，不支持反向兑换！"

        if amount <= 0:
            return "兑换数量必须大于 0！"

        source_currency = EXCHANGE_SOURCE[target_currency]
        rate = TransactionService.get_exchange_rate(target_currency)
        source_cost = (amount + rate - 1) // rate

        source_display = CURRENCY_DISPLAY.get(source_currency, "")
        target_display = CURRENCY_DISPLAY.get(target_currency, "")

        wallet_bal = await WalletService.get_balance(user_id, source_currency)
        if wallet_bal < source_cost:
            return (
                f"{source_display}不足，兑换{amount}{target_display}"
                f"需要{source_cost}{source_display}，"
                f"当前{source_display}：{wallet_bal}。"
            )

        return None

    @staticmethod
    def get_exchange_rate(target_currency: str) -> int:
        """获取兑换比例

        参数:
            target_currency: 目标货币类型

        返回:
            int: 兑换比例
        """
        match target_currency:
            case "silver":
                return base_config.get("gold_to_silver_rate", 100)
            case "copper":
                return base_config.get("silver_to_copper_rate", 100)
            case _:
                return 100

    @staticmethod
    async def exchange(
        user_id: str, target_currency: str, amount: int
    ) -> tuple[str, int, int]:
        """执行货币兑换

        参数:
            user_id: 用户id
            target_currency: 目标货币类型 (silver/copper)
            amount: 兑换目标数量

        返回:
            tuple[str, int, int]:
                (源货币类型, 消耗数量, 获得数量)
        """
        source_currency = EXCHANGE_SOURCE[target_currency]
        rate = TransactionService.get_exchange_rate(target_currency)
        source_cost = (amount + rate - 1) // rate
        actual_target = source_cost * rate

        await WalletService.reduce(
            user_id, source_currency, source_cost, "bank_exchange"
        )
        await WalletService.add(
            user_id, target_currency, actual_target, "bank_exchange"
        )

        return source_currency, source_cost, actual_target

    @staticmethod
    async def transfer_check(
        from_user_id: str,
        to_user_id: str,
        amount: int,
        currency: str = "gold",
    ) -> str | None:
        """检查转账是否合法

        参数:
            from_user_id: 发起转账的用户id
            to_user_id: 接收转账的用户id
            amount: 转账金额
            currency: 货币类型 (gold/silver/copper)

        返回:
            str | None: 错误信息，如果合法则返回None
        """
        if from_user_id == to_user_id:
            return "不能给自己转账哦..."

        if amount <= 0:
            return "转账数量必须大于 0 啊笨蛋！"

        if currency not in CURRENCY_DISPLAY:
            supported = "、".join(CURRENCY_DISPLAY.values())
            return f"不支持的货币类型，支持的类型：{supported}"

        display = CURRENCY_DISPLAY.get(currency, "金币")
        balance = await BankUser.get_balance(from_user_id, currency)

        if balance < amount:
            return f"银行{display}余额不足，" f"当前你的银行存款为：{balance}。"

        return None

    @staticmethod
    def calc_transfer_fee(amount: int) -> tuple[int, float]:
        """计算转账手续费

        参数:
            amount: 转账金额

        返回:
            tuple[int, float]: (手续费, 手续费率)
        """
        fee_rate: float = base_config.get("transfer_fee_rate", 0.01)
        fee_rate = min(max(fee_rate, 0.0), 0.03)
        fee = max(int(amount * fee_rate), 1)
        return fee, fee_rate

    @staticmethod
    async def transfer(
        from_user_id: str,
        to_user_id: str,
        amount: int,
        currency: str = "gold",
    ) -> tuple[int, int]:
        """执行银行转账操作

        参数:
            from_user_id: 发起转账的用户id
            to_user_id: 接收转账的用户id
            amount: 转账金额
            currency: 货币类型 (gold/silver/copper)

        返回:
            tuple[int, int]: (实际到账金额, 手续费)
        """
        fee_rate: float = base_config.get("transfer_fee_rate", 0.01)
        fee_rate = min(max(fee_rate, 0.0), 0.03)
        fee = max(int(amount * fee_rate), 1)
        actual_receive = amount - fee

        await BankUser.withdraw(from_user_id, amount, currency)
        await BankUser.deposit(to_user_id, actual_receive, 0, currency)

        if fee > 0:
            treasury_name = TREASURY_NAMES.get(currency, "gold_treasury")
            await Treasury.increase_treasury_money(fee, treasury_name)

        for log_user_id in (from_user_id, to_user_id):
            await BankLog.create(
                user_id=log_user_id,
                amount=amount,
                rate=0.0,
                handle_type=BankHandleType.TRANSFER.value,
                currency_type=currency,
            )

        return actual_receive, fee
