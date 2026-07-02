"""人设专属知识库

按人格名存储与检索专属知识，为人格补充独立的事实/设定信息。
基于内存字典实现，进程重启后清空，适合临时性知识注入。
"""

from liuying.utils.log import logger


class PersonaKnowledge:
    """人设专属知识库

    按人格名隔离知识条目，支持按 key 读写、按人格批量获取。
    """

    def __init__(self) -> None:
        """初始化人设知识库"""
        self._store: dict[str, dict[str, str]] = {}
        """人格 -> {key: value}"""

    def get(self, persona: str, key: str) -> str | None:
        """获取指定人格的某条知识

        参数:
            persona: 人格名
            key: 知识键

        返回:
            str | None: 知识值，不存在返回None
        """
        bucket = self._store.get(persona)
        if not bucket:
            return None
        return bucket.get(key)

    def set(self, persona: str, key: str, value: str) -> None:
        """写入指定人格的知识条目

        参数:
            persona: 人格名
            key: 知识键
            value: 知识值
        """
        bucket = self._store.setdefault(persona, {})
        bucket[key] = value
        logger.debug(
            f"写入人设知识: persona={persona} key={key}",
            command="AI",
        )

    def get_all(self, persona: str) -> dict:
        """获取指定人格的全部知识

        参数:
            persona: 人格名

        返回:
            dict: 该人格全部知识副本，无人格时返回空字典
        """
        bucket = self._store.get(persona)
        if not bucket:
            return {}
        return dict(bucket)

    def remove(self, persona: str, key: str) -> bool:
        """删除指定人格的某条知识

        参数:
            persona: 人格名
            key: 知识键

        返回:
            bool: 是否删除成功
        """
        bucket = self._store.get(persona)
        if not bucket or key not in bucket:
            return False
        bucket.pop(key)
        return True

    def clear(self, persona: str | None = None) -> None:
        """清空知识库

        参数:
            persona: 指定人格时只清空该人格，None清空全部
        """
        if persona is None:
            self._store.clear()
        else:
            self._store.pop(persona, None)

    def build_prompt_block(self, persona: str) -> str:
        """构建人格知识的提示词块

        参数:
            persona: 人格名

        返回:
            str: 提示词文本，无知识时返回空串
        """
        bucket = self.get_all(persona)
        if not bucket:
            return ""
        lines = [f"\n\n[{persona}专属知识]"]
        for key, value in bucket.items():
            lines.append(f"- {key}: {value}")
        return "\n".join(lines)


persona_knowledge = PersonaKnowledge()
"""人设知识库单例"""
