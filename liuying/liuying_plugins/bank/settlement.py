import random

from liuying.models._log.bank_log import BankLog
from liuying.models._user.bank_user import BankUser
from liuying.models.treasury import Treasury
from liuying.utils.enum import BankHandleType

from .account import AccountService
from .constants import TREASURY_NAMES, base_config
from .wallet import WalletService


async def settlement() -> None:
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

        gold_base = data["gold_base"]
        if gold_base > 0:
            interest = int(gold_base * bank_user.rate)
            if interest > 0:
                net = AccountService.apply_interest_tax(
                    interest,
                    total_deposit,
                    tax_rate,
                    tax_threshold,
                )
                tax = interest - net
                await WalletService.add(uid, "gold", net, "bank_interest")
                if tax > 0:
                    await Treasury.increase_treasury_money(tax, "gold_treasury")
                await BankLog.create(
                    user_id=uid,
                    amount=net,
                    rate=bank_user.rate,
                    handle_type=BankHandleType.INTEREST.value,
                    is_completed=True,
                    currency_type="gold",
                )

        silver_base = data["silver_base"]
        if silver_base > 0:
            silver_range = AccountService.get_rate_range("silver")
            silver_rate = random.uniform(silver_range[0], silver_range[1])
            interest = int(silver_base * silver_rate)
            if interest > 0:
                net = AccountService.apply_interest_tax(
                    interest,
                    total_deposit,
                    tax_rate,
                    tax_threshold,
                )
                tax = interest - net
                await WalletService.add(uid, "silver", net, "bank_interest")
                if tax > 0:
                    await Treasury.increase_treasury_money(tax, "silver_treasury")
                await BankLog.create(
                    user_id=uid,
                    amount=net,
                    rate=silver_rate,
                    handle_type=BankHandleType.INTEREST.value,
                    is_completed=True,
                    currency_type="silver",
                )

        copper_base = data["copper_base"]
        if copper_base > 0:
            copper_range = AccountService.get_rate_range("copper")
            copper_rate = random.uniform(copper_range[0], copper_range[1])
            interest = int(copper_base * copper_rate)
            if interest > 0:
                net = AccountService.apply_interest_tax(
                    interest,
                    total_deposit,
                    tax_rate,
                    tax_threshold,
                )
                tax = interest - net
                await WalletService.add(uid, "copper", net, "bank_interest")
                if tax > 0:
                    await Treasury.increase_treasury_money(tax, "copper_treasury")
                await BankLog.create(
                    user_id=uid,
                    amount=net,
                    rate=copper_rate,
                    handle_type=BankHandleType.INTEREST.value,
                    is_completed=True,
                    currency_type="copper",
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
        await WalletService.add(uid, log.currency_type, net, "bank_interest")
        if tax > 0:
            treasury_name = TREASURY_NAMES.get(log.currency_type, "gold_treasury")
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
