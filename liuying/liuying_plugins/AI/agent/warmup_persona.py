"""人格管理

加载YAML人格配置文件，构建系统提示词，管理用户画像。
支持用户级人格切换：每个用户可独立选择当前bot人格，
人格间对话历史与记忆完全隔离。
"""

from collections import OrderedDict
import json
from pathlib import Path
import time

from ruamel.yaml import YAML

from liuying.services.cache import CacheDict
from liuying.utils.log import logger
from liuying.utils.user.favor import UserFavor

from ..config import get_config, set_config
from ..core.llm import llm_helper as _default_llm_helper
from ..core.llm.model_router import ROLE_WARMUP, model_router
from ..models.user_persona import UserPersonaProfile
from ..models.user_persona_selection import UserPersonaSelection

_PERSONAS_DIR = Path(__file__).parent.parent / "personas"
"""人格配置文件目录"""

FAVOR_ATTITUDES: dict[str, str] = {
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


def extract_persona_desc(persona: dict) -> str:
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
        # 用户激活人格名短TTL缓存：单次消息链路内
        # get_user_persona_name 会被反复调用（processor/prompt_builder/
        # decisions 各取一次），缓存避免每条消息多次查库。
        # OrderedDict 维护访问顺序，命中 move_to_end、淘汰
        # popitem(last=False)，实现 O(1) LRU
        self._name_cache: OrderedDict[str, tuple[float, str]] = (
            OrderedDict()
        )
        self._name_cache_ttl = 60.0
        self._name_cache_max = 512
        """缓存条目上限，超出时先清过期项再淘汰最旧项"""

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
        now = time.monotonic()
        cached = self._name_cache.get(user_id)
        if cached is not None and now - cached[0] < self._name_cache_ttl:
            # 命中后移到末尾，维持 LRU 访问顺序
            self._name_cache.move_to_end(user_id)
            return cached[1]
        name = await UserPersonaSelection.get_persona_name(user_id)
        resolved = (
            name
            if name and self._persona_exists(name)
            else self.get_active_persona_name()
        )
        self._prune_name_cache(now)
        self._name_cache[user_id] = (now, resolved)
        return resolved

    def _prune_name_cache(self, now: float) -> None:
        """控制人格名缓存容量

        条目达到上限时先清除已过期项，仍超限则按
        访问顺序淘汰最旧条目（OrderedDict 首项即最久
        未访问项，popitem O(1)），防止长期运行无限增长。

        参数:
            now: 当前单调时钟时间戳
        """
        if len(self._name_cache) < self._name_cache_max:
            return
        expired = [
            uid
            for uid, (ts, _) in self._name_cache.items()
            if now - ts >= self._name_cache_ttl
        ]
        for uid in expired:
            del self._name_cache[uid]
        while len(self._name_cache) >= self._name_cache_max:
            self._name_cache.popitem(last=False)

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
        self._name_cache.pop(user_id, None)
        await UserPersonaSelection.set_persona_name(user_id, name)
        logger.info(
            f"用户 {user_id} 切换人格: {name}",
            command="AI",
        )

    def _persona_exists(self, name: str) -> bool:
        """检查人格是否存在

        通过YAML配置文件是否存在判断人格是否有效。

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
            dict: 人格配置字典

        异常:
            FileNotFoundError: 人格文件不存在
        """
        return self.load_persona(name)

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
        try:
            return await self.get_persona_by_name(active_name)
        except FileNotFoundError:
            # 用户选择的人格文件缺失时回退全局默认，
            # 避免单个人格文件丢失阻断整条回复链路
            logger.warning(
                f"人格 {active_name} 文件缺失，回退默认人格",
                command="AI",
            )
            return self.get_default_persona()

    def get_default_persona(self) -> dict:
        """获取全局默认人格配置（同步）

        读取 DEFAULT_PERSONA 配置，加载对应人格文件。
        供需要同步获取人格的场景使用（如TTS配置提取）。

        返回:
            dict: 人格配置字典

        异常:
            FileNotFoundError: 人格文件不存在
        """
        return self.load_persona(self.get_active_persona_name())

    def list_personas(self) -> list[str]:
        """列出所有可用人格名

        扫描personas目录下的YAML文件，文件名（不含扩展名）即人格名。

        返回:
            list[str]: 人格名称列表
        """
        if not self.personas_dir.exists():
            return []
        names = [
            f.stem
            for f in self.personas_dir.glob("*.yaml")
            if f.is_file()
        ]
        return sorted(names)

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
                        "description": extract_persona_desc(persona),
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
        attitude = FAVOR_ATTITUDES.get(favor_level, "")
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
    ) -> str:
        """更新用户画像

        当对话历史达到阈值时，调用LLM生成画像。

        参数:
            user_id: 用户ID
            history: 对话历史

        返回:
            str: 生成的画像描述
        """
        if len(history) < 10:
            return await self.get_user_persona(user_id)

        history_text = "\n".join(
            f"{msg.get('role', 'user')}: {msg.get('content', '')}"
            for msg in history[-20:]
        )
        prompt = (
            "请根据以下用户与AI的对话历史，生成一份用户画像。\n\n"
            f"对话历史：\n{history_text}\n\n"
            "请用简洁的语言描述这个用户的特征，包括：\n"
            "- 性格特点\n"
            "- 兴趣爱好\n"
            "- 交流风格\n"
            "- 特别偏好\n\n"
            "只返回画像描述文本，不要其他内容。画像应不超过200字。"
        )

        try:
            role = model_router.resolve(ROLE_WARMUP)
            persona = await _default_llm_helper.chat_text(
                [{"role": "user", "content": prompt}],
                model=role.model or None,
                options=role.apply_to_options({"temperature": 0.4}),
                provider_name=role.provider or None,
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
