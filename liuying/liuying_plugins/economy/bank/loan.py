from datetime import datetime, timedelta

from liuying.models._log.bank_log import BankLog
from liuying.models._user.bank_user import BankUser
from liuying.models._user.user_info import UserInfo
from liuying.utils.enum import BankHandleType

from .constants import VALID_LOAN_PERIODS, base_config
from .wallet import WalletService


class LoanService:
    """贷款服务：贷款申请、还款、贷款查询"""

    @staticmethod
    async def check(
        user_id: str,
        amount: int,
        period_days: int,
    ) -> str | None:
        """检查贷款是否合法

        参数:
            user_id: 用户id
            amount: 贷款金额
            period_days: 贷款期限（7/30/90天）

        返回:
            str | None: 错误信息，如果合法则返回None
        """
        if amount <= 0:
            return "贷款金额必须大于 0！"

        if period_days not in VALID_LOAN_PERIODS:
            periods = "、".join(str(p) for p in VALID_LOAN_PERIODS)
            return f"不支持的贷款期限，支持期限：{periods}天"

        bank_user = await WalletService.get_user(user_id)
        if bank_user.loan_amount > 0:
            return (
                f"你已有未还清的贷款，当前贷款余额为："
                f"{bank_user.loan_amount}。请先还清后再申请新贷款。"
            )

        user = await UserInfo.get_user(user_id)
        max_loan: int = base_config.get("max_loan_amount", 10000)
        loan_limit = user.favor_value * max_loan
        if amount > loan_limit:
            return (
                f"贷款金额超过上限，你的贷款额度为：{loan_limit}"
                f"（好感度等级{user.favor_value} x {max_loan}）。"
            )

        return None

    @staticmethod
    async def apply(
        user_id: str,
        amount: int,
        period_days: int,
    ) -> tuple[BankUser, float, datetime]:
        """申请银行贷款

        参数:
            user_id: 用户id
            amount: 贷款金额
            period_days: 贷款期限（7/30/90天）

        返回:
            tuple[BankUser, float, datetime]:
                银行用户实例，贷款日利率，到期时间
        """
        loan_rate: float = base_config.get("loan_rate", 0.001)

        bank_user = await WalletService.get_user(user_id)
        bank_user.loan_amount = amount
        bank_user.loan_rate = loan_rate
        bank_user.loan_due_date = datetime.now() + timedelta(days=period_days)
        bank_user.update_time = datetime.now()
        await bank_user.save()

        await WalletService.add(user_id, "gold", amount, "bank_loan")

        await BankLog.create(
            user_id=user_id,
            amount=amount,
            rate=loan_rate,
            handle_type=BankHandleType.LOAN.value,
            currency_type="gold",
        )

        return bank_user, loan_rate, bank_user.loan_due_date

    @staticmethod
    async def repay(user_id: str, amount: int) -> tuple[BankUser, int]:
        """偿还银行贷款

        参数:
            user_id: 用户id
            amount: 还款金额

        返回:
            tuple[BankUser, int]: 银行用户实例，实际还款金额
        """
        bank_user = await WalletService.get_user(user_id)

        if bank_user.loan_amount <= 0:
            raise ValueError("你当前没有未还清的贷款。")

        actual_repay = min(amount, bank_user.loan_amount)

        await WalletService.reduce(user_id, "gold", actual_repay, "bank_repay")

        bank_user.loan_amount -= actual_repay
        if bank_user.loan_amount <= 0:
            bank_user.loan_amount = 0
            bank_user.loan_rate = 0.0
            bank_user.loan_due_date = None
        bank_user.update_time = datetime.now()
        await bank_user.save()

        await BankLog.create(
            user_id=user_id,
            amount=actual_repay,
            rate=0.0,
            handle_type=BankHandleType.REPAYMENT.value,
            currency_type="gold",
        )

        return bank_user, actual_repay

    @staticmethod
    async def get_info(user_id: str) -> dict:
        """获取用户贷款信息

        参数:
            user_id: 用户id

        返回:
            dict: 贷款信息字典
        """
        bank_user = await WalletService.get_user(user_id)
        return {
            "loan_amount": bank_user.loan_amount,
            "loan_rate": bank_user.loan_rate,
            "loan_due_date": (
                str(bank_user.loan_due_date) if bank_user.loan_due_date else None
            ),
        }
