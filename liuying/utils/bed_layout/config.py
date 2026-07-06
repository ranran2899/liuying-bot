"""
床图模块配置

负责床图模块所有配置项的统一注册与动态获取。
所有上层模块通过 get_config / get_default_storage 等函数访问配置，
禁止再使用 Pydantic BaseModel 中转层。
"""
from typing import Any

from liuying.configs.config import Config
from liuying.utils.enum import StorageType

_CONFIG_GROUP = "bed_layout"

# 床图模块所有配置项注册列表
# 云存储服务商配置统一以 dict 类型注册，运行时直接以字典方式访问
BED_LAYOUT_CONFIGS: list[dict[str, Any]] = [
    {
        "key": "HOST",
        "default": "127.0.0.1",
        "type": str,
        "help": "床图服务监听地址 | 如: 127.0.0.1(仅本机访问), 0.0.0.0(允许外部访问)",
    },
    {
        "key": "PORT",
        "default": 8088,
        "type": int,
        "help": "床图服务监听端口 | 如: 8088, 需确保端口未被占用",
    },
    {
        "key": "DB_NAME",
        "default": "bed_layout_db",
        "type": str,
        "help": "数据库名称 | 用于存储床图图片数据",
    },
    {
        "key": "MAX_FILE_SIZE",
        "default": 10485760,
        "type": int,
        "help": "最大文件大小(字节) | 默认10MB, 如: 10485760(10MB), 20971520(20MB)",
    },
    {
        "key": "DEFAULT_STORAGE",
        "default": "local",
        "type": str,
        "help": "默认存储类型 | 可选值: local(数据库), tencent, baidu, aliyun, huawei",
    },
    {
        "key": "TENCENT_COS_CONFIG",
        "default": {
            "bucket_name": "",
            "region": "",
            "secret_id": "",
            "secret_key": "",
            "enable_audit": False,
        },
        "type": dict,
        "help": (
            "腾讯云COS对象存储配置\n"
            " - bucket_name: 存储桶名称\n"
            " - region: 所属地域\n"
            " - secret_id/secret_key: 用户密钥\n"
            " - enable_audit: 是否审核内容"
        ),
    },
    {
        "key": "BAIDU_BOS_CONFIG",
        "default": {
            "bucket_name": "",
            "endpoint": "",
            "access_key": "",
            "secret_key": "",
            "audit_mode": 0,
        },
        "type": dict,
        "help": (
            "(推荐)百度云BOS对象存储配置\n"
            " - bucket_name: 存储桶名称\n"
            " - endpoint: 完整官方域名\n"
            " - access_key/secret_key: 百度BCE密钥\n"
            " - audit_mode: 审核模式(0不审核, 1使用oss+审核, 2仅审核)"
        ),
    },
    {
        "key": "ALIYUN_OSS_CONFIG",
        "default": {
            "endpoint": "",
            "bucket_name": "",
            "access_key_id": "",
            "access_key_secret": "",
            "enable_audit": False,
        },
        "type": dict,
        "help": (
            "阿里云OSS对象存储配置\n"
            " - endpoint: EndPoint地址\n"
            " - bucket_name: 存储桶名称\n"
            " - access_key_id/access_key_secret: 访问密钥\n"
            " - enable_audit: 是否审核图片"
        ),
    },
    {
        "key": "HUAWEI_OBS_CONFIG",
        "default": {
            "endpoint": "",
            "bucket_name": "",
            "access_key": "",
            "secret_key": "",
        },
        "type": dict,
        "help": (
            "华为云OBS对象存储配置\n"
            " - endpoint: 终端节点地址\n"
            " - bucket_name: 存储桶名称\n"
            " - access_key/secret_key: 访问密钥"
        ),
    },
    {
        "key": "PUBLIC_ADDRESS_ENABLED",
        "default": False,
        "type": bool,
        "help": "是否开启公网地址 | True: 开启, False: 关闭",
    },
    {
        "key": "PUBLIC_ADDRESS_HOST",
        "default": "",
        "type": str,
        "help": "公网地址 | 如: example.com 或 123.123.123.123",
    },
    {
        "key": "PUBLIC_ADDRESS_PORT",
        "default": None,
        "type": int | None,
        "help": "公网端口(可选) | 如: 9999，留空则自动判断",
    },
    {
        "key": "PUBLIC_ADDRESS_USE_HTTPS",
        "default": False,
        "type": bool,
        "help": "公网地址是否使用HTTPS | True: 使用https://, False: 使用http://",
    },
    {
        "key": "ENABLE_HTTPS",
        "default": False,
        "type": bool,
        "help": "是否启用HTTPS | True: 启用HTTPS服务器, False: 使用HTTP服务器",
    },
    {
        "key": "SSL_CERT_FILE",
        "default": "",
        "type": str,
        "help": "SSL证书文件路径 | 如: cert.pem，留空则自动生成自签名证书",
    },
    {
        "key": "SSL_KEY_FILE",
        "default": "",
        "type": str,
        "help": "SSL私钥文件路径 | 如: key.pem，留空则自动生成自签名证书",
    },
    {
        "key": "API_KEY",
        "default": "",
        "type": str,
        "help": "上传接口API密钥 | 留空则禁用外部上传（仅本机可访问）",
    },
    {
        "key": "ALLOWED_UPLOAD_IPS",
        "default": ["127.0.0.1", "::1"],
        "type": list[str],
        "help": "允许上传的IP白名单 | 默认仅允许本机访问上传接口",
    },
]


def get_config(key: str, default: Any = None) -> Any:
    """获取床图模块配置项

    参数:
        key: 配置键名（不区分大小写）
        default: 未找到时的默认值

    返回:
        Any: 配置值
    """
    return Config.get_config(_CONFIG_GROUP, key, default)


def get_default_storage(storage_type: StorageType | None = None) -> StorageType:
    """获取默认存储类型

    参数:
        storage_type: 显式指定的存储类型，非 None 时直接返回

    返回:
        StorageType: 实际使用的存储类型
    """
    if storage_type is not None:
        return storage_type
    storage_str = get_config("DEFAULT_STORAGE", "local")
    try:
        return StorageType(storage_str)
    except ValueError:
        return StorageType.LOCAL


def set_default_storage(storage_type: StorageType) -> None:
    """设置默认存储类型并持久化

    参数:
        storage_type: 存储类型
    """
    Config.set_config(
        _CONFIG_GROUP, "DEFAULT_STORAGE", storage_type.value, auto_save=True
    )


def get_provider_config(key: str) -> dict[str, Any]:
    """获取云存储服务商配置字典

    参数:
        key: 配置键名，如 "TENCENT_COS_CONFIG"

    返回:
        dict[str, Any]: 配置字典，缺失时返回空字典
    """
    value = get_config(key, {})
    return value if isinstance(value, dict) else {}


def register_configs() -> None:
    """注册床图模块所有配置项"""
    for config_item in BED_LAYOUT_CONFIGS:
        Config.add_plugin_config(
            _CONFIG_GROUP,
            config_item["key"],
            config_item["default"],
            help=config_item["help"],
            default_value=config_item["default"],
            type=config_item["type"],
        )


register_configs()
