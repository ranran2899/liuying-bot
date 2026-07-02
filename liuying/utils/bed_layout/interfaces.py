"""
床图模块公共接口层

定义床图模块的统一存储契约、共享常量、纯函数工具与数据载体。
本模块是整个 bed_layout 包的基础层，禁止导入 bed_layout 内部任何模块，
以避免循环依赖并确保所有上层模块共享同一份接口契约。
"""
from dataclasses import dataclass
from datetime import datetime
import uuid

# 床图允许存储的图片扩展名集合
ALLOWED_EXTENSIONS: frozenset[str] = frozenset(
    {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".ico"}
)

def validate_extension(extension: str) -> None:
    """校验图片扩展名是否受支持

    参数:
        extension: 图片扩展名（包含前导点，如 ".png"）

    异常:
        ValueError: 当扩展名不在 ALLOWED_EXTENSIONS 中时抛出
    """
    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError(f"不支持的文件类型: {extension}")


def generate_filename(filename: str | None, extension: str) -> str:
    """生成最终存储文件名

    参数:
        filename: 自定义文件名，None 时自动生成 UUID 文件名
        extension: 图片扩展名

    返回:
        str: 最终文件名，确保以指定扩展名结尾
    """
    if filename is None:
        return f"{uuid.uuid4().hex}{extension}"
    return filename if filename.endswith(extension) else f"{filename}{extension}"


@dataclass(slots=True)
class StorageStats:
    """床图存储统计信息"""

    image_count: int
    """图片总数"""
    total_size: int
    """图片总大小（字节）"""
    total_size_mb: float
    """图片总大小（MB，保留两位小数）"""
    by_content_type: dict[str, int]
    """按 MIME 类型分类的图片数量"""
    by_extension: dict[str, int]
    """按扩展名分类的图片数量"""
    by_source: dict[str, int]
    """按来源分类的图片数量"""
    by_category: dict[str, int]
    """按分类分类的图片数量"""


@dataclass(slots=True)
class ImageInfo:
    """床图图片元信息（不含二进制数据）"""

    filename: str
    """存储文件名"""
    original_filename: str | None
    """原始文件名"""
    content_type: str | None
    """MIME 类型"""
    file_size: int
    """文件大小（字节）"""
    file_hash: str | None
    """文件 SHA256 哈希"""
    source: str | None
    """图片来源"""
    category: str | None
    """图片分类"""
    tags: list[str] | None
    """图片标签列表"""
    original_url: str | None
    """原始图片 URL"""
    create_time: datetime | None
    """创建时间"""
    url: str | None
    """访问 URL（仅本地存储可生成）"""
