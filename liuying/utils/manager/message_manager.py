from typing import ClassVar

type MessageRecord = tuple[str, str | None]
"""消息记录: (消息ID, QQ官方适配器openid)，openid 为 None 表示无需会话标识的平台"""


class MessageManager:
    """消息管理器"""
    data: ClassVar[dict[str, list[MessageRecord]]] = {}

    @classmethod
    def add(cls, uid: str, msg_id: str, openid: str | None = None) -> None:
        """记录用户消息ID。

        将消息ID追加到指定用户的历史记录中，并触发长度检查。

        参数:
            uid: 用户唯一标识。
            msg_id: 待记录的消息ID。
            openid: QQ官方适配器的群或用户openid，撤回时定位会话。
        """
        cls.data.setdefault(uid, []).append((msg_id, openid))
        cls.remove_check(uid)

    @classmethod
    def check(cls, uid: str, msg_id: str) -> bool:
        """检查消息ID是否已存在于用户记录中。

        参数:
            uid: 用户唯一标识。
            msg_id: 待检查的消息ID。

        返回:
            若存在则返回 True，否则返回 False。
        """
        items = cls.data.get(uid)
        return items is not None and any(m == msg_id for m, _ in items)

    @classmethod
    def pop_last(cls, uid: str) -> MessageRecord | None:
        """取出并移除用户最近一条消息记录。

        QQ官方适配器的引用事件不携带被引用消息ID，撤回时定位bot最近发送的消息。

        参数:
            uid: 用户唯一标识。

        返回:
            最近的消息记录，无记录时返回 None。
        """
        items = cls.data.get(uid)
        return items.pop() if items else None

    @classmethod
    def remove_check(cls, uid: str) -> None:
        """检查并裁剪用户消息记录长度。

        当某用户消息记录超过200条时，丢弃前100条以控制内存占用。

        参数:
            uid: 用户唯一标识。
        """
        if (items := cls.data.get(uid)) and len(items) > 200:
            cls.data[uid] = items[100:]

    @classmethod
    def get(cls, uid: str) -> list[str]:
        """获取用户全部消息ID记录。

        参数:
            uid: 用户唯一标识。

        返回:
            该用户的消息ID列表，无记录时返回空列表。
        """
        return [msg_id for msg_id, _ in cls.data.get(uid, [])]
