"""
帮助数据源模块
"""
from pathlib import Path
from typing import Any

import nonebot
from nonebot_plugin_uninfo import Uninfo

from liuying.configs.utils import PluginExtraData
from liuying.models._user import UserPermLevel
from liuying.models.plugin_info import PluginInfo
from liuying.models.statistics import Statistics
from liuying.ui import render as ui_render
from liuying.utils.enum import PluginType
from liuying.utils.image import BuildImage

from .config import (
    GROUP_HELP_PATH,
    SIMPLE_DETAIL_HELP_IMAGE,
    SIMPLE_HELP_IMAGE,
    driver,
)
from .render import HelpRender


class HelpManage:
    """帮助数据管理"""

    @staticmethod
    def get_save_path(group_id: str | None, is_detail: bool) -> Path:
        """
        获取帮助图片保存路径

        参数:
            group_id: 群号
            is_detail: 是否详细

        返回:
            Path: 保存路径
        """
        match (group_id, is_detail):
            case (str(gid), _):
                return GROUP_HELP_PATH / f"{gid}_{is_detail}.png"
            case (None, True):
                return SIMPLE_DETAIL_HELP_IMAGE
            case _:
                return SIMPLE_HELP_IMAGE

    @classmethod
    async def create_help_image(
        cls, session: Uninfo, group_id: str | None, is_detail: bool
    ) -> Path:
        """
        生成帮助图片并保存

        参数:
            session: Uninfo
            group_id: 群号
            is_detail: 是否详细

        返回:
            Path: 图片保存路径
        """
        image_data = await HelpRender.build(session, group_id, is_detail)
        result = BuildImage.open(image_data)

        save_path = cls.get_save_path(group_id, is_detail)
        await result.save(save_path)
        return save_path

    @staticmethod
    async def get_user_allowed_types(user_id: str) -> list[PluginType]:
        """
        获取用户可访问插件类型列表

        参数:
            user_id: 用户id

        返回:
            list[PluginType]: 插件类型列表
        """
        types = [PluginType.NORMAL, PluginType.DEPENDANT]

        user_levels = await UserPermLevel.filter(
            user_id=user_id, user_perm__gt=0
        ).exists()

        if user_levels:
            types.extend([PluginType.ADMIN, PluginType.SUPER_AND_ADMIN])

        if user_id in driver.config.superusers:
            types.append(PluginType.SUPERUSER)

        return types

    @classmethod
    async def get_plugin_help_detail(
        cls, user_id: str, name: str, is_superuser: bool
    ) -> str | bytes:
        """
        获取功能的帮助信息

        参数:
            user_id: 用户id
            name: 插件名称或id
            is_superuser: 是否为超级用户

        返回:
            str | bytes: 帮助信息
        """
        allowed_types = await cls.get_user_allowed_types(user_id)
        plugin = await cls._find_plugin(name, allowed_types)

        if not plugin:
            return "没有查找到这个功能噢..."

        return await cls._build_help_detail(plugin, is_superuser, user_id)

    @classmethod
    async def get_smart_help_text(cls, name: str = "") -> str:
        """
        获取智能模式帮助文本（供AI智能工具调用）

        参数:
            name: 插件名称或模块名，空串时列出全部可用插件

        返回:
            str: 帮助文本
        """
        keyword = (name or "").strip()
        if not keyword:
            plugins = await cls.get_plugin_list()
            if not plugins:
                return "暂无可用插件"
            lines: list[str] = ["可用插件列表："]
            current_menu = ""
            for plugin in plugins:
                menu = str(plugin.get("menu_type") or "其他")
                if menu != current_menu:
                    current_menu = menu
                    lines.append(f"[{menu}]")
                desc = str(plugin.get("description") or "")[:60]
                lines.append(
                    f"- {plugin.get('name')}（{plugin.get('module')}）: {desc}"
                )
            return "\n".join(lines)

        info = await cls.get_plugin_full_info(keyword)
        if not info:
            return f"未找到插件: {keyword}"
        return cls._format_plugin_detail(info)

    @staticmethod
    def _format_plugin_detail(info: dict[str, Any]) -> str:
        """
        将插件完整信息格式化为帮助文本

        参数:
            info: get_plugin_full_info 返回的插件完整信息

        返回:
            str: 插件详情文本
        """
        parts: list[str] = [f"{info.get('name')}（{info.get('module')}）"]
        if description := str(info.get("description") or ""):
            parts.append(f"描述: {description}")
        if usage := str(info.get("usage") or ""):
            parts.append(f"用法: {usage}")
        commands = info.get("commands") or []
        if commands:
            parts.append("命令:")
            for cmd in commands:
                line = f"- {cmd.get('command', '')}"
                params = cmd.get("params") or []
                if params:
                    line += " " + " ".join(f"[{p}]" for p in params)
                if cmd.get("description"):
                    line += f": {cmd['description']}"
                parts.append(line)
        if info.get("status") is False:
            parts.append("（当前已禁用）")
        return "\n".join(parts)

    @classmethod
    async def get_plugin_list(cls) -> list[dict[str, Any]]:
        """
        获取全部可见插件摘要列表（普通/管理员/超级用户）

        供其他插件调用的查询接口，不含依赖插件与父插件。

        返回:
            list[dict[str, Any]]: 插件摘要列表，每项包含
                id/name/module/aliases/commands/description/menu_type/
                plugin_type/admin_level/status/tools_count
        """
        plugins = await PluginInfo.visible_query(
            plugin_type__in=[
                PluginType.NORMAL,
                PluginType.ADMIN,
                PluginType.SUPER_AND_ADMIN,
                PluginType.SUPERUSER,
            ],
        ).all()

        result: list[dict[str, Any]] = []
        for plugin in plugins:
            nb_plugin = nonebot.get_plugin_by_module_name(plugin.module_path)
            description = ""
            aliases: list[str] = []
            commands: list[dict[str, Any]] = []
            tools_count = 0
            if nb_plugin and nb_plugin.metadata:
                description = nb_plugin.metadata.description
                extra_data = PluginExtraData(**nb_plugin.metadata.extra)
                aliases = sorted(extra_data.aliases)
                commands = [cmd.model_dump() for cmd in extra_data.commands]
                tools_count = len(extra_data.smart_tools or [])
            result.append({
                "id": str(plugin.id),
                "name": plugin.name,
                "module": plugin.module,
                "aliases": aliases,
                "commands": commands,
                "description": description,
                "menu_type": plugin.menu_type,
                "plugin_type": (
                    str(plugin.plugin_type) if plugin.plugin_type else None
                ),
                "admin_level": plugin.admin_level,
                "status": plugin.status,
                "tools_count": tools_count,
            })
        return result

    @classmethod
    async def get_plugin_full_info(cls, name: str) -> dict[str, Any] | None:
        """
        获取单个插件的完整信息（插件信息/功能描述/使用方法/命令列表）

        供其他插件调用的查询接口，支持插件名称、模块名或id。

        参数:
            name: 插件名称、模块名或id

        返回:
            dict[str, Any] | None: 插件完整信息，未找到时返回 None
        """
        if name.isdigit():
            plugin = await PluginInfo.filter(
                id=int(name), is_show=True, is_delete=False
            ).first()
        else:
            plugin = (
                await PluginInfo.get_plugin(
                    name=name, is_show=True, is_delete=False
                )
                or await PluginInfo.get_plugin(
                    module=name, is_show=True, is_delete=False
                )
            )
        if not plugin:
            return None

        info: dict[str, Any] = {
            "id": str(plugin.id),
            "name": plugin.name,
            "module": plugin.module,
            "menu_type": plugin.menu_type,
            "plugin_type": str(plugin.plugin_type) if plugin.plugin_type else None,
            "admin_level": plugin.admin_level,
            "status": plugin.status,
            "author": plugin.author,
            "version": plugin.version,
            "description": "",
            "usage": "",
            "superuser_help": "",
            "commands": [],
            "aliases": [],
            "smart_tools": [],
            "call_count": 0,
        }

        nb_plugin = nonebot.get_plugin_by_module_name(plugin.module_path)
        if nb_plugin and nb_plugin.metadata:
            extra_data = PluginExtraData(**nb_plugin.metadata.extra)
            info.update({
                "author": extra_data.author or plugin.author,
                "version": extra_data.version or plugin.version,
                "description": nb_plugin.metadata.description,
                "usage": nb_plugin.metadata.usage,
                "superuser_help": extra_data.superuser_help or "",
                "commands": [cmd.model_dump() for cmd in extra_data.commands],
                "aliases": sorted(extra_data.aliases),
                "smart_tools": [
                    tool.to_dict() for tool in extra_data.smart_tools or []
                ],
            })

        info["call_count"] = await Statistics.filter(plugin_name=plugin.module).count()
        return info

    @classmethod
    async def _find_plugin(
        cls, name: str, allowed_types: list[PluginType]
    ) -> PluginInfo | None:
        """
        查找插件

        参数:
            name: 插件名称或id
            allowed_types: 允许的插件类型列表

        返回:
            PluginInfo | None: 插件信息
        """
        if name.isdigit():
            return await PluginInfo.filter(
                id=int(name), plugin_type__in=allowed_types,
            ).first()

        return await PluginInfo.filter(
            name__iexact=name,
            load_status=True,
            plugin_type__in=allowed_types,
        ).first()

    @classmethod
    async def _build_help_detail(
        cls, plugin: PluginInfo, is_superuser: bool, user_id: str
    ) -> str | bytes:
        """
        构建帮助详情

        参数:
            plugin: 插件信息
            is_superuser: 是否为超级用户
            user_id: 用户ID

        返回:
            str | bytes: 帮助详情
        """
        nb_plugin = nonebot.get_plugin_by_module_name(plugin.module_path)

        if not nb_plugin or not nb_plugin.metadata:
            return "糟糕! 该功能没有帮助喔..."

        extra_data = PluginExtraData(**nb_plugin.metadata.extra)

        if is_superuser and not extra_data.superuser_help:
            return "该功能没有超级用户帮助信息"

        usage = extra_data.superuser_help if is_superuser else nb_plugin.metadata.usage
        call_count = await Statistics.filter(plugin_name=plugin.module).count()

        template_data = {
            "title": nb_plugin.metadata.name,
            "author": extra_data.author,
            "version": extra_data.version,
            "call_count": call_count,
            "descriptions": cls._format_text(nb_plugin.metadata.description),
            "usages": cls._format_text(usage),
        }

        return await ui_render(
            "pages/builtin/help_detail", template_data,
            user_id=user_id, wait=2,
        )

    @staticmethod
    def _format_text(text: str) -> list[str]:
        """
        格式化文本，移除每行公共前导空格

        参数:
            text: 原始文本

        返回:
            list[str]: 格式化后的文本列表
        """
        lines = text.split("\n")
        min_spaces = min(
            (len(line) - len(line.lstrip(" ")) for line in lines if line.strip()),
            default=0,
        )
        return [line[min_spaces:] for line in lines]
