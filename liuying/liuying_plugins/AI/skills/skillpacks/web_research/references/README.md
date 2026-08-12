深度检索技能实现说明

- 生产入口：`scripts/main.py` 的 `build_tools(runtime)`
- 调试入口：`scripts/main.py` 的 `run(question, queries)`
- 核心实现：`scripts/impl.py`

关键设计：

- `asyncio.gather` 并发子查询，`asyncio.timeout` 统一兜底总耗时
- `_search_one` 内部吞掉单路异常，实现部分失败可用
- `_interleave` 轮次交错展平，`_dedup_key` 归一化去重
- 汇总失败时退化为直接返回材料，工具永不返回空结果

三级降级链：完整汇总 → 原始材料 → 明确的不可用提示。

调参入口都在 `impl.py` 顶部常量：并发数、每路条数、归并上限、
摘要截断长度、总超时。
