"""人格管理

加载YAML人格配置文件，构建系统提示词，管理用户画像。
支持用户级人格切换：每个用户可独立选择当前bot人格，
人格间对话历史与记忆完全隔离。
"""

from datetime import datetime
from pathlib import Path

from ruamel.yaml import YAML

from liuying.services.cache import CacheDict
from liuying.utils.log import logger
from liuying.utils.user.favor import UserFavor

from ..config import get_config, set_config
from ..models.user_persona import UserPersonaProfile
from ..models.user_persona_selection import UserPersonaSelection
from .llm import llm_helper as _default_llm_helper

_PERSONAS_DIR = Path(__file__).parent.parent / "personas"
"""人格配置文件目录"""

_FAVOR_ATTITUDES: dict[str, str] = {
    "陌生": "礼貌但保持距离，不主动套近乎",
    "初识": "友好但不过分亲近，保持基本礼貌",
    "熟悉": "可以自然交流，偶尔开玩笑",
    "友好": "态度温和，愿意帮助对方",
    "信任": "像朋友一样自然，可以分享日常",
    "亲密": "关系很好，可以聊更多话题",
    "挚友": "像老朋友一样自然，可以畅所欲言",
    "至交": "非常亲密，可以分享内心想法",
    "知己": "心灵相通，可以深入交流",
    "恋人": "温柔亲密，主动表达关心和爱意",
}
"""好感度态度档"""

_PERSONA_UPDATE_PROMPT = """请根据以下用户与AI的对话历史，生成一份用户画像。

对话历史：
{history}

请用简洁的语言描述这个用户的特征，包括：
- 性格特点
- 兴趣爱好
- 交流风格
- 特别偏好

只返回画像描述文本，不要其他内容。画像应不超过200字。"""


class PersonaManager:
    """人格管理器

    加载YAML人格配置，构建系统提示词，管理用户画像。
    支持用户级人格切换：每个用户可独立选择当前bot人格。
    """

    def __init__(self, personas_dir: Path | None = None) -> None:
        """初始化人格管理器

        参数:
            personas_dir: 人格文件目录，None时用默认目录
        """
        self.personas_dir = personas_dir or _PERSONAS_DIR
        self._yaml = YAML(typ="safe")
        self._cache = CacheDict("AI_PERSONA")
        """人格配置缓存（永不过期）"""

    def get_active_persona_name(self) -> str:
        """获取全局默认人格名

        从 DEFAULT_PERSONA 配置读取，未配置时回退到 "liuying"。
        此值为用户未单独设置人格时的兜底值。

        返回:
            str: 全局默认人格名
        """
        name = get_config("DEFAULT_PERSONA", "liuying")
        if not name or not isinstance(name, str):
            return "liuying"
        return name

    def set_active_persona(self, name: str) -> None:
        """切换全局默认人格并持久化

        校验人格存在后写入 DEFAULT_PERSONA 配置项，
        并持久化到 plugins2config.yaml。

        参数:
            name: 人格名称（YAML文件名，不含扩展名）

        异常:
            FileNotFoundError: 人格文件不存在
        """
        self.load_persona(name)
        set_config("DEFAULT_PERSONA", name, auto_save=True)
        logger.info(
            f"已切换全局默认人格: {name}", command="AI"
        )

    async def get_user_persona_name(self, user_id: str) -> str:
        """获取用户当前激活的人格名

        优先读取用户级人格选择（UserPersonaSelection），
        未设置时回退到全局默认人格（DEFAULT_PERSONA）。

        参数:
            user_id: 用户ID

        返回:
            str: 用户当前激活的人格名
        """
        try:
            name = await UserPersonaSelection.get_persona_name(user_id)
            if name and self._persona_exists(name):
                return name
        except Exception as e:
            logger.debug(
                f"读取用户人格选择失败，回退全局默认: {e}",
                command="AI",
                e=e,
            )
        return self.get_active_persona_name()

    async def set_user_persona(
        self, user_id: str, name: str
    ) -> None:
        """设置用户当前激活的人格

        校验人格存在后写入 UserPersonaSelection 表，
        实现用户级人格切换。

        参数:
            user_id: 用户ID
            name: 人格名称（YAML文件名，不含扩展名）

        异常:
            FileNotFoundError: 人格文件不存在
        """
        self.load_persona(name)
        await UserPersonaSelection.set_persona_name(user_id, name)
        logger.info(
            f"用户 {user_id} 切换人格: {name}",
            command="AI",
        )

    async def clear_user_persona(self, user_id: str) -> bool:
        """清除用户的人格选择（回退到全局默认）

        参数:
            user_id: 用户ID

        返回:
            bool: 是否清除成功
        """
        return await UserPersonaSelection.clear_persona_name(user_id)

    def _persona_exists(self, name: str) -> bool:
        """检查人格文件是否存在

        参数:
            name: 人格名称（YAML文件名，不含扩展名）

        返回:
            bool: 是否存在
        """
        return (self.personas_dir / f"{name}.yaml").exists()

    def load_persona(self, name: str) -> dict:
        """加载指定人格

        参数:
            name: 人格名称

        返回:
            dict: 人格配置字典

        异常:
            FileNotFoundError: 人格文件不存在
        """
        if name in self._cache:
            return self._cache[name]
        persona_path = self.personas_dir / f"{name}.yaml"
        if not persona_path.exists():
            raise FileNotFoundError(f"人格文件不存在: {persona_path}")
        with open(persona_path, encoding="utf-8") as f:
            persona = self._yaml.load(f) or {}
        self._cache[name] = persona
        logger.debug(
            f"加载人格: {name}", command="AI"
        )
        return persona

    async def get_persona_by_name(self, name: str) -> dict:
        """按人格名获取人格配置

        参数:
            name: 人格名称

        返回:
            dict: 人格配置字典，加载失败时回退到默认或内置兜底
        """
        try:
            return self.load_persona(name)
        except FileNotFoundError:
            try:
                return self.load_persona("default")
            except FileNotFoundError:
                return {
                    "name": "AI助手",
                    "system_prompt": "你是一个友好的AI助手。",
                    "traits": {},
                    "taboos": [],
                }

    async def get_user_persona_config(self, user_id: str) -> dict:
        """获取用户当前激活的人格配置

        读取用户级人格选择，加载对应人格文件。
        未设置或加载失败时回退到全局默认或内置兜底。

        参数:
            user_id: 用户ID

        返回:
            dict: 人格配置字典
        """
        active_name = await self.get_user_persona_name(user_id)
        return await self.get_persona_by_name(active_name)

    def get_default_persona(self) -> dict:
        """获取全局默认人格配置（同步）

        读取 DEFAULT_PERSONA 配置，加载对应人格文件。
        供需要同步获取人格的场景使用（如TTS配置提取）。

        返回:
            dict: 人格配置字典
        """
        active_name = self.get_active_persona_name()
        try:
            return self.load_persona(active_name)
        except FileNotFoundError:
            try:
                return self.load_persona("default")
            except FileNotFoundError:
                return {
                    "name": "AI助手",
                    "system_prompt": "你是一个友好的AI助手。",
                    "traits": {},
                    "taboos": [],
                }

    def list_personas(self) -> list[str]:
        """列出所有可用人格名

        返回:
            list[str]: 人格名称列表
        """
        if not self.personas_dir.exists():
            return []
        return [
            f.stem
            for f in self.personas_dir.glob("*.yaml")
            if f.is_file()
        ]

    def list_personas_with_desc(self) -> list[dict]:
        """列出所有可用人格及其描述

        返回:
            list[dict]: 人格信息列表，每项含 name/display_name/description
        """
        names = self.list_personas()
        result: list[dict] = []
        for name in names:
            try:
                persona = self.load_persona(name)
                result.append(
                    {
                        "name": name,
                        "display_name": persona.get("name", name),
                        "description": self._extract_persona_desc(
                            persona
                        ),
                    }
                )
            except Exception as e:
                logger.debug(
                    f"加载人格描述失败: {name} {e}",
                    command="AI",
                    e=e,
                )
                result.append(
                    {
                        "name": name,
                        "display_name": name,
                        "description": "",
                    }
                )
        return result

    def _extract_persona_desc(self, persona: dict) -> str:
        """从人格配置提取简短描述

        参数:
            persona: 人格配置字典

        返回:
            str: 简短描述（不超过80字）
        """
        prompt = persona.get("system_prompt", "")
        if not prompt:
            return ""
        first_line = ""
        for line in prompt.split("\n"):
            line = line.strip()
            _skip = ("姓名", "年龄", "性别")
            if line and not any(line.startswith(s) for s in _skip):
                first_line = line
                break
        if not first_line:
            first_line = prompt.strip().split("\n")[0].strip()
        return first_line[:80]

    async def build_system_prompt(
        self,
        persona: dict,
        user_id: str,
        group_id: str | None = None,
    ) -> str:
        """构建系统提示词

        参数:
            persona: 人格配置
            user_id: 用户ID
            group_id: 群组ID

        返回:
            str: 完整系统提示词
        """
        parts: list[str] = []

        base_prompt = persona.get("system_prompt", "")
        parts.append(base_prompt)

        favor_info = await UserFavor.get_favor_info(user_id)
        favor_level = favor_info.get("favor_level", "陌生")
        attitude = _FAVOR_ATTITUDES.get(favor_level, "")
        if attitude:
            parts.append(
                f"\n\n[好感度与语气]\n当前好感: {favor_level}\n"
                f"语气: {attitude}"
            )

        traits = persona.get("traits", {})
        if traits and isinstance(traits, dict):
            trait_lines = []
            for key, val in traits.items():
                if isinstance(val, list):
                    val = "、".join(str(v) for v in val)
                trait_lines.append(f"- {key}: {val}")
            if trait_lines:
                parts.append("\n\n[人格特征]\n" + "\n".join(trait_lines))

        taboos = persona.get("taboos", [])
        if taboos and isinstance(taboos, list):
            taboo_lines = [f"- {t}" for t in taboos]
            parts.append("\n\n[禁忌事项]\n" + "\n".join(taboo_lines))

        user_persona = await UserPersonaProfile.get_persona(user_id)
        if user_persona:
            parts.append(f"\n\n[用户画像]\n{user_persona}")

        max_len = persona.get("max_response_length", 200)
        parts.append(f"\n\n[输出要求]\n回复保持简洁，不超过{max_len}字")

        return "".join(parts)

    async def get_user_persona(self, user_id: str) -> str:
        """获取用户画像

        参数:
            user_id: 用户ID

        返回:
            str: 用户画像描述，无则返回空串
        """
        return await UserPersonaProfile.get_persona(user_id)

    async def update_user_persona(
        self,
        user_id: str,
        history: list[dict[str, str]],
        llm_helper=None,
    ) -> str:
        """更新用户画像

        当对话历史达到阈值时，调用LLM生成画像。

        参数:
            user_id: 用户ID
            history: 对话历史
            llm_helper: LLM助手，None时延迟导入

        返回:
            str: 生成的画像描述
        """
        if len(history) < 10:
            return await self.get_user_persona(user_id)

        if llm_helper is None:
            llm_helper = _default_llm_helper

        history_text = "\n".join(
            f"{msg.get('role', 'user')}: {msg.get('content', '')}"
            for msg in history[-20:]
        )
        prompt = _PERSONA_UPDATE_PROMPT.format(history=history_text)

        try:
            persona = await llm_helper.chat_text(
                [{"role": "user", "content": prompt}],
                options={"temperature": 0.4},
            )
            await UserPersonaProfile.update_persona(user_id, persona)
            logger.debug(
                f"更新用户画像: {user_id}",
                command="AI",
            )
            return persona
        except Exception as e:
            logger.warning(
                f"更新用户画像失败: {e}", command="AI", e=e
            )
            return await self.get_user_persona(user_id)

    async def apply_user_correction(
        self, user_id: str, correction: str
    ) -> UserPersonaProfile:
        """应用用户/管理员更正画像

        参数:
            user_id: 用户ID
            correction: 更正内容

        返回:
            UserPersonaProfile: 更新后的画像
        """
        profile, _ = await UserPersonaProfile.get_or_create(user_id=user_id)
        profile.user_correction = correction
        profile.updated_at = datetime.now()
        await profile.save(update_fields=["user_correction", "updated_at"])
        return profile

    def get_persona_tts_config(self, persona: dict) -> dict:
        """从人格提取TTS配置

        参数:
            persona: 人格配置

        返回:
            dict: TTS配置（voice/model等）
        """
        return {
            "voice": persona.get("tts_voice", "alloy"),
            "mood": persona.get("sticker_mood", "neutral"),
        }

    def get_persona_sticker_mood(self, persona: dict) -> str:
        """获取人格贴纸情绪倾向

        参数:
            persona: 人格配置

        返回:
            str: 贴纸情绪（warm/cool/neutral）
        """
        return persona.get("sticker_mood", "neutral")


persona_manager = PersonaManager()
"""人格管理器单例"""
