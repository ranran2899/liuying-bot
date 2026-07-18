from fastapi import APIRouter
from fastapi.responses import JSONResponse
from nonebot import require
from nonebot.compat import model_dump

from liuying.liuying_plugins.superuser.plugin_store.data_source import StoreManager
from liuying.models.plugin_info import PluginInfo
from liuying.utils.log import logger

from ....base_model import Result
from ....utils import authentication
from .model import PluginIr

# 确保插件商店依赖已加载
require("liuying.liuying_plugins.superuser.plugin_store")

router = APIRouter(prefix="/store")


@router.get(
    "/get_plugin_store",
    dependencies=[authentication()],
    response_model=Result[dict],
    response_class=JSONResponse,
    description="获取插件商店插件信息",  # type: ignore
)
async def _() -> Result[dict]:
    try:
        plugin_list, extra_plugin_list = await StoreManager.get_data()
        plugin_list = [
            {**model_dump(plugin), "name": plugin.name, "id": idx}
            for idx, plugin in enumerate(plugin_list + extra_plugin_list)
        ]
        modules = await PluginInfo.filter(load_status=True).values_list(
            "module", flat=True
        )
        return Result.ok({"install_module": modules, "plugin_list": plugin_list})
    except Exception as e:
        logger.error("获取插件商店插件信息失败", command="WebUi", e=e)
        return Result.fail(f"获取插件商店插件信息失败: {type(e)}: {e}")


@router.post(
    "/install_plugin",
    dependencies=[authentication()],
    response_model=Result,
    response_class=JSONResponse,
    description="安装插件",  # type: ignore
)
async def _(param: PluginIr) -> Result:
    try:
        result = await StoreManager.add_plugin(param.id)  # type: ignore
        return Result.ok(info=result)
    except Exception as e:
        return Result.fail(f"安装插件失败: {type(e)}: {e}")


@router.post(
    "/update_plugin",
    dependencies=[authentication()],
    response_model=Result,
    response_class=JSONResponse,
    description="更新插件",  # type: ignore
)
async def _(param: PluginIr) -> Result:
    try:
        result = await StoreManager.update_plugin(param.id)  # type: ignore
        return Result.ok(info=result)
    except Exception as e:
        return Result.fail(f"更新插件失败: {type(e)}: {e}")


@router.post(
    "/remove_plugin",
    dependencies=[authentication()],
    response_model=Result,
    response_class=JSONResponse,
    description="移除插件",  # type: ignore
)
async def _(param: PluginIr) -> Result:
    try:
        result = await StoreManager.remove_plugin(param.id)  # type: ignore
        return Result.ok(info=result)
    except Exception as e:
        return Result.fail(f"移除插件失败: {type(e)}: {e}")
