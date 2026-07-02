"""LLM 状态文本构建模块"""
from liuying.models._llm import TokenUsage
from liuying.utils.LLM import llm_manager
from liuying.utils.LLM.tracker import token_tracker
from liuying.utils.LLM.web_search.tracker import search_tracker


def capability_names(provider_name: str) -> str:
    """获取供应商支持的能力名称列表

    参数:
        provider_name: 供应商名称

    返回:
        逗号分隔的能力名称
    """
    if not (provider := llm_manager.get_provider(provider_name)):
        return "-"
    return ", ".join(sorted(c.value for c in provider.capabilities()))


async def build_status_text() -> str:
    """构建 LLM 状态文本

    返回:
        状态文本
    """
    config = llm_manager.config
    providers = llm_manager.get_all_providers()

    lines = [
        "【LLM 状态】",
        f"默认模型: {config.default_model_name or '未配置'}",
        "",
    ]

    if not providers:
        lines.append("尚未配置任何供应商。")
        return "\n".join(lines)

    lines.append(f"已配置供应商 ({len(providers)}):")
    for provider_cfg in providers:
        models = [m.model_name for m in provider_cfg.models if m.model_name]
        lines.append(f"- {provider_cfg.name} [{provider_cfg.api_type}]")
        lines.append(f"  模型: {', '.join(models) if models else '-'}")
        lines.append(f"  能力: {capability_names(provider_cfg.name)}")

    await append_token_usage(lines)
    await append_search_usage(lines)

    return "\n".join(lines)


async def append_token_usage(lines: list[str]) -> None:
    """追加 Token 消耗统计到状态文本

    参数:
        lines: 状态文本行列表，原地追加
    """
    try:
        provider_summary = await token_tracker.get_provider_summary()
        model_summary = await token_tracker.get_model_summary()
        daily_total = await token_tracker.get_total()
        weekly = await TokenUsage.get_range_summary(7)
        all_time = await TokenUsage.get_total_summary()
    except Exception:
        # 数据库未就绪时静默跳过
        return

    lines.append("")
    lines.append("Token 消耗统计:")

    if not model_summary and not all_time["total_tokens"]:
        lines.append("暂无统计记录。")
        return

    if provider_summary:
        lines.append("今日按供应商:")
        for provider_name, record in sorted(provider_summary.items()):
            lines.append(
                f"- {provider_name}: "
                f"提示 {record['prompt_tokens']} | "
                f"补全 {record['completion_tokens']} | "
                f"总计 {record['total_tokens']}"
            )

    if model_summary:
        lines.append("今日按模型:")
        for model_name, record in sorted(model_summary.items()):
            lines.append(
                f"- {model_name}: "
                f"提示 {record['prompt_tokens']} | "
                f"补全 {record['completion_tokens']} | "
                f"总计 {record['total_tokens']}"
            )

    if daily_total["total_tokens"]:
        lines.append(
            f"今日合计: 提示 {daily_total['prompt_tokens']} | "
            f"补全 {daily_total['completion_tokens']} | "
            f"总计 {daily_total['total_tokens']}"
        )

    if weekly and all_time["total_tokens"]:
        lines.append("近7天:")
        for key, record in sorted(weekly.items()):
            lines.append(
                f"- {key}: "
                f"总计 {record['total_tokens']} | "
                f"请求 {record['request_count']} 次"
            )

    if all_time["total_tokens"]:
        lines.append(
            f"累计: 提示 {all_time['prompt_tokens']} | "
            f"补全 {all_time['completion_tokens']} | "
            f"总计 {all_time['total_tokens']} | "
            f"请求 {all_time['request_count']} 次"
        )


async def append_search_usage(lines: list[str]) -> None:
    """追加网络搜索使用次数统计到状态文本

    参数:
        lines: 状态文本行列表，原地追加
    """
    provider_summary = await search_tracker.get_provider_summary()
    baidu_mode_summary = await search_tracker.get_baidu_mode_summary()
    baidu_quota = await search_tracker.get_baidu_quota()
    search_total = await search_tracker.get_total()

    lines.append("")
    lines.append("网络搜索使用统计:")
    if not provider_summary:
        lines.append("暂无统计记录。")
        return

    lines.append("按引擎:")
    for provider_name, record in sorted(provider_summary.items()):
        lines.append(
            f"- {provider_name}: 调用 {record['count']} 次"
            + (f" (最近: {record['last_used']})" if record["last_used"] else "")
        )

    if baidu_mode_summary:
        lines.append("百度搜索模式:")
        mode_labels = {
            "web_search": "百度搜索",
            "chat": "智能搜索生成",
            "web_summary": "智能搜索生成(高性能版)",
        }
        for mode, record in sorted(baidu_mode_summary.items()):
            label = mode_labels.get(mode, mode)
            lines.append(f"- {label}: {record['count']} 次")

    daily_limit = baidu_quota["daily_limit"]
    if daily_limit > 0:
        remaining = baidu_quota["remaining"]
        used = baidu_quota["used"]
        lines.append(
            f"百度智能搜索生成配额: 已用 {used}/{daily_limit}，"
            f"剩余 {remaining} 次，次日零点重置"
        )
    else:
        lines.append(
            f"搜索总调用: {search_total['count']} 次"
        )
