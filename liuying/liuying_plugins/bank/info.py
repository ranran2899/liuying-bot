import asyncio
from collections import defaultdict
from datetime import datetime, timedelta

from liuying.models._log.bank_log import BankLog
from liuying.models._user.bank_user import BankUser
from liuying.models.treasury import Treasury
from liuying.utils.enum import BankHandleType
from liuying.utils.user import UserMedia

from .constants import CURRENCY_DISPLAY, base_config
from .wallet import WalletService


class InfoService:
    """信息查询服务：用户信息、银行总览、排行榜、历史记录"""

    @staticmethod
    async def get_user_data(user_id: str, user_name: str) -> dict:
        """获取用户银行数据

        参数:
            user_id: 用户id
            user_name: 用户名

        返回:
            dict: 用户银行数据字典
        """
        bank_user = await WalletService.get_user(user_id)

        (
            rank,
            deposit_count,
            today_gold_deposit,
            today_silver_deposit,
            today_copper_deposit,
            total_interest,
            avatar_url,
        ) = await asyncio.gather(
            BankUser.filter(BankUser.amount > bank_user.amount).count(),
            BankLog.filter(user_id=user_id).count(),
            BankLog.get_user_today_deposit(user_id, "gold"),
            BankLog.get_user_today_deposit(user_id, "silver"),
            BankLog.get_user_today_deposit(user_id, "copper"),
            InfoService._get_total_interest(user_id),
            UserMedia.get_avatar(user_id),
        )

        now = datetime.now()
        end_time = (
            now
            + timedelta(days=1)
            - timedelta(hours=now.hour, minutes=now.minute, seconds=now.second)
        )

        all_today = today_gold_deposit + today_silver_deposit + today_copper_deposit
        today_deposit_amount = sum(log.amount for log in all_today)
        projected_revenue = sum(
            int(log.amount * log.rate * log.effective_hour) or 1
            for log in today_gold_deposit
            if not log.is_completed
        )

        deposit_list = [
            {
                "id": log.id,
                "date": str(now.date()),
                "start_time": str(log.create_time).split(".")[0],
                "end_time": str(end_time.replace(microsecond=0)),
                "amount": log.amount,
                "currency_type": log.currency_type,
                "currency_display": CURRENCY_DISPLAY.get(
                    log.currency_type, "金币"
                ),
                "rate": f"{log.rate * 100:.2f}",
                "projected_revenue": (
                    int(log.amount * log.rate * log.effective_hour) or 1
                ),
            }
            for log in all_today
            if not log.is_completed
        ]

        return {
            "name": user_name,
            "rank": rank + 1,
            "avatar_url": avatar_url,
            "amount": bank_user.amount,
            "silver_amount": bank_user.silver_amount,
            "copper_amount": bank_user.copper_amount,
            "deposit_count": deposit_count,
            "today_deposit_count": len(all_today),
            "cumulative_gain": total_interest,
            "projected_revenue": projected_revenue,
            "today_deposit_amount": today_deposit_amount,
            "deposit_list": deposit_list,
            "create_time": str(now.replace(microsecond=0)),
        }

    @staticmethod
    async def _get_total_interest(user_id: str) -> int:
        """获取用户累计利息收益

        参数:
            user_id: 用户id

        返回:
            int: 累计利息收益
        """
        logs = await BankLog.filter(
            BankLog.user_id == user_id,
            BankLog.handle_type == BankHandleType.INTEREST.value,
        ).all()
        return sum(log.amount for log in logs)

    @staticmethod
    async def get_bank_data() -> dict:
        """获取银行总览数据

        返回:
            dict: 银行总览数据字典
        """
        now = datetime.now()
        now_start = now - timedelta(
            hours=now.hour, minutes=now.minute, seconds=now.second
        )

        bank_users = await BankUser.filter().all()
        total_amount = sum(user.amount for user in bank_users)
        total_silver = sum(user.silver_amount for user in bank_users)
        total_copper = sum(user.copper_amount for user in bank_users)
        user_count = len(bank_users)

        today_count = await BankLog.filter(
            BankLog.create_time >= now_start,
            BankLog.handle_type == BankHandleType.DEPOSIT.value,
        ).count()

        interest_logs = await BankLog.filter(
            BankLog.handle_type == BankHandleType.INTEREST.value
        ).all()
        interest_amount = sum(log.amount for log in interest_logs)

        week_logs = await BankLog.filter(
            BankLog.create_time >= now_start - timedelta(days=7),
            BankLog.handle_type == BankHandleType.DEPOSIT.value,
        ).all()

        active_user_ids = {log.user_id for log in week_logs}
        active_user_count = len(active_user_ids)

        date_amount: dict[str, int] = defaultdict(int)
        for log in week_logs:
            date_str = str(log.create_time.date())
            date_amount[date_str] += log.amount

        e_date: list[str] = []
        e_amount: list[int] = []
        date = now.date()
        for _ in range(7):
            date_str = str(date)
            e_date.append(date_str[5:])
            e_amount.append(date_amount.get(date_str, 0))
            date -= timedelta(days=1)
        e_date.reverse()
        e_amount.reverse()

        first_log = await BankLog.filter().order_by("create_time").first()
        days = 1
        if first_log:
            days = (now.date() - first_log.create_time.date()).days + 1

        treasury_gold = await Treasury.get_treasury_money("gold_treasury")
        treasury_silver = await Treasury.get_treasury_money("silver_treasury")
        treasury_copper = await Treasury.get_treasury_money("copper_treasury")

        return {
            "amount_sum": total_amount,
            "silver_amount_sum": total_silver,
            "copper_amount_sum": total_copper,
            "user_count": user_count,
            "today_count": today_count,
            "day_amount": int(total_amount / days) if days > 0 else 0,
            "interest_amount": interest_amount,
            "active_user_count": active_user_count,
            "e_data": e_date,
            "e_amount": e_amount,
            "treasury_gold": treasury_gold,
            "treasury_silver": treasury_silver,
            "treasury_copper": treasury_copper,
            "create_time": str(now.replace(microsecond=0)),
        }

    @staticmethod
    async def get_leaderboard(limit: int = 10) -> list[dict]:
        """获取银行资产排行榜

        参数:
            limit: 返回排名数量

        返回:
            list[dict]: 排行榜列表
        """
        bank_users = await BankUser.filter().all()
        gold_to_silver: int = base_config.get("gold_to_silver_rate", 64)
        silver_to_copper: int = base_config.get("silver_to_copper_rate", 64)

        leaderboard: list[dict] = []
        for user in bank_users:
            total_assets = (
                user.amount
                + user.silver_amount / gold_to_silver
                + user.copper_amount / (gold_to_silver * silver_to_copper)
            )
            leaderboard.append(
                {
                    "user_id": user.user_id,
                    "total_assets": int(total_assets),
                    "gold": user.amount,
                    "silver": user.silver_amount,
                    "copper": user.copper_amount,
                }
            )

        leaderboard.sort(key=lambda x: x["total_assets"], reverse=True)
        leaderboard = leaderboard[:limit]

        for i, entry in enumerate(leaderboard):
            entry["rank"] = i + 1

        return leaderboard

    @staticmethod
    async def get_history(
        user_id: str, page: int = 1, page_size: int = 10
    ) -> dict:
        """获取用户银行操作记录

        参数:
            user_id: 用户id
            page: 页码
            page_size: 每页数量

        返回:
            dict: 分页记录字典
        """
        total = await BankLog.filter(user_id=user_id).count()
        offset = (page - 1) * page_size
        logs = await (
            BankLog.filter(user_id=user_id)
            .order_by("-create_time")
            .offset(offset)
            .limit(page_size)
            .all()
        )

        records = [
            {
                "id": log.id,
                "amount": log.amount,
                "rate": (
                    f"{log.rate * 100:.2f}%" if log.rate else "0.00%"
                ),
                "handle_type": log.handle_type,
                "currency_type": log.currency_type,
                "currency_display": CURRENCY_DISPLAY.get(
                    log.currency_type, "金币"
                ),
                "create_time": str(log.create_time).split(".")[0],
                "is_completed": log.is_completed,
            }
            for log in logs
        ]

        return {
            "records": records,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size,
        }
