"""知识书 Lorebook

按关键词触发额外知识注入到 prompt。
当用户消息命中某条目的触发关键词时，将该条目内容拼装为
额外上下文，用于补充人格/世界观/设定类知识。
"""

from liuying.utils.log import logger

from ...config import get_config


class Lorebook:
    """知识书

    管理触发关键词与对应知识条目的映射，支持匹配与上下文构建。
    """

    def __init__(self) -> None:
        """初始化知识书"""
        self._entries: list[dict[str, str]] = []
        """条目列表，每项含 trigger/content"""

    def add_entry(self, trigger: str, content: str) -> None:
        """添加知识条目

        参数:
            trigger: 触发关键词（多个以英文逗号分隔）
            content: 知识内容
        """
        trigger = (trigger or "").strip()
        content = (content or "").strip()
        if not trigger or not content:
            return
        self._entries.append(
            {"trigger": trigger, "content": content}
        )
        logger.debug(
            f"添加知识书条目: trigger={trigger}",
            command="AI",
        )

    def match(self, text: str) -> list[str]:
        """匹配文本命中的知识内容

        参数:
            text: 待匹配文本

        返回:
            list[str]: 命中的知识内容列表
        """
        if not text:
            return []
        lowered = text.lower()
        hits: list[str] = []
        for entry in self._entries:
            triggers = [
                t.strip().lower()
                for t in entry["trigger"].split(",")
                if t.strip()
            ]
            if any(t in lowered for t in triggers):
                hits.append(entry["content"])
        return hits

    def build_context(self, text: str) -> str:
        """构建命中知识的上下文文本

        受 LOREBOOK_ENABLED 配置开关控制。

        参数:
            text: 待匹配文本

        返回:
            str: 拼接后的上下文，无命中时返回空串
        """
        if not get_config("LOREBOOK_ENABLED", True):
            return ""
        hits = self.match(text)
        if not hits:
            return ""
        lines = ["\n\n[扩展知识]"]
        for item in hits:
            lines.append(f"- {item}")
        return "\n".join(lines)

    def remove_entry(self, trigger: str) -> bool:
        """删除指定触发词的条目

        参数:
            trigger: 触发关键词

        返回:
            bool: 是否删除成功
        """
        before = len(self._entries)
        self._entries = [
            e for e in self._entries if e["trigger"] != trigger
        ]
        return len(self._entries) < before

    def clear(self) -> None:
        """清空全部条目"""
        self._entries.clear()

    def list_entries(self) -> list[dict[str, str]]:
        """列出全部条目

        返回:
            list[dict]: 条目副本列表
        """
        return [dict(e) for e in self._entries]


lorebook = Lorebook()
"""知识书单例"""
