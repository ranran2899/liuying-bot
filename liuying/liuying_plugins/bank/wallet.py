from liuying.models._user.bank_user import BankUser
from liuying.models._user.user_curr import UserCurr
from liuying.models._user.user_info import UserInfo
from liuying.models.treasury import Treasury

from .constants import TREASURY_NAMES


class WalletService:
    """钱包服务：银行用户查询、钱包余额、资金增减"""

    @staticmethod
    async def get_user(user_id: str) -> BankUser:
        """获取银行用户信息

        参数:
            user_id: 用户id

        返回:
            BankUser: 银行用户实例
        """
        user, _ = await BankUser.get_or_create(user_id=user_id)
        return user

    @staticmethod
    async def get_balance(user_id: str, currency: str) -> int:
        """获取用户银行中指定币种余额

        参数:
            user_id: 用户id
            currency: 货币类型 (gold/silver/copper)

        返回:
            int: 银行余额
        """
        bank_user = await WalletService.get_user(user_id)
        match currency:
            case "gold":
                return bank_user.amount
            case "silver":
                return bank_user.silver_amount
            case "copper":
                return bank_user.copper_amount
            case _:
                return 0

    @staticmethod
    async def get_wallet_balance(user_id: str, currency: str) -> int:
        """获取用户钱包中指定币种余额

        参数:
            user_id: 用户id
            currency: 货币类型 (gold/silver/copper)

        返回:
            int: 钱包余额
        """
        match currency:
            case "gold":
                return await UserInfo.get_user_gold(user_id)
            case "silver":
                return await UserCurr.get_user_silver(user_id)
            case "copper":
                return await UserCurr.get_user_copper(user_id)
            case _:
                return 0

    @staticmethod
    async def reduce(
        user_id: str,
        currency: str,
        amount: int,
        source: str = "bank",
    ) -> None:
        """从用户钱包扣除指定币种

        参数:
            user_id: 用户id
            currency: 货币类型 (gold/silver/copper)
            amount: 扣除金额
            source: 来源标识
        """
        match currency:
            case "gold":
                await UserInfo.reduce_gold(
                    user_id, amount, source
                )
            case "silver":
                await UserCurr.reduce_silver(user_id, amount, source)
            case "copper":
                await UserCurr.reduce_copper(user_id, amount, source)

    @staticmethod
    async def add(
        user_id: str,
        currency: str,
        amount: int,
        source: str = "bank",
    ) -> None:
        """向用户钱包添加指定币种

        参数:
            user_id: 用户id
            currency: 货币类型 (gold/silver/copper)
            amount: 添加金额
            source: 来源标识
        """
        match currency:
            case "gold":
                await UserInfo.add_gold(user_id, amount, source)
            case "silver":
                await UserCurr.add_silver(user_id, amount, source)
            case "copper":
                await UserCurr.add_copper(user_id, amount, source)

    @staticmethod
    async def consume(
        user_id: str,
        currency: str,
        amount: int,
        source: str = "bank",
    ) -> None:
        """从用户银行扣除指定币种并转入钱包

        参数:
            user_id: 用户id
            currency: 货币类型 (gold/silver/copper)
            amount: 扣除金额
            source: 来源标识
        """
        await BankUser.withdraw(user_id, amount, currency)
        await WalletService.add(user_id, currency, amount, source)
        treasury_name = TREASURY_NAMES.get(currency, "gold_treasury")
        await Treasury.decrease_treasury_money(amount, treasury_name)

    @staticmethod
    async def grant(
        user_id: str,
        currency: str,
        amount: int,
        source: str = "bank",
    ) -> None:
        """从用户钱包扣除指定币种并存入银行

        参数:
            user_id: 用户id
            currency: 货币类型 (gold/silver/copper)
            amount: 存入金额
            source: 来源标识
        """
        await WalletService.reduce(user_id, currency, amount, source)
        await BankUser.deposit(user_id, amount, 0, currency)
        treasury_name = TREASURY_NAMES.get(currency, "gold_treasury")
        await Treasury.increase_treasury_money(amount, treasury_name)
