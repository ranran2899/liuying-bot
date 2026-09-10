# 流萤 AI 插件系统性代码质量评估报告

- 审查范围：`liuying/liuying_plugins/AI/`（约 110 个 Python 文件，15000+ 行）
- 审查方法：4 路并行深度审查（agent / core / pipeline+handlers+jobs / skills+models+config）
- 审查日期：2026-09-10

## 执行摘要

整体工程质量高于社区平均水平：分层清晰（agent 规划-执行-响应三层、core 按域划分、pipeline 按回复生命周期拆分）、文档字符串与类型标注覆盖率近乎 100%、match-case / `X | None` / `dataclass(slots=True)` 等新语法使用到位、管理命令权限校验完备、ORM 值全量参数绑定（无 SQL 注入）。

但存在系统性短板：
1. **7 个影响正确性/可用性的严重缺陷**（含 1 个配置即崩溃 bug、1 个历史窗口永不过期的数据 bug、1 个技能功能整体死亡）
2. **7 个安全风险**（SSRF 防护缺失、技能包路径穿越、计算资源滥用等）
3. **10+ 个热路径性能债**（事件循环阻塞、全表扫描、O(n²) 算法）
4. **大量配置型死代码与空壳转发**（约 500+ 行从未接线/无调用方）

两轮优化已完成约 80 项修复，详见第六、七节执行状态。个别审查建议在实施后按"避免过度实现"原则回退（见 S9 说明）。

## 一、严重缺陷（正确性/可用性）——已全部修复

| # | 位置 | 问题 | 状态 |
|---|------|------|------|
| 1 | `core/peer_awareness.py` | `_parsed_ids` 在 `__init__` 未初始化，配置 `PEER_BOT_IDS` 后首条群消息即 AttributeError | 已修复 |
| 2 | `models/conversation_record.py` | `get_history` 升序+limit 取"最早 N 条"，历史上下文永不前移 | 已修复（改倒序，调用方 reversed 语义对齐） |
| 3 | `skills/api.py` + `__init__.py` | `SkillRuntime` 缺 `memory_manager` 字段，user_profile 技能恒返回"未配置记忆管理器" | 已修复（新增字段并在主入口注入） |
| 4 | `agent/runtime/planner.py` | `metadata_fallback_turn_plan` 仅传 has_images，群聊防误插话兜底分支永不触发 | 已修复（plan/_plan_with_llm 传 is_group/is_at_bot，run_agent 与 reply_generator 接线） |
| 5 | `agent/runner.py` | `_inject_guidance_to_messages` 原地修改 messages，指导文本可重复累积 | 已修复（幂等标记防重注入） |
| 6 | `pipeline/response_review.py` + `jobs/group_style_autobuild.py` | 模板 `{{`/`}}` 非 f-string 转义，JSON 示例输出双大括号误导 LLM | 已修复 |
| 7 | `core/tasks_service.py` | `json.loads` 位于 try 外，params_json 损坏炸穿调度回调 | 已修复（容错降级到 description） |
| 8 | `agent/runtime/responder.py` | `float(data.get(...))` 未容错，LLM 输出 "high" 字符串即降级为固定文案 | 已修复（_safe_ambiguity 枚举映射） |
| 9 | `agent/runner.py` | `msg.get("content")[:100]` 对多模态 list 切片污染规划器输入 | 已修复（提取文本段） |

## 二、安全风险——两轮修复状态

| # | 位置 | 风险 | 状态 |
|---|------|------|------|
| S1 | `core/tools/web_fetch.py` | SSRF：未拦内网/环回/云元数据地址 | 已修复（DNS 解析后私网段校验，含 rebinding 局限说明） |
| S2 | `skills/loader.py` | 技能包 entrypoint 路径穿越后被 exec_module 执行 | 已修复（resolve + is_relative_to 校验） |
| S3 | `skills/media.py` | image_url 工具参数无 SSRF 校验 | 已修复（scheme 白名单 + 私网拒绝） |
| S4 | `skills/skillpacks/calculator` | `pow(9, 3.8e8)`/`factorial(10**6)` 绕过算力限制 | 已修复（函数调用补指数/参数上限） |
| S5 | `skills/skillpacks/translate` | 异常全文回传聊天泄露内部信息 | 已修复（只回传异常类型名） |
| S6 | `handlers/chat_commands.py` | ACL 黑名单检查滞后于视觉 LLM 调用 | 已修复（前移至消息入口） |
| S7 | `agent/mcp_bridge.py` | args/tools 类型逐项校验缺失、JSON 配置即命令执行入口 | 已修复（第二轮：command/args/tools/env 类型校验，非法跳过并告警） |
| S8 | `core/llm/ai_routes.py` | CLI 降级无总预算、用户消息拼命令行参数 | 已修复（第二轮：45s 总预算 + 强制 stdin） |
| S9 | `agent/tools/builtin/plugin_invoker.py` | 曾加 30 前缀危险命令黑名单拦截 LLM 代发命令 | 已回退：下游 admin/超管插件的权限校验门槛高于 AI 插件，AI 代发的命令它们天然不会受理，黑名单为过度实现 |

## 三、性能瓶颈——两轮全部修复（15 项）

| # | 位置 | 问题 | 状态 |
|---|------|------|------|
| P1 | `core/memory/curator.py` | O(n²) 同步余弦阻塞事件循环 | 已修复（to_thread 卸载 + 模长预计算） |
| P2 | `core/knowledge_db/retriever.py` | 向量检索无 LIMIT 全表扫描+逐行 JSON 反序列化 | 已修复（第二轮：扫描上限 2000 + id 时间序 + user/persona 归属过滤） |
| P3 | `core/knowledge/store.py` | tokenize 正则每次调用重新编译 | 已修复（模块级预编译） |
| P4 | `pipeline/prompt_builder.py` | 四路独立 IO 串行 await | 已修复（gather 并行，记忆路保留降级） |
| P5 | `core/persona.py` | 手工 LRU while+min() O(n²) | 已修复（OrderedDict O(1)） |
| P6 | `core/vision/manager.py` | 完整 base64 作缓存 key | 已修复（sha256 哈希 key） |
| P7 | `core/context/thread_tracker.py` | 过期线程仅置标志从不删除，内存泄漏 | 已修复（清理时删除条目与空 group 键） |
| P8 | `core/memory/background_intelligence.py` | `text.split()` 中文去重失效 | 已修复（复用 _common.tokenize CJK 2-gram） |
| P9 | `jobs/*` | 全行 ORM 拉取仅需单列 | 已修复（values_list；proactive 空闲过滤下推数据库） |
| P10 | `models/knowledge_query_log.py` | 7 天全量行拉到 Python Counter | 已修复（ORM group_count 聚合下推） |
| P11 | `models/sticker_item.py` | mood_tags LIKE 子串误匹配 | 已修复（带引号精确匹配 JSON 元素） |
| P12 | `core/memory/recall.py` | 查询改写 LLM 位于每条消息热路径 | 已修复（第二轮：默认关闭 + config 声明同步） |
| P13 | `AI/config.py` | 热路径每次调用重读配置（含类型转换/模型构建） | 已修复（第二轮：5s TTL 缓存 + 浅拷贝 + set 失效） |
| P14 | `agent/mcp_bridge.py` | 每次工具调用重启 MCP 子进程（1-5s/次） | 已修复（第二轮：长连接池 + 失败重建重试） |
| P15 | `core/memory/evolves.py` | 单消息最多 5 次串行 LLM 关系判断 | 已修复（第二轮：批量 JSON 判断，失败降级回逐个） |
| P16 | `agent/runtime/planner.py` | 每轮重新渲染 24 工具元数据 | 已修复（第二轮：registry.revision 缓存） |
| P17 | `core/vision/capabilities.py` | 全 provider 串行探测 | 未修（探测仅在启动期执行，非热路径，暂缓） |

## 四、过度设计与死代码——两轮清理状态

| # | 位置 | 问题 | 状态 |
|---|------|------|------|
| D1 | `agent/skill_isolation.py` + `agent/isolated_runner.py` | 254 行全量死代码 | 已删除（第二轮） |
| D2 | `agent/query_rewriter.py` vs `core/knowledge_db/query_rewriter.py` | 双实现职责重叠，agent 版无缓存 | 保留（需业务确认 prompt 差异，暂缓） |
| D3 | `handlers/chat_helpers.py:29-68` | `_AIUserStateManager` 死状态管理 | 已删除（第二轮） |
| D4 | `pipeline/reply_buffer.py` | `clear()` 无调用方；`first_message_id` 仅 debug 用 | 已删除（第二轮） |
| D5 | `agent/tools/registry.py` | `to_openai_schemas` 无调用方 | 已删除（第二轮） |
| D6 | `tools/registry.py` | `per_session_quota` 死字段（7 skillpack 配置） | 已删除（第二轮，7 处联动清理） |
| D7 | `sticker/curation.py`、`pipeline/sticker.py` | 纯参数转发空壳 | 保留（部分转发有兼容价值，暂缓） |
| D8 | `runtime/intent_rules.py` | IntentRuleManager 空壳类 | 已降级为模块函数（第二轮，兼容类保留） |
| D9 | 5 处全静态类+伪单例 | `reply_turn_trace`/`search_ranker` 等 | 保留（低风险低收益，暂缓） |
| D10 | `core/runtime/switch.py` | 6 项功能无配置映射静默假持久化 | 已补 warning 告警（第二轮，不静默） |
| D11 | `agent/runtime/constants.py` | LATENCY_CLASS 曾疑死代码 | 审查确认为活代码（tool_catalog 消费），保留 |

## 五、职责混乱与架构问题——状态

| # | 问题 | 状态 |
|---|------|------|
| 1 | **双头消息所有权**：runner 注入 + responder 重建历史，口径不一致 | 保留（需 pipeline 联动重构） |
| 2 | **knowledge/ vs knowledge_db/** 命名误导 | 保留（物理移动破坏绝对导入，独立窗口执行） |
| 3 | **persona.py 四重职责** | 保留（拆分需回归测试） |
| 4 | **chat_helpers 名实脱节** | 部分缓解（第二轮已删死状态管理） |
| 5 | **memory 三套去重实现** | 保留（两套已对齐分词，策略漂移缓解） |
| 6 | **executor.py 九重职责** | 保留（拆分风险高，建议独立版本） |
| 7 | **provider_router + provider_health 双状态** | 保留（需 provider 回归） |
| 8 | **GroupContextSnapshot.style 双轨写入** | 已统一（第二轮：autobuild 改 profile 同构 JSON，删除兼容分支） |
| 9 | **register_mcp_tools 混入 jobs** | 已归位（第二轮：移至插件启动流程） |

## 六、第二轮优化执行明细（已实施）

**A1 MCP 桥接重构**：长连接池（存活检测复用、失败重建重试一次）、优雅退出（terminate→2s→kill）、close() 接入插件关闭钩子、JSON-RPC notification 容错、配置四段类型校验、handler 闭包解耦单例。

**A2 死代码删除**：D1/D3/D4/D5/D6/D8 全部落地（约 500+ 行）；draw 规则单字"画"改多字词（消除"动画好看"误触发）；reply_buffer 满 10 条静默丢弃补 warning；planner 工具元数据缓存。

**A3 core 记忆/知识优化**：P2/P12/P13/P15 落地；`manager.clear_all(clear_entries=False)` 保留业务表；memory/manager 后台任务 `Semaphore(4)` 限流；curator preferences 去重；active_learning 配额加锁+成功后递增；switch 假持久化告警。

**A4 models 层修复**：user_task/emotion_state 补唯一索引+去重 SQL；user_task 达上限抛 ValueError（原永久死锁）；create_task IntegrityError 重试取号；token_ledger get_summary 三扫合一；sticker_item 原子 update；sticker 情绪定义收敛 constants；library/importer 聚合与批删；semantics 真 LRU；members 真实 total；protocol 探测 60s TTL；prune_stale 批删。

**A5 handlers/jobs 修复**：任务创建三道防线（每用户≤10、消息≤500 截断、拒绝每分钟）；proactive Target 统一 + random.shuffle 消除群饥饿；social 超长文案截断发送；群风格 JSON 双轨统一；reply_generator 重试惰性化；tts 配置一次读取 + 300 字上限；executor 变体 `retries=0`。

**A6 安全杂项**：CLI 45s 预算 + 强制 stdin；peer_awareness 移除"酱"误伤 + ASCII 词边界正则；chat_intent "早"精确匹配（正则 12 / 问候 8 用例行为自验通过）。原 plugin_invoker 危险命令黑名单按"避免过度实现"回退删除——下游插件权限校验已天然拦截，AI 代发命令不会越权。

## 七、已修复但需运维关注

- `get_history` 语义修正后，对话历史将真正滚动到最近记录——预期行为修复
- ACL 前移后黑名单用户消息在入口即被拦截，视觉 LLM 消耗归零——预期降本
- `user_profile` 技能恢复可用
- **MCP 改长连接**：子进程常驻；重启插件由 close() 统一释放
- **检索查询改写默认关闭**：新部署省掉每条消息一次 LLM 延迟；老部署 yaml 已有该键仍为 True 需手动改
- **evolves 批量判断**：后台链路 LLM 次数降约 4/5；批量解析失败自动降级回逐个（行为兼容）
- **新增唯一索引**：历史脏数据（重复 task_no/emotion 行）首次启动由去重 SQL 自动清理
- **CLI 降级改 stdin + 45s 预算**：命令行注入面消除

## 验证结果

- `uv run ruff check liuying/liuying_plugins/AI/`：**All checks passed**（0 报错）
- 195 个 Python 文件 `ast.parse` 语法校验：**全部通过**（较首轮少 2 个 = 已删除死代码文件）
- 全项目 ruff 失败项均位于未触碰的其他模块（platform/web_ui/KeyValue 等历史遗留）
- 两轮合计：新增报告 1 份 + 修改约 55 个 AI 插件文件 + 删除 2 个死代码文件；未引入任何新依赖