from enum import StrEnum


class PriorityLifecycleType(StrEnum):
    STARTUP = "STARTUP"
    """启动"""
    SHUTDOWN = "SHUTDOWN"
    """关闭"""


class BotSentType(StrEnum):
    GROUP = "GROUP"
    PRIVATE = "PRIVATE"


class BankHandleType(StrEnum):
    DEPOSIT = "DEPOSIT"
    """存款"""
    WITHDRAW = "WITHDRAW"
    """取款"""
    TRANSFER = "TRANSFER"
    """转账"""
    LOAN = "LOAN"
    """贷款"""
    REPAYMENT = "REPAYMENT"
    """还款"""
    INTEREST = "INTEREST"
    """利息"""


class EventLogType(StrEnum):
    GROUP_MEMBER_INCREASE = "GROUP_MEMBER_INCREASE"
    """群成员增加"""
    GROUP_MEMBER_DECREASE = "GROUP_MEMBER_DECREASE"
    """群成员减少"""
    KICK_MEMBER = "KICK_MEMBER"
    """踢出群成员"""
    KICK_BOT = "KICK_BOT"
    """踢出Bot"""
    LEAVE_MEMBER = "LEAVE_MEMBER"
    """主动退群"""


class CacheType(StrEnum):
    """
    缓存类型
    """

    PLUGINS = "GLOBAL_ALL_PLUGINS"
    """全局全部插件"""
    GROUPS = "GLOBAL_ALL_GROUPS"
    """全局全部群组"""
    USERS = "GLOBAL_ALL_USERS"
    """全部用户"""
    BAN = "GLOBAL_ALL_BAN"
    """全局ban列表"""
    BOT = "GLOBAL_BOT"
    """全局bot信息"""
    LEVEL = "GLOBAL_USER_LEVEL"
    """用户权限"""
    LIMIT = "GLOBAL_LIMIT"
    """插件限制"""
    SENSITIVE = "GLOBAL_SENSITIVE_WORDS"
    """敏感词列表"""
    QQ_BOT_CONFIG = "GLOBAL_QQ_BOT_CONFIG"
    """QQ机器人配置"""
    BOT_PRIORITY = "GLOBAL_BOT_PRIORITY"
    """机器人账号优先级"""


class DbLockType(StrEnum):
    """
    锁类型
    """

    CREATE = "CREATE"
    """创建"""
    DELETE = "DELETE"
    """删除"""
    UPDATE = "UPDATE"
    """更新"""
    QUERY = "QUERY"
    """查询"""
    UPSERT = "UPSERT"
    """创建或更新"""


class CurrHandle(StrEnum):
    """
    货币处理
    """
    BUY = "BUY"
    """购买"""
    GET = "GET"
    """获取"""
    PLUGIN = "PLUGIN"
    """插件花费"""


class PropHandle(StrEnum):
    """
    道具处理
    """

    BUY = "BUY"
    """购买"""
    USE = "USE"
    """使用"""
    DELETE = "DELETE"
    """删除"""
    FAILED = "FAILED"
    """失败"""
    INSUFFICIENT_ITEMS = "INSUFFICIENT_ITEMS"
    """数量不足"""
    ITEM_NOT_FOUND = "ITEM_NOT_FOUND"
    """道具不存在"""
    HANDLER_NOT_REGISTERED = "HANDLER_NOT_REGISTERED"
    """未注册使用函数"""
    ERROR = "ERROR"
    """错误"""


class PluginType(StrEnum):
    """
    插件类型
    """

    SUPERUSER = "SUPERUSER"
    """超级用户"""
    ADMIN = "ADMIN"
    """管理员"""
    SUPER_AND_ADMIN = "ADMIN_SUPER"
    """管理员以及超级用户"""
    NORMAL = "NORMAL"
    """普通插件"""
    DEPENDANT = "DEPENDANT"
    """依赖插件，一般为没有主动触发命令的插件，受权限控制"""
    HIDDEN = "HIDDEN"
    """隐藏插件，一般为没有主动触发命令的插件，不受权限控制，如消息统计"""
    PARENT = "PARENT"
    """父插件，仅仅标记"""


class BlockType(StrEnum):
    """
    禁用状态
    """

    PRIVATE = "PRIVATE"
    GROUP = "GROUP"
    ALL = "ALL"


class PluginLimitType(StrEnum):
    """
    插件限制类型
    """

    CD = "CD"
    COUNT = "COUNT"
    BLOCK = "BLOCK"


class LimitCheckType(StrEnum):
    """
    插件限制类型
    """

    PRIVATE = "PRIVATE"
    GROUP = "GROUP"
    ALL = "ALL"


class LimitWatchType(StrEnum):
    """
    插件限制监听对象
    """

    USER = "USER"
    GROUP = "GROUP"
    ALL = "ALL"


class RequestType(StrEnum):
    """
    请求类型
    """

    FRIEND = "FRIEND"
    """好友"""
    GROUP = "GROUP"
    """群组"""


class RequestHandleType(StrEnum):
    """
    请求处理类型
    """

    APPROVE = "APPROVE"
    """同意"""
    REFUSED = "REFUSED"
    """拒绝"""
    IGNORE = "IGNORE"
    """忽略"""
    EXPIRE = "EXPIRE"
    """过期或失效"""


class TaskStatus(StrEnum):
    """定时任务状态枚举"""

    RUNNING = "running"
    """运行中"""
    PAUSED = "paused"
    """已暂停"""
    COMPLETED = "completed"
    """已完成"""
    PENDING = "pending"
    """待处理"""
    FAILED = "failed"
    """失败"""


class TriggerType(StrEnum):
    """触发器类型枚举"""

    CRON = "cron"
    """Cron表达式触发器"""
    INTERVAL = "interval"
    """时间间隔触发器"""
    DATE = "date"
    """日期触发器"""

class RepoType(StrEnum):
    """仓库类型"""

    GITEE = "gitee"
    """Gitee仓库"""
    GITHUB = "github"
    """GitHub仓库"""
    ALIYUN = "aliyun"
    """阿里云Code仓库"""

class StorageType(StrEnum):
    """
    存储类型枚举
    """
    LOCAL = "local"
    """本地存储"""
    TENCENT = "tencent"
    """腾讯云COS存储"""
    BAIDU = "baidu"
    """百度云BOS存储"""
    ALIYUN = "aliyun"
    """阿里云OSS存储"""
    HUAWEI = "huawei"
    """华为云OBS存储"""


class ModeType(StrEnum):
    """图片模式类型"""

    BINARY = "1"
    """二值图"""
    CMYK = "CMYK"
    """CMYK 模式"""
    FLOAT = "F"
    """浮点模式"""
    HSV = "HSV"
    """HSV 模式"""
    INT = "I"
    """整型模式"""
    L = "L"
    """灰度模式"""
    LAB = "LAB"
    """LAB 模式"""
    PALETTE = "P"
    """调色板模式"""
    RGB = "RGB"
    """RGB 模式"""
    RGBA = "RGBA"
    """RGBA 模式"""
    RGBX = "RGBX"
    """RGBX 模式"""
    YCBCR = "YCbCr"
    """YCbCr 模式"""


class CenterType(StrEnum):
    """粘贴居中类型"""

    CENTER = "center"
    """完全居中"""
    HEIGHT = "height"
    """垂直居中"""
    WIDTH = "width"
    """水平居中"""


class FilterType(StrEnum):
    """图片滤镜类型"""

    GAUSSIAN_BLUR = "GaussianBlur"
    """高斯模糊"""
    EDGE_ENHANCE = "EDGE_ENHANCE"
    """边缘增强"""
    SMOOTH = "SMOOTH"
    """平滑"""


class GradientDirection(StrEnum):
    """渐变方向"""

    HORIZONTAL = "horizontal"
    """水平"""
    VERTICAL = "vertical"
    """垂直"""
    DIAGONAL = "diagonal"
    """对角"""
    RADIAL = "radial"
    """径向"""


class ArtFilter(StrEnum):
    """艺术滤镜类型"""

    VINTAGE = "vintage"
    """复古"""
    OIL_PAINTING = "oil_painting"
    """油画"""
    CARTOON = "cartoon"
    """卡通"""
    SKETCH = "sketch"
    """素描"""


class ModuleStyle(StrEnum):
    """二维码点阵样式"""

    SQUARE = "square"
    """方形"""
    ROUNDED = "rounded"
    """圆角"""
    CIRCLE = "circle"
    """圆形"""
    GAPPED = "gapped"
    """间距方形"""


class WaitStrategy(StrEnum):
    """重试等待策略"""

    FIXED = "fixed"
    """固定等待"""
    EXPONENTIAL = "exponential"
    """指数退避"""


class CircuitState(StrEnum):
    """熔断器状态"""

    CLOSED = "closed"
    """关闭（正常放行）"""
    OPEN = "open"
    """打开（熔断中，快速失败）"""
    HALF_OPEN = "half_open"
    """半开（试探性放行）"""


class RateLimitAlgorithm(StrEnum):
    """限流算法类型"""

    TOKEN_BUCKET = "token_bucket"
    """令牌桶"""
    SLIDING_WINDOW = "sliding_window"
    """滑动窗口"""
