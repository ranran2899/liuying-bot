ACG 检索技能实现说明

- 生产入口：`scripts/main.py` 的 `build_tools(runtime)`
- 调试入口：`scripts/main.py` 的 `run(name, kind)`
- 核心实现：`scripts/impl.py`

设计要点：

- 不接入 Bangumi 等专用 API，避免为单技能引入密钥与配额管理
- 精度提升来自关键词工程：`_KIND_KEYWORDS` 按类型补充领域词
- `kind` 用 JSON Schema 的 `enum` 约束，减少模型传错值

扩展类型：往 `_KIND_KEYWORDS` 加一项即可，enum 会自动同步。
