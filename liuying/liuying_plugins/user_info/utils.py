"""
用户信息插件工具类
"""

from nonebot_plugin_alconna import Button


class QQMsgBuilder:
    """QQ消息构建器"""

    @staticmethod
    def _markdown(image_url: str, width: str, height: str) -> str:
        """构建Markdown内容

        参数:
            image_url: 图片URL
            width: 图片宽度
            height: 图片高度

        返回:
            str: Markdown格式字符串
        """
        return "\n".join([
            # f"> 用户信息",
            f"![用户信息卡片 #{width}px #{height}px]({image_url})",
        ])

    @staticmethod
    def _keyboard() -> list[Button]:
        """构建消息按钮

        返回:
            list[Button]: 按钮列表
        """
        return [
            Button(
                flag="enter",
                label="签到",
                clicked_label="签到",
                text="/签到",
                permission="all",
            ),
            Button(
                flag="enter",
                label="我的信息",
                clicked_label="我的信息",
                id="btn_userinfo",
                text="/我的信息",
                permission="all",
            ),
            Button(
                flag="enter",
                label="我的令牌",
                clicked_label="我的令牌",
                id="btn_token",
                text="/我的令牌",
                permission="all",
            ),
        ]
