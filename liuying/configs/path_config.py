from pathlib import Path

IMAGE_PATH = Path() / "resources" / "image"
"""图片资源"""
RECORD_PATH = Path() / "resources" / "record"
"""录音资源"""
TEXT_PATH = Path() / "resources" / "text"
"""文本资源"""
LOG_PATH = Path() / "log"
"""日志资源"""
FONT_PATH = Path() / "resources" / "font"
"""字体资源"""
DATA_PATH = Path() / "data"
"""数据资源"""
TEMP_PATH = Path() / "resources" / "temp"
"""临时资源"""
THEMES_PATH = Path() / "resources" / "themes"
"""主题资源"""
TEMPLATE_PATH = Path() / "resources" / "template"
"""模板资源"""
PLUGIN_PATH = Path() / "liuying" / "plugins"
"""插件资源"""
UI_CACHE_PATH = TEMP_PATH / "ui_cache"
"""UI缓存资源"""

for p in (
    IMAGE_PATH,
    RECORD_PATH,
    TEXT_PATH,
    LOG_PATH,
    FONT_PATH,
    DATA_PATH,
    TEMP_PATH,
    UI_CACHE_PATH,
    TEMPLATE_PATH,
    PLUGIN_PATH,
):
    p.mkdir(parents=True, exist_ok=True)
