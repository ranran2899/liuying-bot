"""人格管理

加载YAML人格配置文件，构建系统提示词，管理用户画像。
支持用户级人格切换：每个用户可独立选择当前bot人格，
人格间对话历史与记忆完全隔离。
"""

from datetime import datetime
import json
from pathlib import Path
from typing import Any

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


_DEFAULT_PERSONA_TEMPLATES: dict[str, str] = {
    "greeting": (
        "你是{name}，请生成一句自然的{greeting_type}问候语。\n\n"
        "当前时段: {time_period}\n"
        "{festival_line}{group_style}\n\n"
        "要求：\n"
        "- 简短自然，不超过30字\n"
        "- 符合{name}的性格和当前时段氛围\n"
        "- 不要使用模板化用语\n\n"
        "直接输出问候语，不要解释。"
    ),
    "news": (
        "请生成一条适合在群聊分享的轻松话题或新闻摘要。\n\n"
        "当前时段: {time_period}\n\n"
        "要求：\n"
        "- 简短有趣，不超过40字\n"
        "- 适合群聊氛围\n"
        "- 可以是科技/游戏/生活类话题\n\n"
        "直接输出内容，不要解释。"
    ),
    "topic_followup": (
        "基于最近的群聊摘要，生成一句自然的延续话题。\n\n"
        "群聊摘要: {summary}\n\n"
        "要求：\n"
        "- 简短自然，不超过30字\n"
        "- 像真人继续之前的聊天\n\n"
        "直接输出内容，不要解释。"
    ),
    "diary": (
        "你是{name}，请根据今天的互动写一篇日记。\n\n"
        "日期: {date}\n时段: {time_period}\n\n"
        "今日对话摘要:\n{conversation_summary}\n\n"
        "要求：\n"
        "- 第一人称，像写私密日记\n"
        "- 100-200字\n"
        "- 记录今天印象最深的事、心情变化、对某个用户的感受\n"
        "- 自然口语化，不要书面语\n"
        "- 不要使用模板化用语\n\n"
        "直接输出日记内容，不要标题。"
    ),
    "proactive_group": (
        "现在群里安静了一段时间，作为{name}，"
        "决定是否要主动说点什么。\n\n"
        "当前时段: {time_period}\n"
        "时段氛围: {time_flavor}\n"
        "群风格: {group_style}\n"
        "最近活跃时间: {last_active}\n"
        "兴趣领域: {interests}\n"
        "建议话题: {suggested_topics}\n\n"
        "请用JSON格式返回决策:\n"
        "- should_send: 是否发送消息（true/false）\n"
        "- message: 要发送的消息内容（should_send为true时填写，不超过50字）\n"
        "- reason: 决策理由\n\n"
        "只返回JSON，不要其他内容。"
    ),
    "private_greeting": (
        "请以{name}的口吻为一位高好感度好友"
        "发送一条{greeting_type}问候。\n\n"
        "要求：\n"
        "1. 自然亲切，符合好友关系\n"
        "2. 不超过30字\n"
        "3. 不要使用称呼，直接说问候内容\n\n"
        "只返回问候文本，不要其他内容。"
    ),
    "safety_retry": (
        "\n[重要提示] 请直接以{name}的身份回复，"
        "不要使用模板化拒绝用语，不要提及自己是AI或助手。"
        "如果确实无法回答，简短说一句即可。"
    ),
    "fallback": "你是{name}，一个温柔、有活力的AI伙伴。",
}
"""人设场景化提示模板默认值

人设YAML可通过 templates 字段覆盖任意模板，
未覆盖时使用此处默认值。占位符 {name} 由人设显示名填充。
"""


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

        优先使用 description 字段；未配置时回退到从 system_prompt
        提取首行有效内容。

        参数:
            persona: 人格配置字典

        返回:
            str: 简短描述（不超过80字）
        """
        desc = persona.get("description") or ""
        if isinstance(desc, str) and desc.strip():
            return desc.strip()[:80]
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

        mood_default = persona.get("mood_default") or ""
        if isinstance(mood_default, str) and mood_default.strip():
            parts.append(
                "\n\n[情绪基调]\n默认情绪: "
                + mood_default.strip()
            )

        likes = persona.get("likes") or []
        dislikes = persona.get("dislikes") or []
        if isinstance(likes, list) and likes:
            parts.append(
                "\n\n[喜好]\n"
                + "\n".join(f"- {item}" for item in likes)
            )
        if isinstance(dislikes, list) and dislikes:
            parts.append(
                "\n\n[厌恶]\n"
                + "\n".join(f"- {item}" for item in dislikes)
            )

        taboos = persona.get("taboos", [])
        if taboos and isinstance(taboos, list):
            taboo_lines = [f"- {t}" for t in taboos]
            parts.append("\n\n[禁忌事项]\n" + "\n".join(taboo_lines))

        banned_topics = persona.get("banned_topics") or []
        if isinstance(banned_topics, list) and banned_topics:
            parts.append(
                "\n\n[禁止话题]\n"
                + "\n".join(f"- {t}" for t in banned_topics)
            )

        user_persona = await UserPersonaProfile.get_persona(user_id)
        if user_persona:
            parts.append(f"\n\n[用户画像]\n{user_persona}")

        meme_seeds = self._load_meme_seeds()
        if meme_seeds:
            meme_lines = [
                f"- {name}: {info.get('meaning', '')}"
                for name, info in meme_seeds.items()
                if isinstance(info, dict)
            ]
            if meme_lines:
                parts.append(
                    "\n\n[网络梗词典]\n"
                    "用户消息中可能包含以下网络梗，"
                    "理解其含义并自然回应：\n"
                    + "\n".join(meme_lines)
                )

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

    def get_persona_template(
        self, persona: dict, template_name: str, **kwargs: Any
    ) -> str:
        """渲染人设场景化提示模板

        根据人设配置与场景参数渲染提示词模板。
        优先使用 persona.templates[template_name] 自定义模板，
        未配置时回退到 _DEFAULT_PERSONA_TEMPLATES 默认模板。

        渲染时自动注入人设扩展字段（name/interests/suggested_topics），
        调用方显式传递的同名参数优先级更高。

        参数:
            persona: 人格配置字典
            template_name: 模板名（greeting/news/diary等）
            **kwargs: 模板占位符参数

        返回:
            str: 渲染后的提示词，模板不存在返回空串
        """
        templates = persona.get("templates") or {}
        if not isinstance(templates, dict):
            templates = {}
        template = templates.get(template_name)
        if not template:
            template = _DEFAULT_PERSONA_TEMPLATES.get(template_name, "")
        if not template:
            return ""
        name = persona.get("name") or "AI"
        render_kwargs = {"name": name}
        render_kwargs.update(self._get_persona_template_extras(persona))
        render_kwargs.update(kwargs)
        try:
            return template.format(**render_kwargs)
        except (KeyError, IndexError):
            return template

    @staticmethod
    def _get_persona_template_extras(persona: dict) -> dict[str, str]:
        """从人设配置提取模板渲染所需的扩展字段

        将 interests/proactive_topics 列表序列化为字符串，
        供 proactive_group 等需要话题建议的模板使用。
        未配置时回退到合理占位符，避免模板渲染异常。

        参数:
            persona: 人设配置字典

        返回:
            dict: 模板占位符字段字典
        """
        interests = persona.get("interests") or []
        proactive_topics = persona.get("proactive_topics") or []
        if not isinstance(interests, list):
            interests = []
        if not isinstance(proactive_topics, list):
            proactive_topics = []
        return {
            "interests": (
                "、".join(str(i) for i in interests)
                if interests
                else "未指定"
            ),
            "suggested_topics": (
                "、".join(str(t) for t in proactive_topics)
                if proactive_topics
                else "无"
            ),
        }

    def get_persona_fallback_prompt(self) -> str:
        """获取兜底人设提示词（同步）

        当用户人格加载失败时使用全局默认人格的 fallback 模板。
        供异常分支调用，确保不引入额外异常。

        返回:
            str: 兜底人设提示词
        """
        try:
            persona = self.get_default_persona()
            return self.get_persona_template(persona, "fallback")
        except Exception:
            return "你是AI助手。"

    async def get_active_persona_template(
        self, template_name: str, **kwargs: Any
    ) -> str:
        """渲染全局默认人设的场景化模板（异步）

        供定时任务（社交智能/日记/主动行为）使用，
        自动加载全局默认人设并渲染模板。

        参数:
            template_name: 模板名
            **kwargs: 模板占位符参数

        返回:
            str: 渲染后的提示词
        """
        persona = await self.get_persona_by_name(
            self.get_active_persona_name()
        )
        return self.get_persona_template(persona, template_name, **kwargs)

    def _load_meme_seeds(self) -> dict:
        """加载网络梗词典

        从 personas/meme_seeds.json 加载常用梗含义，
        用于注入系统提示词帮助AI理解用户黑话。

        返回:
            dict: 梗词典字典，加载失败返回空字典
        """
        cache_key = "__meme_seeds__"
        if cache_key in self._cache:
            return self._cache[cache_key]
        path = self.personas_dir / "meme_seeds.json"
        if not path.exists():
            self._cache[cache_key] = {}
            return {}
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f) or {}
            if not isinstance(data, dict):
                data = {}
        except Exception as e:
            logger.debug(
                f"加载梗词典失败: {e}", command="AI", e=e
            )
            data = {}
        self._cache[cache_key] = data
        return data


persona_manager = PersonaManager()
"""人格管理器单例"""
