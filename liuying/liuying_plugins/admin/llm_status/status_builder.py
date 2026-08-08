"""LLM 状态数据构建与图片生成模块"""

from datetime import datetime
import json

from liuying.models._llm import TokenUsage
from liuying.services.LLM import llm_manager
from liuying.services.LLM.tracker import token_tracker
from liuying.services.LLM.web_search.tracker import search_tracker
from liuying.ui.services import render

BAIDU_MODE_LABELS = {
    "web_search": "百度搜索",
    "chat": "智能搜索生成",
    "web_summary": "智能搜索生成(高性能版)",
}


def capability_names(provider_name: str) -> list[str]:
    """获取供应商支持的能力名称列表

    参数:
        provider_name: 供应商名称

    返回:
        能力名称列表
    """
    if not (provider := llm_manager.get_provider(provider_name)):
        return []
    return sorted(c.value for c in provider.capabilities())


def build_providers() -> list[dict]:
    """构建供应商配置数据

    返回:
        供应商信息列表
    """
    return [
        {
            "name": cfg.name,
            "apiType": cfg.api_type,
            "models": [m.model_name for m in cfg.models if m.model_name],
            "capabilities": capability_names(cfg.name),
        }
        for cfg in llm_manager.get_all_providers()
    ]


def _usage_rows(summary: dict[str, dict]) -> list[dict]:
    """把 Token 统计字典转换为展示行

    参数:
        summary: 以名称为键的统计字典

    返回:
        展示行列表，按总计倒序
    """
    rows = [
        {
            "name": name,
            "prompt": record["prompt_tokens"],
            "completion": record["completion_tokens"],
            "total": record["total_tokens"],
        }
        for name, record in summary.items()
    ]
    return sorted(rows, key=lambda row: row["total"], reverse=True)


async def build_token_data() -> dict:
    """构建 Token 消耗统计数据

    返回:
        Token 统计数据字典
    """
    provider_summary = await token_tracker.get_provider_summary()
    model_summary = await token_tracker.get_model_summary()
    daily_total = await token_tracker.get_total()
    weekly = await TokenUsage.get_range_summary(7)
    all_time = await TokenUsage.get_total_summary()

    weekly_rows = [
        {
            "date": key,
            "total": record["total_tokens"],
            "count": record["request_count"],
        }
        for key, record in sorted(weekly.items())
    ]

    return {
        "hasData": bool(model_summary or all_time["total_tokens"]),
        "providers": _usage_rows(provider_summary),
        "models": _usage_rows(model_summary),
        "daily": {
            "prompt": daily_total["prompt_tokens"],
            "completion": daily_total["completion_tokens"],
            "total": daily_total["total_tokens"],
        },
        "allTime": {
            "prompt": all_time["prompt_tokens"],
            "completion": all_time["completion_tokens"],
            "total": all_time["total_tokens"],
            "requestCount": all_time["request_count"],
        },
        "weekly": weekly_rows if all_time["total_tokens"] else [],
    }


async def build_search_data() -> dict:
    """构建网络搜索使用统计数据

    返回:
        搜索统计数据字典
    """
    provider_summary = await search_tracker.get_provider_summary()
    mode_summary = await search_tracker.get_baidu_mode_summary()
    quota = await search_tracker.get_baidu_quota()
    total = await search_tracker.get_total()

    providers = sorted(
        (
            {
                "name": name,
                "count": record["count"],
                "lastUsed": record["last_used"],
            }
            for name, record in provider_summary.items()
        ),
        key=lambda row: row["count"],
        reverse=True,
    )

    modes = [
        {"label": BAIDU_MODE_LABELS.get(mode, mode), "count": record["count"]}
        for mode, record in sorted(mode_summary.items())
    ]

    quota_data = None
    if (daily_limit := quota["daily_limit"]) > 0:
        quota_data = {
            "used": quota["used"],
            "remaining": quota["remaining"],
            "dailyLimit": daily_limit,
            "percent": min(100, int(quota["used"] / daily_limit * 100)),
        }

    return {
        "providers": providers,
        "modes": modes,
        "quota": quota_data,
        "total": total["count"],
    }


async def build_status_data() -> dict:
    """构建 LLM 状态完整数据

    返回:
        用于模板渲染的数据字典
    """
    providers = build_providers()
    return {
        "defaultModel": llm_manager.config.default_model_name or "未配置",
        "providerCount": len(providers),
        "providers": providers,
        "token": await build_token_data(),
        "search": await build_search_data(),
    }


async def gen_status_img(user_id: str | None = None) -> bytes:
    """生成 LLM 状态图片

    参数:
        user_id: 用户ID，用于选择用户主题

    返回:
        图片字节数据
    """
    data = await build_status_data()
    weekly = data["token"]["weekly"]
    data["chartLabels"] = json.dumps([row["date"] for row in weekly])
    data["chartTotals"] = json.dumps([row["total"] for row in weekly])
    data["currentTime"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return await render(
        "pages/builtin/llm_status",
        data=data,
        user_id=user_id,
        wait=1,
    )
