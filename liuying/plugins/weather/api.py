"""
天气插件API接口
提供供其他插件调用的天气查询功能
"""
from typing import Dict, Any, Optional, Tuple
from liuying.utils.log import logger
from .data_source import find_city_code, search_city_code, get_weather, get_all_districts


class WeatherAPI:
    """天气查询API类，供其他插件调用"""
    
    @staticmethod
    async def get_weather_by_city(city_name: str) -> Optional[Dict[str, Any]]:
        """
        根据城市名称获取天气信息
        
        Args:
            city_name: 城市名称，如"北京"或"北京市"
            
        Returns:
            天气信息字典，包含原始数据和格式化信息，查询失败返回None
            格式: {
                "success": bool,
                "city": str,
                "province": str,
                "raw_data": dict,
                "formatted": {
                    "weather": str,
                    "temperature": str,
                    "feelst": str,
                    "humidity": str,
                    "wind": str,
                    "rain": str,
                    "comfort": str,
                    "publish_time": str
                }
            }
        """
        try:
            logger.debug(f"API查询城市天气: {city_name}")
            stationid = await search_city_code(city_name)
            
            if not stationid:
                logger.warning(f"未找到城市: {city_name}")
                return None
                
            weather_data = await get_weather(stationid)
            if not weather_data:
                logger.warning(f"获取天气数据失败: {city_name}")
                return None
                
            return WeatherAPI._format_weather_data(weather_data, city_name)
        except Exception as e:
            logger.error(f"查询城市天气异常: {e}")
            return None
    
    @staticmethod
    async def get_weather_by_province_city(province: str, city: str) -> Optional[Dict[str, Any]]:
        """
        根据省份和城市名称获取天气信息
        
        Args:
            province: 省份名称，如"河北"或"河北省"
            city: 城市名称，如"北京"或"北京市"
            
        Returns:
            天气信息字典，包含原始数据和格式化信息，查询失败返回None
        """
        try:
            logger.debug(f"API查询省份城市天气: {province}-{city}")
            stationid = await find_city_code(province, city)
            
            if not stationid:
                logger.warning(f"未找到城市: {province}-{city}")
                return None
                
            weather_data = await get_weather(stationid)
            if not weather_data:
                logger.warning(f"获取天气数据失败: {province}-{city}")
                return None
                
            return WeatherAPI._format_weather_data(weather_data, city, province)
        except Exception as e:
            logger.error(f"查询省份城市天气异常: {e}")
            return None
    
    @staticmethod
    async def get_weather_by_stationid(stationid: str) -> Optional[Dict[str, Any]]:
        """
        根据站点ID获取天气信息
        
        Args:
            stationid: 天气站点ID
            
        Returns:
            天气信息字典，包含原始数据和格式化信息，查询失败返回None
        """
        try:
            logger.debug(f"API查询站点天气: {stationid}")
            weather_data = await get_weather(stationid)
            
            if not weather_data:
                logger.warning(f"获取天气数据失败: {stationid}")
                return None
                
            return WeatherAPI._format_weather_data(weather_data)
        except Exception as e:
            logger.error(f"查询站点天气异常: {e}")
            return None
    
    @staticmethod
    async def search_city(city_name: str) -> Optional[Tuple[str, str]]:
        """
        搜索城市代码
        
        Args:
            city_name: 城市名称
            
        Returns:
            成功返回 (stationid, 完整城市名)，失败返回None
        """
        try:
            stationid = await search_city_code(city_name)
            if stationid:
                return stationid, city_name
            return None
        except Exception as e:
            logger.error(f"搜索城市代码异常: {e}")
            return None
    
    @staticmethod
    async def search_province_city(province: str, city: str) -> Optional[Tuple[str, str]]:
        """
        搜索省份城市代码
        
        Args:
            province: 省份名称
            city: 城市名称
            
        Returns:
            成功返回 (stationid, 完整城市名)，失败返回None
        """
        try:
            stationid = await find_city_code(province, city)
            if stationid:
                return stationid, city
            return None
        except Exception as e:
            logger.error(f"搜索省份城市代码异常: {e}")
            return None
    
    @staticmethod
    async def get_districts(province: str) -> Optional[Dict[str, Any]]:
        """
        获取省份下所有区县
        
        Args:
            province: 省份名称
            
        Returns:
            成功返回 {"province": str, "districts": List[str]}，失败返回None
        """
        try:
            result = await get_all_districts(province)
            if result["districts"]:
                return result
            return None
        except Exception as e:
            logger.error(f"获取区县列表异常: {e}")
            return None
    
    @staticmethod
    def _format_weather_data(data: Dict[str, Any], city: str = "", province: str = "") -> Dict[str, Any]:
        """
        格式化天气数据
        
        Args:
            data: 原始天气数据
            city: 城市名称
            province: 省份名称
            
        Returns:
            格式化后的天气数据
        """
        try:
            real_data = data["data"]["real"]
            station = real_data["station"]
            weather_info = real_data["weather"]
            wind_info = real_data["wind"]
            
            # 使用API返回的省份和城市信息，如果没有则使用传入的参数
            result_province = province or station.get("province", "")
            result_city = city or station.get("city", "")
            
            return {
                "success": True,
                "city": result_city,
                "province": result_province,
                "raw_data": data,
                "formatted": {
                    "weather": WeatherAPI._format_value(weather_info['info'], '{}'),
                    "temperature": WeatherAPI._format_value(weather_info['temperature'], '{}℃'),
                    "feelst": WeatherAPI._format_value(weather_info['feelst'], '{}℃'),
                    "temperature_diff": WeatherAPI._format_value(weather_info['temperatureDiff'], '{}℃'),
                    "humidity": WeatherAPI._format_value(weather_info['humidity'], '{}%'),
                    "wind_direct": WeatherAPI._format_value(wind_info['direct'], '{}'),
                    "wind_power": WeatherAPI._format_value(wind_info['power'], '{}'),
                    "wind_speed": WeatherAPI._format_value(wind_info['speed'], '{}m/s'),
                    "rain": WeatherAPI._format_value(weather_info['rain'], '{}mm'),
                    "comfort": WeatherAPI._get_comfort_desc(weather_info['icomfort']),
                    "publish_time": WeatherAPI._format_value(real_data['publish_time'], '{}'),
                    "sunrise": WeatherAPI._format_value(real_data['sunriseSunset']['sunrise'], '{}'),
                    "sunset": WeatherAPI._format_value(real_data['sunriseSunset']['sunset'], '{}')
                }
            }
        except Exception as e:
            logger.error(f"格式化天气数据异常: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    @staticmethod
    def _format_value(value, pattern):
        """
        格式化字段值：若为9999或9999.0则返回未知图案，否则返回带格式的值
        """
        str_value = str(value).strip()
        if str_value in ["9999", "9999.0"]:
            return "❓"
        return pattern.format(value)
    
    @staticmethod
    def _get_comfort_desc(level: int) -> str:
        """舒适度等级描述"""
        comfort_map = {
            -4: "很冷，极不适应",
            -3: "冷，很不舒适",
            -2: "凉，不舒适",
            -1: "凉爽，较舒适",
            0: "舒适，最可接受",
            1: "温暖，较舒适", 
            2: "暖，不舒适",
            3: "热，很不舒适",
            4: "很热，极不适应",
            9999: "❓"
        }
        return comfort_map.get(level, "未知")