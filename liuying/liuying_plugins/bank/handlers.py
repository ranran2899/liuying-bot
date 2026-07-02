from datetime import datetime

from nonebot_plugin_alconna import Arparma, Match
from nonebot_plugin_uninfo import Uninfo

from liuying.configs.config import NICKNAME
from liuying.models._user.user_info import UserInfo
from liuying.ui import render
from liuying.utils.log import logger
from liuying.utils.message import MessageUtils
from liuying.utils.user import UserUid

from .account import AccountService
from .constants import (
    CURRENCY_DISPLAY,
    CURRENCY_NAMES,
    EXCHANGE_SOURCE,
    FIXED_PERIOD_MULTIPLIERS,
    parse_currency,
)
from .info import InfoService
from .loan import LoanService
from .transaction import TransactionService


class BankHandler:
    """银行命令处理器"""

    @staticmethod
    def _resolve_currency_and_amount(
        currency_match: Match[str], amount_match: Match[int]
    ) -> tuple[str, int | None, str | None]:
        """解析货币类型和金额参数

        参数:
            currency_match: 货币类型匹配结果
            amount_match: 金额匹配结果

        返回:
            tuple[str, int | None, str | None]: (货币类型, 金额, 错误信息)
        """
        currency_type = "gold"
        amount_num = None

        if currency_match.available and currency_match.result:
            parsed_currency, parsed_amount = parse_currency(currency_match.result)
            if parsed_amount is not None:
                amount_num = parsed_amount
            else:
                currency_type = parsed_currency

        if amount_match and amount_match.available:
            amount_num = amount_match.result

        if currency_type not in CURRENCY_DISPLAY:
            supported = "、".join(CURRENCY_NAMES.keys())
            return "gold", None, f"不支持的货币类型，支持的类型：{supported}"

        return currency_type, amount_num, None

    @staticmethod
    async def deposit(
        session: Uninfo,
        arparma: Arparma,
        currency: Match[str],
        amount: Match[int],
    ) -> None:
        """处理存款命令"""
        user_id = session.user.id

        currency_type, amount_num, error = (
            BankHandler._resolve_currency_and_amount(currency, amount)
        )

        if error:
            await MessageUtils.build_message(error).finish(reply_to=True)

        if amount_num is None:
            await MessageUtils.build_message(
                "请输入存款金额，例如：存款 金币 100"
            ).finish(reply_to=True)

        display = CURRENCY_DISPLAY.get(currency_type, "金币")

        if result := await AccountService.deposit_check(
            user_id, amount_num, currency_type
        ):
            await MessageUtils.build_message(result).finish(reply_to=True)

        user = await UserInfo.get_user(user_id)
        _, rate, event_rate = await AccountService.deposit(
            user_id, amount_num, user.favor_value, currency_type
        )

        result = f"存款成功！\n此次存款{display}金额为: {amount_num}"

        if currency_type == "gold":
            result += f"\n当前小时利率为: {rate * 100:.2f}%"
            effective_hour = 24 - datetime.now().hour
            if event_rate:
                result += (
                    f"（{NICKNAME}偷偷将小时利率给你增加了"
                    f" {event_rate * 100:.2f}% 哦）"
                )
            revenue = int(amount_num * rate * effective_hour) or 1
            result += f"\n预计总收益为: {revenue} 金币。"

        logger.info(
            f"银行存款:{amount_num}{display}, 存款小时利率: {rate}",
            arparma.header_result,
            session=session,
        )
        await MessageUtils.build_message(result).finish(at_sender=True)

    @staticmethod
    async def withdraw(
        session: Uninfo,
        arparma: Arparma,
        currency: Match[str],
        amount: Match[int],
    ) -> None:
        """处理取款命令"""
        user_id = session.user.id

        currency_type, amount_num, error = (
            BankHandler._resolve_currency_and_amount(currency, amount)
        )

        if error:
            await MessageUtils.build_message(error).finish(reply_to=True)

        if amount_num is None:
            await MessageUtils.build_message(
                "请输入取款金额，例如：取款 金币 100"
            ).finish(reply_to=True)

        display = CURRENCY_DISPLAY.get(currency_type, "金币")

        if result := await AccountService.withdraw_check(
            user_id, amount_num, currency_type
        ):
            await MessageUtils.build_message(result).finish(reply_to=True)

        try:
            bank_user, actual_amount = await AccountService.withdraw(
                user_id, amount_num, currency_type
            )

            if actual_amount <= 0:
                await MessageUtils.build_message(
                    f"银行{display}储备不足，当前无法取款。"
                ).finish(reply_to=True)

            match currency_type:
                case "gold":
                    deposit_display = bank_user.amount
                case "silver":
                    deposit_display = bank_user.silver_amount
                case "copper":
                    deposit_display = bank_user.copper_amount
                case _:
                    deposit_display = 0

            result = (
                f"取款成功！\n当前取款{display}金额为: {actual_amount}\n"
                f"当前{display}存款金额为: {deposit_display}"
            )

            if actual_amount < amount_num:
                result += (
                    f"\n银行{display}储备不足，"
                    f"仅能取出 {actual_amount} {display}。"
                )

            logger.info(
                f"银行取款:{actual_amount}{display}, "
                f"当前存款数:{deposit_display}",
                arparma.header_result,
                session=session,
            )
            await MessageUtils.build_message(result).finish(reply_to=True)
        except ValueError:
            await MessageUtils.build_message(
                "你的银行内的存款数量不足哦..."
            ).finish(reply_to=True)

    @staticmethod
    async def exchange(
        session: Uninfo,
        arparma: Arparma,
        currency: Match[str],
        amount: Match[int],
    ) -> None:
        """处理兑换命令"""
        user_id = session.user.id

        if not currency.available or not currency.result:
            await MessageUtils.build_message(
                "请指定兑换的货币类型，例如：银行兑换 银币 100"
            ).finish(reply_to=True)

        currency_type, _, error = (
            BankHandler._resolve_currency_and_amount(currency, None)
        )
        if error:
            await MessageUtils.build_message(error).finish(reply_to=True)

        if currency_type not in EXCHANGE_SOURCE:
            await MessageUtils.build_message(
                "只能兑换银币或铜币，不支持反向兑换！"
            ).finish(reply_to=True)

        if not amount.available or amount.result is None:
            await MessageUtils.build_message(
                "请输入兑换数量，例如：银行兑换 银币 100"
            ).finish(reply_to=True)

        amount_num = amount.result

        if result := await TransactionService.exchange_check(
            user_id, currency_type, amount_num
        ):
            await MessageUtils.build_message(result).finish(reply_to=True)

        source_currency, source_cost, actual_target = (
            await TransactionService.exchange(user_id, currency_type, amount_num)
        )

        source_display = CURRENCY_DISPLAY.get(source_currency, "")
        target_display = CURRENCY_DISPLAY.get(currency_type, "")

        result = (
            f"兑换成功！\n"
            f"消耗{source_display}：{source_cost}\n"
            f"获得{target_display}：{actual_target}"
        )

        logger.info(
            f"银行兑换:消耗{source_cost}{source_display},"
            f"获得{actual_target}{target_display}",
            arparma.header_result,
            session=session,
        )
        await MessageUtils.build_message(result).finish(at_sender=True)

    @staticmethod
    async def transfer(
        session: Uninfo,
        arparma: Arparma,
        uid: Match[str],
        currency: Match[str],
        amount: Match[int],
    ) -> None:
        """处理用户间转账命令"""
        user_id = session.user.id

        if not uid.available or not uid.result:
            await MessageUtils.build_message(
                "请输入要转账的用户UID，例如：转账 100000001 金币 500"
            ).finish(reply_to=True)

        if not currency.available or not currency.result:
            await MessageUtils.build_message(
                "请指定货币类型，例如：转账 100000001 金币 500"
            ).finish(reply_to=True)

        if not amount.available or amount.result is None:
            await MessageUtils.build_message(
                "请输入转账数量，例如：转账 100000001 金币 500"
            ).finish(reply_to=True)

        target_uid = uid.result
        currency_str = currency.result
        amount_num = amount.result

        if currency_str not in CURRENCY_NAMES:
            supported = "、".join(CURRENCY_NAMES.keys())
            await MessageUtils.build_message(
                f"不支持的货币类型，支持的类型：{supported}"
            ).finish(reply_to=True)

        currency_type = CURRENCY_NAMES[currency_str]
        display = CURRENCY_DISPLAY.get(currency_type, "金币")

        target_user_id = await UserUid.get_user_id_by_uid(target_uid)
        if not target_user_id:
            await MessageUtils.build_message(
                f"真是个笨蛋，根本没有这个uid {target_uid}！"
            ).finish(reply_to=True)

        if target_user_id == user_id:
            await MessageUtils.build_message("不能给自己转账哦...").finish(
                reply_to=True
            )

        if result := await TransactionService.transfer_check(
            user_id, target_user_id, amount_num, currency_type
        ):
            await MessageUtils.build_message(result).finish(reply_to=True)

        actual_receive, fee = await TransactionService.transfer(
            user_id, target_user_id, amount_num, currency_type
        )

        result = f"转账成功！\n向 UID: {target_uid} 转出 {amount_num} {display}"
        if fee > 0:
            result += (
                f"\n手续费：{fee}{display}，"
                f"对方实际到账：{actual_receive}{display}"
            )

        logger.info(
            f"银行转账:向{target_uid}转出{amount_num}{display},"
            f"手续费:{fee}",
            arparma.header_result,
            session=session,
        )
        await MessageUtils.build_message(result).finish(at_sender=True)

    @staticmethod
    async def user_info(session: Uninfo, arparma: Arparma) -> None:
        """处理查看用户银行信息命令"""
        user_id = session.user.id
        user_name = session.user.name or "用户"

        user_payload = await InfoService.get_user_data(user_id, user_name)

        render_data = {"page_type": "user", "payload": user_payload}
        image_bytes = await render(
            "pages/builtin/bank",
            data=render_data,
            user_id=user_id,
            viewport={"width": 386, "height": 10},
        )

        await MessageUtils.build_message(image_bytes).send()
        logger.info("查看银行个人信息", arparma.header_result, session=session)

    @staticmethod
    async def bank_info(session: Uninfo, arparma: Arparma) -> None:
        """处理查看银行总览信息命令"""
        overview_payload = await InfoService.get_bank_data()

        render_data = {
            "page_type": "overview",
            "payload": overview_payload,
        }
        image_bytes = await render(
            "pages/builtin/bank",
            data=render_data,
            user_id=session.user.id,
            viewport={"width": 450, "height": 10},
        )

        await MessageUtils.build_message(image_bytes).send()
        logger.info("查看银行信息", arparma.header_result, session=session)

    @staticmethod
    async def fixed_deposit(
        session: Uninfo,
        arparma: Arparma,
        currency: Match[str],
        amount: Match[int],
        period: Match[int],
    ) -> None:
        """处理定期存款命令"""
        user_id = session.user.id

        currency_type, amount_num, error = (
            BankHandler._resolve_currency_and_amount(currency, amount)
        )

        if error:
            await MessageUtils.build_message(error).finish(reply_to=True)

        if amount_num is None:
            await MessageUtils.build_message(
                "请输入存款金额，例如：定期存款 金币 1000 30"
            ).finish(reply_to=True)

        period_days = period.result if period.available else 30

        if period_days not in FIXED_PERIOD_MULTIPLIERS:
            periods = "、".join(str(p) for p in FIXED_PERIOD_MULTIPLIERS)
            await MessageUtils.build_message(
                f"不支持的存款期限，支持期限：{periods}天"
            ).finish(reply_to=True)

        display = CURRENCY_DISPLAY.get(currency_type, "金币")

        if result := await AccountService.deposit_check(
            user_id, amount_num, currency_type
        ):
            await MessageUtils.build_message(result).finish(reply_to=True)

        try:
            _, rate, total_interest = await AccountService.fixed_deposit(
                user_id, amount_num, currency_type, period_days
            )

            result = (
                f"定期存款成功！\n"
                f"存款{display}金额：{amount_num}\n"
                f"存款期限：{period_days}天\n"
                f"定期利率：{rate * 100:.4f}%\n"
                f"预计利息：{total_interest}{display}"
            )

            logger.info(
                f"银行定期存款:{amount_num}{display}, "
                f"期限:{period_days}天, 利率:{rate}",
                arparma.header_result,
                session=session,
            )
            await MessageUtils.build_message(result).finish(at_sender=True)
        except ValueError as e:
            await MessageUtils.build_message(str(e)).finish(reply_to=True)

    @staticmethod
    async def loan(
        session: Uninfo,
        arparma: Arparma,
        amount: Match[int],
        period: Match[int],
    ) -> None:
        """处理贷款申请命令"""
        user_id = session.user.id

        if not amount.available or amount.result is None:
            await MessageUtils.build_message(
                "请输入贷款金额，例如：贷款 5000 30"
            ).finish(reply_to=True)

        amount_num = amount.result
        period_days = period.result if period.available else 30

        if result := await LoanService.check(user_id, amount_num, period_days):
            await MessageUtils.build_message(result).finish(reply_to=True)

        try:
            _, loan_rate, due_date = await LoanService.apply(
                user_id, amount_num, period_days
            )

            result = (
                f"贷款成功！\n"
                f"贷款金额：{amount_num}金币\n"
                f"贷款期限：{period_days}天\n"
                f"日利率：{loan_rate * 100:.3f}%\n"
                f"到期时间：{due_date.strftime('%Y-%m-%d %H:%M')}"
            )

            logger.info(
                f"银行贷款:{amount_num}金币, "
                f"期限:{period_days}天, 利率:{loan_rate}",
                arparma.header_result,
                session=session,
            )
            await MessageUtils.build_message(result).finish(at_sender=True)
        except ValueError as e:
            await MessageUtils.build_message(str(e)).finish(reply_to=True)

    @staticmethod
    async def repay(
        session: Uninfo,
        arparma: Arparma,
        amount: Match[int],
    ) -> None:
        """处理还款命令"""
        user_id = session.user.id

        if not amount.available or amount.result is None:
            await MessageUtils.build_message(
                "请输入还款金额，例如：还款 5000"
            ).finish(reply_to=True)

        amount_num = amount.result

        try:
            bank_user, actual_repay = await LoanService.repay(user_id, amount_num)

            result = f"还款成功！\n还款金额：{actual_repay}金币"

            if bank_user.loan_amount > 0:
                result += f"\n剩余贷款：{bank_user.loan_amount}金币"
            else:
                result += "\n贷款已全部还清！"

            logger.info(
                f"银行还款:{actual_repay}金币, "
                f"剩余贷款:{bank_user.loan_amount}",
                arparma.header_result,
                session=session,
            )
            await MessageUtils.build_message(result).finish(at_sender=True)
        except ValueError as e:
            await MessageUtils.build_message(str(e)).finish(reply_to=True)

    @staticmethod
    async def leaderboard(session: Uninfo, arparma: Arparma) -> None:
        """处理银行排行榜命令"""
        leaderboard_data = await InfoService.get_leaderboard()

        if not leaderboard_data:
            await MessageUtils.build_message("暂无银行排行数据。").finish(
                reply_to=True
            )

        lines = ["-- 银行资产排行榜 --"]
        for entry in leaderboard_data:
            lines.append(
                f"第{entry['rank']}名 | "
                f"总资产：{entry['total_assets']} | "
                f"金币：{entry['gold']} | "
                f"银币：{entry['silver']} | "
                f"铜币：{entry['copper']}"
            )

        result = "\n".join(lines)

        logger.info("查看银行排行", arparma.header_result, session=session)
        await MessageUtils.build_message(result).finish(at_sender=True)

    @staticmethod
    async def history(
        session: Uninfo,
        arparma: Arparma,
        page: Match[int],
    ) -> None:
        """处理银行记录命令"""
        user_id = session.user.id
        page_num = page.result if page.available else 1

        history_data = await InfoService.get_history(user_id, page_num)

        records = history_data["records"]
        if not records:
            await MessageUtils.build_message("暂无银行操作记录。").finish(
                reply_to=True
            )

        handle_type_map = {
            "DEPOSIT": "存款",
            "WITHDRAW": "取款",
            "TRANSFER": "转账",
            "INTEREST": "利息",
            "LOAN": "贷款",
            "REPAYMENT": "还款",
            "FIXED_DEPOSIT": "定期存款",
        }

        lines = [
            f"-- 银行记录（第{history_data['page']}"
            f"/{history_data['total_pages']}页）--"
        ]
        for record in records:
            handle = handle_type_map.get(record["handle_type"], record["handle_type"])
            lines.append(
                f"{record['create_time']} | {handle} | "
                f"{record['currency_display']}{record['amount']}"
            )

        result = "\n".join(lines)

        logger.info(
            f"查看银行记录, 第{page_num}页",
            arparma.header_result,
            session=session,
        )
        await MessageUtils.build_message(result).finish(at_sender=True)
