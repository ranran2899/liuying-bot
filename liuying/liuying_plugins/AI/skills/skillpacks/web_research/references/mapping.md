函数映射

- `impl.research(question, queries, llm_helper)` -> `run(question, queries)`
- `impl.build_research_tool(runtime)` -> `build_tools(runtime)`
- `impl.merge_results(batches)` 归并去重
- `impl._interleave(batches)` 轮次交错展平
- `impl._dedup_key(item)` 去重键计算
- `impl._normalize_url(url)` URL 归一化
- `impl.format_material(items)` 材料格式化

暴露工具名：`deep_research`（每会话配额 2 次）
