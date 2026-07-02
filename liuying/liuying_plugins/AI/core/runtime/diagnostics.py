"""主动诊断

主动预测与诊断系统潜在问题，输出健康检查报告。
受 PROACTIVE_DIAGNOSTICS_ENABLED 配置开关控制。
"""

from datetime import datetime

from liuying.utils.log import logger

from ...config import get_config


class Diagnostics:
    """主动诊断器

    提供整体诊断与轻量健康检查两类接口，
    供定时任务或WebUI调用。
    """

    async def diagnose(self) -> dict:
        """执行整体诊断

        返回:
            dict: 诊断报告，含 modules/config/timestamp
        """
        if not get_config("PROACTIVE_DIAGNOSTICS_ENABLED", False):
            return {
                "enabled": False,
                "message": "主动诊断未启用",
                "timestamp": datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
            }
        report: dict = {
            "enabled": True,
            "timestamp": datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            "modules": {},
            "issues": [],
        }
        report["modules"]["memory"] = self._check_memory()
        report["modules"]["llm"] = self._check_llm()
        report["modules"]["persona"] = self._check_persona()
        report["modules"]["safety"] = self._check_safety()
        flat_issues: list[str] = []
        for m in report["modules"].values():
            module_issues = m.get("issues", [])
            if module_issues:
                flat_issues.extend(module_issues)
        report["issues"] = flat_issues
        if flat_issues:
            logger.warning(
                f"诊断发现{len(flat_issues)}个问题",
                command="AI",
            )
        else:
            logger.info(
                "诊断完成，未发现问题",
                command="AI",
            )
        return report

    async def check_health(self) -> dict:
        """执行轻量健康检查

        返回:
            dict: 健康状态，含 status/ok/timestamp
        """
        ok = True
        checks: dict[str, bool] = {}
        if not get_config("ENABLE_AI", True):
            ok = False
            checks["ai_enabled"] = False
        else:
            checks["ai_enabled"] = True
        chat_provider = get_config("CHAT_PROVIDER", None)
        checks["chat_provider"] = bool(chat_provider)
        if not chat_provider:
            ok = False
        checks["memory_enabled"] = bool(
            get_config("MEMORY_ENABLED", True)
        )
        return {
            "ok": ok,
            "checks": checks,
            "timestamp": datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
        }

    def _check_memory(self) -> dict:
        """检查记忆模块配置

        返回:
            dict: 记忆模块检查结果
        """
        issues: list[str] = []
        if not get_config("MEMORY_ENABLED", True):
            issues.append("记忆系统未启用")
        top_k = get_config("MEMORY_RECALL_TOP_K", 5)
        if not isinstance(top_k, int) or top_k <= 0:
            issues.append("MEMORY_RECALL_TOP_K配置异常")
        return {
            "enabled": get_config("MEMORY_ENABLED", True),
            "issues": issues,
        }

    def _check_llm(self) -> dict:
        """检查LLM模块配置

        返回:
            dict: LLM模块检查结果
        """
        issues: list[str] = []
        if not get_config("CHAT_PROVIDER", None):
            issues.append("未配置CHAT_PROVIDER")
        strict = get_config("STRICT_MAIN_MODEL", False)
        lite = get_config("LITE_MODEL_ENABLED", False)
        if strict and lite:
            issues.append("严格主模型与轻量模型同时开启")
        return {
            "provider": get_config("CHAT_PROVIDER", None),
            "issues": issues,
        }

    def _check_persona(self) -> dict:
        """检查人格模块配置

        返回:
            dict: 人格模块检查结果
        """
        issues: list[str] = []
        name = get_config("DEFAULT_PERSONA", "liuying")
        if not name:
            issues.append("DEFAULT_PERSONA为空")
        return {
            "persona": name,
            "issues": issues,
        }

    def _check_safety(self) -> dict:
        """检查安全模块配置

        返回:
            dict: 安全模块检查结果
        """
        issues: list[str] = []
        if not get_config("SAFETY_FILTER_ENABLED", True):
            issues.append("安全过滤未启用")
        return {
            "filter_enabled": get_config(
                "SAFETY_FILTER_ENABLED", True
            ),
            "issues": issues,
        }


diagnostics = Diagnostics()
"""主动诊断器单例"""
