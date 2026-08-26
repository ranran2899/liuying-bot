from pathlib import Path

RESOURCES_PATH = Path() / "resources"
"""资源包根目录"""
WEB_UI_PATH = Path() / "data" / "web_ui"
"""WebUI 静态资源目录"""
IMAGE_PATH = RESOURCES_PATH / "image"
"""图片资源"""
RECORD_PATH = RESOURCES_PATH / "record"
"""录音资源"""
TEXT_PATH = RESOURCES_PATH / "text"
"""文本资源"""
LOG_PATH = Path() / "log"
"""日志资源"""
FONT_PATH = RESOURCES_PATH / "font"
"""字体资源"""
DATA_PATH = Path() / "data"
"""数据资源"""
DB_PATH = DATA_PATH / "db"
"""数据库资源"""
TEMP_PATH = RESOURCES_PATH / "temp"
"""临时资源"""
THEMES_PATH = RESOURCES_PATH / "themes"
"""主题资源"""
TEMPLATE_PATH = RESOURCES_PATH / "template"
"""模板资源"""
PLUGIN_PATH = Path() / "liuying" / "plugins"
"""插件资源"""
UI_CACHE_PATH = TEMP_PATH / "ui_cache"
"""UI缓存资源"""

for p in (
    RESOURCES_PATH,
    WEB_UI_PATH,
    IMAGE_PATH,
    RECORD_PATH,
    TEXT_PATH,
    LOG_PATH,
    FONT_PATH,
    DATA_PATH,
    DB_PATH,
    TEMP_PATH,
    UI_CACHE_PATH,
    THEMES_PATH,
    TEMPLATE_PATH,
    PLUGIN_PATH,
):
    p.mkdir(parents=True, exist_ok=True)
