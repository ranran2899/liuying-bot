from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import (
    Alconna,
    Args,
    Arparma,
    Match,
    Subcommand,
    on_alconna,
)
from nonebot_plugin_uninfo import Uninfo

from liuying.configs.config import NICKNAME, Config
from liuying.configs.utils import PluginExtraData, RegisterConfig
from liuying.utils.apscheduler import task_manager
from liuying.utils.log import logger

from .handlers import BankHandler
from .settlement import SettlementService

__plugin_meta__ = PluginMetadata(
    name=f"{NICKNAME}银行",
    description=f"""
    银行，提供高品质的存款！当好感度等级达到指定等级时，{NICKNAME}会偷偷的帮助你哦。
    存款额度与好感度有关，每日存款次数有限制。
    支持金币、银币、铜币三种货币的存取款服务。
    支持定期存款、银行贷款、转账手续费、利息税等高级功能。
    """.strip(),
    usage="""
    指令：
        存款 [货币类型] [金额]
        取款 [货币类型] [金额]
        银行兑换 [货币类型] [数量]
        转账 [用户uid] [货币类型] [数量]
        定期存款 [货币类型] [金额] [期限]
        贷款 [金额] [期限]
        还款 [金额]
        银行排行
        银行记录 [页码]
        银行信息
        我的银行信息
    货币类型：金币、银币、铜币（不填默认为金币）
    兑换仅支持：金币兑换银币，银币兑换铜币（不可反向）
    转账需使用对方UID，转账货币来自银行账户余额，收取手续费
    定期存款期限：7、30、90天，利率随期限递增
    贷款期限：7、30、90天，贷款额度与好感度等级相关
    示例：
        存款 金币 1000
        存款 银币 500
        存款 100（默认存金币）
        取款 铜币 200
        银行兑换 银币 100
        银行兑换 铜币 500
        转账 100000001 金币 500
        定期存款 金币 1000 30
        贷款 5000 30
        还款 5000
        银行排行
        银行记录
    """.strip(),
    extra=PluginExtraData(
        author="liuying",
        version="0.3",
        menu_type="娱乐",
        configs=[
            RegisterConfig(
                key="sign_max_deposit",
                value=10000,
                help="好感度换算存款金额比例，当值是100时，最大存款金额=好感度等级*100，存款的最低金额是10000（强制）",
                default_value=10000,
                type=int,
            ),
            RegisterConfig(
                key="sign_max_silver_deposit",
                value=100000,
                help="银币存款上限倍率，最大银币存款=好感度等级*该值，最低10000",
                default_value=100000,
                type=int,
            ),
            RegisterConfig(
                key="sign_max_copper_deposit",
                value=10000000,
                help="铜币存款上限倍率，最大铜币存款=好感度等级*该值，最低100000",
                default_value=10000000,
                type=int,
            ),
            RegisterConfig(
                key="max_daily_deposit_count",
                value=3,
                help="每日每种货币最大存款次数（各币种独立计算）",
                default_value=3,
                type=int,
            ),
            RegisterConfig(
                key="rate_range",
                value=[0.0005, 0.001],
                help="小时利率范围",
                default_value=[0.0005, 0.001],
                type=list,
            ),
            RegisterConfig(
                key="impression_event",
                value=5,
                help="到达指定好感度等级时随机提高利率",
                default_value=5,
                type=int,
            ),
            RegisterConfig(
                key="impression_event_range",
                value=[0.00001, 0.0003],
                help="到达指定好感度等级时随机提高利率的范围",
                default_value=[0.00001, 0.0003],
                type=list,
            ),
            RegisterConfig(
                key="impression_event_prop",
                value=0.3,
                help="到达指定好感度等级时随机提高利率的触发概率",
                default_value=0.3,
                type=float,
            ),
            RegisterConfig(
                key="gold_to_silver_rate",
                value=64,
                help="金币兑换银币比例，1金币可兑换的银币数量",
                default_value=64,
                type=int,
            ),
            RegisterConfig(
                key="silver_to_copper_rate",
                value=64,
                help="银币兑换铜币比例，1银币可兑换的铜币数量",
                default_value=64,
                type=int,
            ),
            RegisterConfig(
                key="transfer_fee_rate",
                value=0.01,
                help="转账手续费率，默认0.01（1%），范围0~0.03",
                default_value=0.01,
                type=float,
            ),
            RegisterConfig(
                key="loan_rate",
                value=0.001,
                help="贷款日利率，默认0.001（0.1%）",
                default_value=0.001,
                type=float,
            ),
            RegisterConfig(
                key="max_loan_amount",
                value=10000,
                help="最大贷款金额倍率，贷款上限=好感度等级*该值",
                default_value=10000,
                type=int,
            ),
            RegisterConfig(
                key="interest_tax_rate",
                value=0.0,
                help="利息税率，默认0.0（0%），高级玩家利息收益扣税",
                default_value=0.0,
                type=float,
            ),
            RegisterConfig(
                key="interest_tax_threshold",
                value=1000000,
                help="利息税起征点，存款超过该值时收取利息税",
                default_value=1000000,
                type=int,
            ),
            RegisterConfig(
                key="silver_rate_range",
                value=[0.0003, 0.0006],
                help="银币利率范围",
                default_value=[0.0003, 0.0006],
                type=list,
            ),
            RegisterConfig(
                key="copper_rate_range",
                value=[0.0001, 0.0003],
                help="铜币利率范围",
                default_value=[0.0001, 0.0003],
                type=list,
            ),
            RegisterConfig(
                key="treasury_min_reserve",
                value=100000,
                help="国库最低储备，低于此值时限制取款",
                default_value=100000,
                type=int,
            ),
        ],
    ).to_dict(),
)

Config.set_name("bank", "银行")

_matcher = on_alconna(
    Alconna(
        "bank",
        Subcommand("deposit", Args["currency?", str]["amount?", int]),
        Subcommand("withdraw", Args["currency?", str]["amount?", int]),
        Subcommand("exchange", Args["currency?", str]["amount?", int]),
        Subcommand(
            "transfer",
            Args["uid", str]["currency", str]["amount", int],
        ),
        Subcommand("user-info"),
        Subcommand("bank-info"),
        Subcommand(
            "fixed-deposit",
            Args["currency?", str]["amount?", int]["period?", int, 30],
        ),
        Subcommand("loan", Args["amount", int]["period?", int, 30]),
        Subcommand("repay", Args["amount", int]),
        Subcommand("leaderboard"),
        Subcommand("history", Args["page?", int, 1]),
    ),
    priority=5,
    block=True,
)

_matcher.shortcut(
    r"存款\s*(?P<currency>金币|银币|铜币)?\s*(?P<amount>\d+)?",
    command="bank",
    arguments=["deposit", "{currency}", "{amount}"],
    prefix=True,
)

_matcher.shortcut(
    r"取款\s*(?P<currency>金币|银币|铜币)?\s*(?P<amount>\d+)?",
    command="bank",
    arguments=["withdraw", "{currency}", "{amount}"],
    prefix=True,
)

_matcher.shortcut(
    r"我的银行信息",
    command="bank",
    arguments=["user-info"],
    prefix=True,
)

_matcher.shortcut(
    r"银行信息",
    command="bank",
    arguments=["bank-info"],
    prefix=True,
)

_matcher.shortcut(
    r"银行兑换\s*(?P<currency>银币|铜币)\s*(?P<amount>\d+)",
    command="bank",
    arguments=["exchange", "{currency}", "{amount}"],
    prefix=True,
)

_matcher.shortcut(
    r"转账\s*(?P<uid>\d+)\s*(?P<currency>金币|银币|铜币)\s*(?P<amount>\d+)",
    command="bank",
    arguments=["transfer", "{uid}", "{currency}", "{amount}"],
    prefix=True,
)

_matcher.shortcut(
    r"定期存款\s*(?P<currency>金币|银币|铜币)?\s*(?P<amount>\d+)?\s*(?P<period>\d+)?",
    command="bank",
    arguments=["fixed-deposit", "{currency}", "{amount}", "{period}"],
    prefix=True,
)

_matcher.shortcut(
    r"贷款\s*(?P<amount>\d+)\s*(?P<period>\d+)?",
    command="bank",
    arguments=["loan", "{amount}", "{period}"],
    prefix=True,
)

_matcher.shortcut(
    r"还款\s*(?P<amount>\d+)",
    command="bank",
    arguments=["repay", "{amount}"],
    prefix=True,
)

_matcher.shortcut(
    r"银行排行",
    command="bank",
    arguments=["leaderboard"],
    prefix=True,
)

_matcher.shortcut(
    r"银行记录",
    command="bank",
    arguments=["history"],
    prefix=True,
)


@_matcher.assign("deposit")
async def _(
    session: Uninfo,
    arparma: Arparma,
    currency: Match[str],
    amount: Match[int],
):
    await BankHandler.deposit(session, arparma, currency, amount)


@_matcher.assign("withdraw")
async def _(
    session: Uninfo,
    arparma: Arparma,
    currency: Match[str],
    amount: Match[int],
):
    await BankHandler.withdraw(session, arparma, currency, amount)


@_matcher.assign("exchange")
async def _(
    session: Uninfo,
    arparma: Arparma,
    currency: Match[str],
    amount: Match[int],
):
    await BankHandler.exchange(session, arparma, currency, amount)


@_matcher.assign("transfer")
async def _(
    session: Uninfo,
    arparma: Arparma,
    uid: Match[str],
    currency: Match[str],
    amount: Match[int],
):
    await BankHandler.transfer(session, arparma, uid, currency, amount)


@_matcher.assign("user-info")
async def _(session: Uninfo, arparma: Arparma):
    await BankHandler.user_info(session, arparma)


@_matcher.assign("bank-info")
async def _(session: Uninfo, arparma: Arparma):
    await BankHandler.bank_info(session, arparma)


@_matcher.assign("fixed-deposit")
async def _(
    session: Uninfo,
    arparma: Arparma,
    currency: Match[str],
    amount: Match[int],
    period: Match[int],
):
    await BankHandler.fixed_deposit(session, arparma, currency, amount, period)


@_matcher.assign("loan")
async def _(
    session: Uninfo,
    arparma: Arparma,
    amount: Match[int],
    period: Match[int],
):
    await BankHandler.loan(session, arparma, amount, period)


@_matcher.assign("repay")
async def _(
    session: Uninfo,
    arparma: Arparma,
    amount: Match[int],
):
    await BankHandler.repay(session, arparma, amount)


@_matcher.assign("leaderboard")
async def _(session: Uninfo, arparma: Arparma):
    await BankHandler.leaderboard(session, arparma)


@_matcher.assign("history")
async def _(
    session: Uninfo,
    arparma: Arparma,
    page: Match[int],
):
    await BankHandler.history(session, arparma, page)


@task_manager.cron_task("bank_settlement", hour=0, minute=0)
async def _bank_settlement():
    """每日0点结算利息"""
    await SettlementService.settle_daily_interest()
    logger.info("银行结算", "定时任务")
