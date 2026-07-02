"""画像服务层

统一画像服务，整合用户画像与人格管理，
提供读取/更新画像的统一入口，避免上层直接操作数据模型。
"""

from datetime import datetime
import json

from liuying.utils.log import logger

from ...models.user_persona import UserPersonaProfile


class ProfileService:
    """画像服务

    统一封装用户画像的读取与更新，整合人格管理信息，
    上层模块仅需通过本服务访问画像数据。
    """

    def __init__(self) -> None:
        """初始化画像服务"""
        self._cache: dict[str, dict] = {}
        """内存画像缓存（user_id -> 画像字典）"""

    async def get_profile(self, user_id: str) -> dict:
        """获取用户画像

        参数:
            user_id: 用户ID

        返回:
            dict: 画像字典，含 persona/structured/user_correction/updated_at
        """
        if user_id in self._cache:
            return dict(self._cache[user_id])
        profile = await UserPersonaProfile.filter(
            user_id=user_id
        ).first()
        if not profile:
            result: dict = {
                "user_id": user_id,
                "persona": "",
                "structured": {},
                "user_correction": "",
                "updated_at": "",
            }
            return result
        try:
            structured = json.loads(profile.structured_json or "{}")
        except (json.JSONDecodeError, TypeError):
            structured = {}
        updated = (
            profile.updated_at.strftime("%Y-%m-%d %H:%M")
            if profile.updated_at
            else ""
        )
        result = {
            "user_id": profile.user_id,
            "persona": profile.persona or "",
            "structured": structured,
            "user_correction": profile.user_correction or "",
            "updated_at": updated,
        }
        self._cache[user_id] = dict(result)
        return result

    async def update_profile(
        self, user_id: str, data: dict
    ) -> None:
        """更新用户画像

        参数:
            user_id: 用户ID
            data: 画像数据，支持 persona/structured/user_correction 键
        """
        profile, _ = await UserPersonaProfile.get_or_create(
            user_id=user_id
        )
        if "persona" in data:
            profile.persona = str(data["persona"] or "")
        if "structured" in data:
            structured = data["structured"]
            if isinstance(structured, dict):
                profile.structured_json = json.dumps(
                    structured, ensure_ascii=False
                )
            elif isinstance(structured, str):
                profile.structured_json = structured
        if "user_correction" in data:
            profile.user_correction = (
                str(data["user_correction"]) if data["user_correction"] else None
            )
        profile.updated_at = datetime.now()
        await profile.save(
            update_fields=[
                "persona",
                "structured_json",
                "user_correction",
                "updated_at",
            ]
        )
        self._cache.pop(user_id, None)
        logger.debug(
            f"更新用户画像: {user_id}", command="AI"
        )

    def invalidate(self, user_id: str) -> None:
        """清除指定用户的画像缓存

        参数:
            user_id: 用户ID
        """
        self._cache.pop(user_id, None)

    def clear_cache(self) -> None:
        """清空全部画像缓存"""
        self._cache.clear()


profile_service = ProfileService()
"""画像服务单例"""
