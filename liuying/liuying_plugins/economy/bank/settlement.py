"""银行利息结算服务模块

提供每日活期利息结算、定期存款到期处理。
支持多币种（金/银/铜）利息计算及利息税扣除。
"""

import random

from liuying.models._log.bank_log import BankLog
from liuying.models._user.bank_user import BankUser
from liuying.models.treasury import Treasury
from liuying.utils.enum import BankHandleType

from .account import AccountService
from .constants import TREASURY_NAMES, base_config
from .wallet import WalletService


class SettlementService:
    """银行利息结算服务类

    每日定时任务调用，结算多币种活期利息、未完成存款单利息，
    并处理到期定期存款。支持利息税扣除与国库归集。
    """

    @staticmethod
    async def settle_daily_interest() -> None:
        """结算每日利息（支持多币种，含利息税和定期存款到期处理）"""
        bank_users = await BankUser.filter().all()

        user_data: dict[str, dict] = {}
        for bank_user in bank_users:
            user_data[bank_user.user_id] = {
                "bank_user": bank_user,
                "gold_base": bank_user.amount,
                "silver_base": bank_user.silver_amount,
                "copper_base": bank_user.copper_amount,
            }

        deposit_logs = await BankLog.filter(
            BankLog.is_completed == False,  # noqa: E712
            BankLog.handle_type == BankHandleType.DEPOSIT.value,
        ).all()

        for log in deposit_logs:
            uid = log.user_id
            if uid not in user_data:
                bank_user = await WalletService.get_user(uid)
                user_data[uid] = {
                    "bank_user": bank_user,
                    "gold_base": bank_user.amount,
                    "silver_base": bank_user.silver_amount,
                    "copper_base": bank_user.copper_amount,
                }
            match log.currency_type:
                case "gold":
                    user_data[uid]["gold_base"] -= log.amount
                case "silver":
                    user_data[uid]["silver_base"] -= log.amount
                case "copper":
                    user_data[uid]["copper_base"] -= log.amount

        tax_rate: float = base_config.get("interest_tax_rate", 0.0)
        tax_threshold: int = base_config.get("interest_tax_threshold", 1000000)

        for uid, data in user_data.items():
            bank_user = data["bank_user"]
            total_deposit = AccountService.get_total_deposit_value(bank_user)

            if data["gold_base"] > 0:
                await SettlementService._settle_currency_interest(
                    uid,
                    "gold",
                    data["gold_base"],
                    bank_user.rate,
                    total_deposit,
                    tax_rate,
                    tax_threshold,
                )

            if data["silver_base"] > 0:
                silver_range = AccountService.get_rate_range("silver")
                silver_rate = random.uniform(
                    silver_range[0], silver_range[1]
                )
                await SettlementService._settle_currency_interest(
                    uid,
                    "silver",
                    data["silver_base"],
                    silver_rate,
                    total_deposit,
                    tax_rate,
                    tax_threshold,
                )

            if data["copper_base"] > 0:
                copper_range = AccountService.get_rate_range("copper")
                copper_rate = random.uniform(
                    copper_range[0], copper_range[1]
                )
                await SettlementService._settle_currency_interest(
                    uid,
                    "copper",
                    data["copper_base"],
                    copper_rate,
                    total_deposit,
                    tax_rate,
                    tax_threshold,
                )

        for log in deposit_logs:
            interest = int(log.amount * log.rate * log.effective_hour) or 1
            uid = log.user_id
            total_deposit = 0
            if uid in user_data:
                total_deposit = AccountService.get_total_deposit_value(
                    user_data[uid]["bank_user"]
                )
            net = AccountService.apply_interest_tax(
                interest, total_deposit, tax_rate, tax_threshold
            )
            tax = interest - net
            await WalletService.add(
                uid, log.currency_type, net, "bank_interest"
            )
            if tax > 0:
                treasury_name = TREASURY_NAMES.get(
                    log.currency_type, "gold_treasury"
                )
                await Treasury.increase_treasury_money(tax, treasury_name)
            log.is_completed = True
            await log.save()
            await BankLog.create(
                user_id=uid,
                amount=net,
                rate=log.rate,
                handle_type=BankHandleType.INTEREST.value,
                is_completed=True,
                currency_type=log.currency_type,
            )

        await AccountService.settle_fixed_deposits(user_data)

    @staticmethod
    async def _settle_currency_interest(
        uid: str,
        currency: str,
        base: int,
        rate: float,
        total_deposit: int,
        tax_rate: float,
        tax_threshold: int,
    ) -> None:
        """计算并发放指定币种的活期利息

        参数:
            uid: 用户ID
            currency: 货币类型 (gold/silver/copper)
            base: 计息基数
            rate: 利率
            total_deposit: 用户总存款价值（用于利息税起征判断）
            tax_rate: 利息税率
            tax_threshold: 利息税起征点
        """
        interest = int(base * rate)
        if interest <= 0:
            return
        net = AccountService.apply_interest_tax(
            interest, total_deposit, tax_rate, tax_threshold
        )
        tax = interest - net
        await WalletService.add(uid, currency, net, "bank_interest")
        if tax > 0:
            treasury_name = TREASURY_NAMES.get(currency, "gold_treasury")
            await Treasury.increase_treasury_money(tax, treasury_name)
        await BankLog.create(
            user_id=uid,
            amount=net,
            rate=rate,
            handle_type=BankHandleType.INTEREST.value,
            is_completed=True,
            currency_type=currency,
        )
