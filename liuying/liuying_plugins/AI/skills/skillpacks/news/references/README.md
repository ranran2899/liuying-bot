新闻技能实现说明

- 生产入口：`scripts/main.py` 的 `build_tools(runtime)`
- 调试入口：`scripts/main.py` 的 `run(category)`
- 核心实现：`scripts/impl.py`

分类到检索关键词的映射维护在 `impl.py` 内的常量表，
新增分类只需扩展该表，无需修改工具 schema 以外的逻辑。
