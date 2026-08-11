from typing import ClassVar

type MessageMap = dict[str, list[str]]


class MessageManager:
    """消息管理器"""
    data: ClassVar[MessageMap] = {}

    @classmethod
    def add(cls, uid: str, msg_id: str):
        cls.data.setdefault(uid, []).append(msg_id)
        cls.remove_check(uid)

    @classmethod
    def check(cls, uid: str, msg_id: str) -> bool:
        items = cls.data.get(uid)
        return items is not None and msg_id in items

    @classmethod
    def remove_check(cls, uid: str):
        if (items := cls.data.get(uid)) and len(items) > 200:
            cls.data[uid] = items[100:]

    @classmethod
    def get(cls, uid: str) -> list[str]:
        return cls.data.get(uid, [])
