"""
床图模块公共接口层

定义床图模块共享的常量与纯函数工具。
本模块是整个 bed_layout 包的基础层，禁止导入 bed_layout 内部任何模块，
以避免循环依赖并确保所有上层模块共享同一份接口契约。
"""
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
