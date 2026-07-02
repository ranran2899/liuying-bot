"""
天气插件核心
"""
from typing import Dict, Any

from nonebot_plugin_alconna import Alconna, on_alconna, Args
from nonebot_plugin_uninfo import Uninfo

from liuying.utils.message import MessageUtils
from liuying.utils.log import logger
from liuying.models._user.user_intro import UserIntroInfo
from .api import WeatherAPI

# 注册天气查询命令
weather_cmd = on_alconna(
    Alconna("天气", Args["city", str]),
    aliases={"查天气", "/天气"},
    priority=50,
    block=True
)

# 注册支持区县查询命令
districts_cmd = on_alconna(
    Alconna("支持区县", Args["province", str]),
    aliases={"查询区县", "可查区县", "/支持区县"},
    priority=50,
    block=True
)

@weather_cmd.handle()
async def handle_weather(session: Uninfo, city: str):
    """处理天气查询请求"""
    logger.info(f"用户天气查询请求:{city}", command="天气", session=session)
    
    if not city:
        await MessageUtils.build_message("请输入查询指令，例如：\n天气 北京\n天气 河北-石家庄").finish()
    
    # 解析输入
    parts = city.split("-")
    
    # 使用WeatherAPI查询天气
    if len(parts) >= 2:
        province, city_name = parts[0], parts[1]
        logger.debug(f"尝试省份+城市查询: {province}, {city_name}")
        weather_data = await WeatherAPI.get_weather_by_province_city(province, city_name)
        location_name = city_name
    else:
        # 如果没有分隔符，尝试将整个输入作为城市名
        logger.debug(f"尝试城市名查询: {city}")
        weather_data = await WeatherAPI.get_weather_by_city(city)
        location_name = city
    
    if not weather_data:
        await MessageUtils.build_message(f"未找到城市 '{city}'，请检查输入是否正确（格式：省份-城市）").finish()
    
    logger.debug(f"获取到天气数据: {weather_data['province']}{weather_data['city']}")
    
    # 保存用户位置信息
    try:
        user_id = session.user.id
        # 获取或创建用户记录
        user, _ = await UserIntroInfo.get_or_create(user_id=user_id)
        # 更新位置信息
        user.location = location_name
        # 保存更新
        await user.save()
        logger.debug(f"已更新用户 {user_id} 的位置为: {location_name}")
    except Exception as e:
        logger.warning(f"保存用户位置信息失败: {e}")
    
    # 发送天气报告
    await send_weather_report(session, weather_data)

async def send_weather_report(session: Uninfo, data: Dict[str, Any]):
    """格式化并发送天气信息"""
    formatted = data["formatted"]
    
    # 拼接天气信息
    msg = [
        f"【{data['province']}{data['city']}天气】",
        f"🕒 发布时间：{formatted['publish_time']}",
        "",
        f"🌤 当前天气：{formatted['weather']}",
        f"🌡 温度：{formatted['temperature']} (体感{formatted['feelst']})",
        f"📈 温差：{formatted['temperature_diff']}",
        f"💧 湿度：{formatted['humidity']}",
        f"🌬 风力：{formatted['wind_direct']} "
        f"{formatted['wind_power']} "
        f"({formatted['wind_speed']})",
        f"☔ 降水量：{formatted['rain']}",
        f"📊 舒适度：{formatted['comfort']}",
        f"🌅 日出：{formatted['sunrise']}",
        f"🌇 日落：{formatted['sunset']}"
    ]
    
    await MessageUtils.build_message("\n".join(msg)).finish()

@districts_cmd.handle()
async def handle_all_districts(session: Uninfo, province: str):
    """处理支持区县查询请求"""
    logger.info(f"用户区县查询请求:{province}", command="支持区县", session=session)
    
    if not province:
        await MessageUtils.build_message("请输入省份名称，例如：支持区县 河北").finish()
    
    result = await WeatherAPI.get_districts(province)
    if not result:
        await MessageUtils.build_message(f"未找到省份 '{province}' 或该省份下无可用区县数据").finish()
    
    total = len(result["districts"])
    msg = [
        f"📌 {result['province']} 全部区县 ({total}个)：",
        "、".join(result["districts"])
    ]
    await MessageUtils.build_message("\n".join(msg)).finish()
