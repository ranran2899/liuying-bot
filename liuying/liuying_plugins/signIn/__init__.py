"""
NoneBot 签到插件
"""
from nonebot.plugin import PluginMetadata

from liuying.configs.utils import Command, PluginExtraData, RegisterConfig

from .signIn import sign_in_cmd

__plugin_meta__ = PluginMetadata(
    name="签到",
    description="每日签到，证明你在这里",
    usage="""
    每日签到
    指令:
        签到
    * 签到获得随机基础金币奖励(1-配置值)
    * 连续签到每天额外获得1金币，上限为配置值
    * 签到获得随机基础好感度奖励(1-配置值)
    * 连续签到每天额外获得1好感度，上限为配置值
    * 基于自然日(24:00)重置签到状态，跨午夜签到判定为连续签到
    """.strip(),
    extra=PluginExtraData(
        author="liuying",
        version="0.5",
        menu_type="功能",
        is_show=True,
        commands=[Command(command="签到")],
        configs=[
            RegisterConfig(
                key="SIGN_GOLD",
                value=50,
                help="签到基础金币奖励上限，实际奖励为1到此值的随机整数",
                default_value=50,
                type=int,
            ),
            RegisterConfig(
                key="MAX_SIGN_GOLD",
                value=30,
                help="连续签到奖励金币上限，每连续签到1天额外获得1金币，最高不超过此值",
                default_value=30,
                type=int,
            ),
            RegisterConfig(
                key="ITEM_DROP_RATE",
                value=50,
                help="签到好感度双倍加持卡Ⅰ掉落概率",
                default_value=50,
                type=float,
            ),
            RegisterConfig(
                key="BASE_FAVOR_EXPERIENCE",
                value=30,
                help="签到基础好感度经验奖励上限，实际奖励为1到此值的随机整数",
                default_value=30,
                type=int,
            ),
            RegisterConfig(
                key="CONSECUTIVE_FAVOR_BONUS",
                value=3,
                help="连续签到好感度奖励上限，每连续签到1天额外获得1好感度，最高不超过此值",
                default_value=3,
                type=int,
            ),
            RegisterConfig(
                key="MAX_FAVOR",
                value=9,
                help="最大好感度等级",
                default_value=9,
                type=int,
            ),
            RegisterConfig(
                key="FAVOR_EXPERIENCE_RATE",
                value=1.5,
                help="好感度等级经验增长速率",
                default_value=1.5,
                type=float,
            ),
            RegisterConfig(
                key="MAX_LEVEL",
                value=100,
                help="最大等级",
                default_value=100,
                type=int,
            ),
            RegisterConfig(
                key="LEVEL_EXPERIENCE_RATE",
                value=1.2,
                help="等级等级经验增长速率",
                default_value=1.2,
                type=float,
            ),
        ],
    ).to_dict(),
)

export = [sign_in_cmd]
