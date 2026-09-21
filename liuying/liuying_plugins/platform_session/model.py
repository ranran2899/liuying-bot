"""统一会话数据模型"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from enum import IntEnum
import json
from typing import Any, TypedDict

from .constraint import SupportAdapter, SupportScope
from .util import DatetimeJsonEncoder


class BasicInfo(TypedDict):
    """机器人基础信息"""

    self_id: str
    """机器人自身id"""
    adapter: SupportAdapter
    """所属适配器"""
    scope: SupportScope
    """平台范围"""


class SceneType(IntEnum):
    """对话场景类型"""

    PRIVATE = 0
    """私聊场景"""
    GROUP = 1
    """群聊场景"""
    GUILD = 2
    """频道场景"""
    CHANNEL_TEXT = 3
    """子频道文本场景"""
    CHANNEL_CATEGORY = 4
    """频道分类场景"""
    CHANNEL_VOICE = 5
    """子频道语音场景"""


class ModelMixin:
    """序列化能力基类，统一 dump/dump_json 行为

    以 __slots__=() 保证子类 dataclass(slots=True) 的槽位优化不被破坏。
    """

    __slots__ = ()

    def dump(self) -> dict[str, Any]:
        """序列化为字典"""
        return json.loads(self.dump_json())

    def dump_json(self, indent: int | None = None) -> str:
        """序列化为 JSON 字符串"""
        return json.dumps(
            asdict(self), ensure_ascii=False, indent=indent, cls=DatetimeJsonEncoder
        )


@dataclass(slots=True)
class Scene(ModelMixin):
    """对话场景，如群组、频道、私聊等"""

    id: str
    """场景id"""
    type: SceneType
    """场景类型"""
    name: str | None = None
    """场景名称"""
    avatar: str | None = None
    """场景头像"""
    parent: Scene | None = None
    """父级场景"""

    @property
    def is_private(self) -> bool:
        """是否私聊场景"""
        return self.type == SceneType.PRIVATE

    @property
    def is_group(self) -> bool:
        """是否群聊场景"""
        return self.type == SceneType.GROUP

    @property
    def is_guild(self) -> bool:
        """是否频道场景"""
        return self.type == SceneType.GUILD

    @property
    def is_channel(self) -> bool:
        """是否子频道场景"""
        return self.type.value >= SceneType.CHANNEL_TEXT.value

    def __hash__(self) -> int:
        return hash(self.id)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Scene) and self.id == other.id

    @classmethod
    def load(cls, data: dict) -> Scene:
        """从字典反序列化"""
        _data = data.copy()
        _data["type"] = SceneType(data["type"])
        if data.get("parent"):
            _data["parent"] = cls.load(data["parent"])
        return cls(**_data)


@dataclass(slots=True)
class User(ModelMixin):
    """用户信息"""

    id: str
    """用户id"""
    name: str | None = None
    """用户名"""
    nick: str | None = None
    """用户昵称"""
    avatar: str | None = None
    """用户头像"""
    gender: str = "unknown"
    """用户性别"""

    def __hash__(self) -> int:
        return hash(self.id)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, User) and self.id == other.id

    @classmethod
    def load(cls, data: dict) -> User:
        """从字典反序列化"""
        return cls(**data)


@dataclass(slots=True)
class Role(ModelMixin):
    """群员角色信息"""

    id: str
    """角色id"""
    level: int = 0
    """角色等级/权限"""
    name: str | None = None
    """角色名称"""

    @classmethod
    def load(cls, data: dict) -> Role:
        """从字典反序列化"""
        return cls(**data)


@dataclass(slots=True)
class MuteInfo(ModelMixin):
    """禁言信息"""

    muted: bool
    """是否被禁言"""
    duration: timedelta
    """禁言时长"""
    start_at: datetime | None = None
    """禁言开始时间"""

    def __post_init__(self) -> None:
        if self.duration.total_seconds() < 1:
            self.muted = False
        if self.start_at and (datetime.now() - self.start_at) > self.duration:
            self.muted = False

    @classmethod
    def load(cls, data: dict) -> MuteInfo:
        """从字典反序列化"""
        _data = data.copy()
        _data["duration"] = timedelta(seconds=data["duration"])
        if data.get("start_at"):
            _data["start_at"] = datetime.fromtimestamp(data["start_at"])
        return cls(**_data)


@dataclass(slots=True)
class Member(ModelMixin):
    """群员信息"""

    user: User
    """群员用户信息"""
    nick: str | None = None
    """群员昵称"""
    mute: MuteInfo | None = None
    """群员禁言信息"""
    joined_at: datetime | None = None
    """加入时间"""
    roles: list[Role] = field(default_factory=list)
    """群员角色"""

    @property
    def id(self) -> str:
        """群员用户id"""
        return self.user.id

    @property
    def role(self) -> Role | None:
        """权限最高的角色"""
        if not self.roles:
            return None
        return max(self.roles, key=lambda r: r.level)

    @classmethod
    def load(cls, data: dict) -> Member:
        """从字典反序列化"""
        _data = data.copy()
        _data["user"] = User.load(data["user"])
        if data.get("roles"):
            _data["roles"] = [Role.load(role) for role in data["roles"]]
        if data.get("mute"):
            _data["mute"] = MuteInfo.load(data["mute"])
        if data.get("joined_at"):
            _data["joined_at"] = datetime.fromtimestamp(data["joined_at"])
        return cls(**_data)


@dataclass(slots=True)
class Session(ModelMixin):
    """统一会话信息"""

    self_id: str
    """机器人id"""
    adapter: str | SupportAdapter
    """适配器名称"""
    scope: str | SupportScope
    """平台范围"""
    scene: Scene
    """场景信息"""
    user: User
    """用户信息"""
    member: Member | None = None
    """群员信息"""
    operator: Member | None = None
    """操作者信息"""
    platform: str | set[str] | None = None
    """平台名称，仅当目标适配器存在多个平台时使用"""

    @property
    def id(self) -> str:
        """会话唯一标识符"""
        if self.scene.is_private:
            return self.scene_path
        return f"{self.scene_path}_{self.user.id}"

    @property
    def scene_path(self) -> str:
        """会话的场景路径，类似于 event.get_session_id()"""
        if self.scene.is_private:
            if self.scene.parent:
                return f"{self.scene.parent.id}_{self.user.id}"
            return self.user.id
        if self.scene.is_group:
            return self.scene.id
        if self.scene.parent:
            return f"{self.scene.parent.id}_{self.scene.id}"
        return self.scene.id

    @property
    def guild(self) -> Scene | None:
        """父级频道"""
        if self.scene.is_guild:
            return self.scene
        if self.scene.is_channel:
            return self.scene.parent
        return None

    @property
    def channel(self) -> Scene | None:
        """子频道"""
        if self.scene.is_channel:
            return self.scene
        return None

    @property
    def group(self) -> Scene | None:
        """群组"""
        if self.scene.is_group:
            return self.scene
        return None

    @property
    def friend(self) -> Scene | None:
        """好友私聊场景"""
        if self.scene.is_private:
            return self.scene
        return None

    @property
    def basic(self) -> BasicInfo:
        """机器人基础信息"""
        return {
            "self_id": self.self_id,
            "adapter": SupportAdapter(self.adapter),
            "scope": SupportScope(self.scope),
        }

    def __hash__(self) -> int:
        return hash(self.id)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Session) and self.id == other.id

    @classmethod
    def load(cls, data: dict) -> Session:
        """从字典反序列化"""
        _data = data.copy()
        _data["adapter"] = SupportAdapter(data["adapter"])
        _data["scope"] = SupportScope(data["scope"])
        _data["scene"] = Scene.load(data["scene"])
        _data["user"] = User.load(data["user"])
        if data.get("member"):
            _data["member"] = Member.load(data["member"])
        if data.get("operator"):
            _data["operator"] = Member.load(data["operator"])
        return cls(**_data)
