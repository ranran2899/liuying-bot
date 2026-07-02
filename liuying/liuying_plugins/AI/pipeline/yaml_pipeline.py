"""YAML风格响应管道

解析LLM返回的YAML格式响应，并按结构化字段重新构建
可读的回复文本。受 YAML_PIPELINE_ENABLED 配置开关控制。
"""

import re

from ruamel.yaml import YAML

from liuying.utils.log import logger

from ..config import get_config

_CODE_FENCE_RE = re.compile(
    r"^```(?:ya?ml)?\s*\n(.*?)\n```\s*$",
    re.DOTALL | re.MULTILINE,
)
"""YAML代码块包裹正则"""

_FIELD_LABELS: dict[str, str] = {
    "reply": "回复",
    "content": "内容",
    "message": "消息",
    "reason": "理由",
    "action": "动作",
    "emotion": "情绪",
    "topic": "话题",
}
"""字段中文标签表"""


class YamlPipeline:
    """YAML响应管道

    将LLM的YAML格式回复解析为字典，再按字段构建可读文本。
    """

    def __init__(self) -> None:
        """初始化YAML管道"""
        self._yaml = YAML(typ="safe")

    def parse(self, yaml_text: str) -> dict:
        """解析YAML文本为字典

        自动剥离代码块包裹，解析失败返回空字典。

        参数:
            yaml_text: YAML格式文本

        返回:
            dict: 解析后的字典
        """
        if not yaml_text or not yaml_text.strip():
            return {}
        text = self._strip_code_fence(yaml_text.strip())
        try:
            data = self._yaml.load(text)
        except Exception as e:
            logger.debug(
                f"YAML解析失败: {e}", command="AI", e=e
            )
            return {}
        if isinstance(data, dict):
            return data
        return {}

    def build_response(self, parsed: dict) -> str:
        """根据解析结果构建回复文本

        参数:
            parsed: 解析后的字典

        返回:
            str: 可读回复文本
        """
        if not parsed or not isinstance(parsed, dict):
            return ""
        reply = (
            parsed.get("reply")
            or parsed.get("content")
            or parsed.get("message")
            or ""
        )
        if not reply:
            return ""
        reply = str(reply).strip()
        extras: list[str] = []
        for key, label in _FIELD_LABELS.items():
            if key in ("reply", "content", "message"):
                continue
            if parsed.get(key):
                extras.append(
                    f"[{label}] {parsed[key]}"
                )
        if not extras:
            return reply
        return f"{reply}\n" + "\n".join(extras)

    def process(self, yaml_text: str) -> str:
        """一体化处理：解析并构建回复

        受 YAML_PIPELINE_ENABLED 配置开关控制，
        关闭时直接返回原始文本。

        参数:
            yaml_text: LLM返回的YAML文本

        返回:
            str: 构建的回复文本
        """
        if not get_config("YAML_PIPELINE_ENABLED", False):
            return yaml_text
        parsed = self.parse(yaml_text)
        if not parsed:
            return yaml_text
        built = self.build_response(parsed)
        return built or yaml_text

    def _strip_code_fence(self, text: str) -> str:
        """剥离YAML代码块包裹

        参数:
            text: 原始文本

        返回:
            str: 剥离后的文本
        """
        match = _CODE_FENCE_RE.match(text)
        if match:
            return match.group(1)
        return text


yaml_pipeline = YamlPipeline()
"""YAML管道单例"""
