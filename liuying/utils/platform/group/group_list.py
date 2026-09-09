from nonebot.adapters import Bot
from nonebot_plugin_uninfo import SceneType, get_interface

from liuying.models._group import GroupConsole
from liuying.utils.platform.helper import PlatformUtils


class GroupListUtils:
    """群组列表工具类"""

    @classmethod
    async def get_group_list(
        cls, bot: Bot, only_group: bool = False
    ) -> tuple[list[GroupConsole], str]:
        """获取群组列表

        参数:
            bot: Bot
            only_group: 是否只获取群组（不获取channel）

        返回:
            tuple[list[GroupConsole], str]: 群组列表, 平台
        """
        if not (interface := get_interface(bot)):
            return [], ""
        platform = PlatformUtils.get_platform(bot)
        result_list = []
        for scene in await interface.get_scenes(SceneType.GROUP):
            result_list.append(
                GroupConsole(group_id=scene.id, group_name=scene.name)
            )
            if (
                not only_group
                and platform != "qq"
                and (
                    channel_list := await interface.get_scenes(
                        parent_scene_id=scene.id
                    )
                )
            ):
                result_list.extend(
                    GroupConsole(
                        group_id=scene.id,
                        group_name=channel.name,
                        channel_id=channel.id,
                    )
                    for channel in channel_list
                )
        return result_list, platform
