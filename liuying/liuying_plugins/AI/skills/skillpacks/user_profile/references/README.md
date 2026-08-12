用户画像技能实现说明

- 生产入口：`scripts/main.py` 的 `build_tools(runtime)`（返回 2 个工具）
- 调试入口：`scripts/main.py` 的 `run(fact)`
- 核心实现：`scripts/impl.py`

依赖：

- `runtime.memory_manager` 的 `add` 与 `get_memory_summary`
- `agent/runtime/session_context` 的当前用户、群组、人格

为什么不把 user_id 做成工具参数：
模型可被诱导传入任意 user_id，从而读写他人记忆。
改为从 ContextVar 取当前会话身份后，越权在结构上不可能发生。

记忆写入本身走 `memory_manager.add`，内部已包含索引与进化逻辑，
本技能不重复实现，也不吞掉其异常。
