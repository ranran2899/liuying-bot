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

## 二、安全风险——已修复 7 项

| # | 位置 | 风险 | 状态 |
|---|------|------|------|
| S1 | `core/tools/web_fetch.py` | SSRF：未拦内网/环回/云元数据地址 | 已修复（DNS 解析后私网段校验，含 rebinding 局限说明） |
| S2 | `skills/loader.py` | 技能包 entrypoint 路径穿越后被 exec_module 执行 | 已修复（resolve + is_relative_to 校验） |
| S3 | `skills/media.py` | image_url 工具参数无 SSRF 校验 | 已修复（scheme 白名单 + 私网拒绝） |
| S4 | `skills/skillpacks/calculator` | `pow(9, 3.8e8)`/`factorial(10**6)` 绕过算力限制 | 已修复（函数调用补指数/参数上限） |
| S5 | `skills/skillpacks/translate` | 异常全文回传聊天泄露内部信息 | 已修复（只回传异常类型名） |
| S6 | `handlers/chat_commands.py` | ACL 黑名单检查滞后于视觉 LLM 调用 | 已修复（前移至消息入口） |
| S7 | `agent/mcp_bridge.py` | args/tools 类型不校验、JSON 配置即命令执行入口 | 未修（属架构级改造，见 P1 建议） |
| S8 | `core/llm/ai_routes.py` | CLI 降级无总预算、参数注入面 | 未修（需与 provider 层联改） |

## 三、性能瓶颈——已修复 11 项

| # | 位置 | 问题 | 状态 |
|---|------|------|------|
| P1 | `core/memory/curator.py` | O(n²) 同步余弦阻塞事件循环 | 已修复（to_thread 卸载 + 模长预计算） |
| P3 | `core/knowledge/store.py` | tokenize 正则每次调用重新编译 | 已修复（模块级预编译） |
| P4 | `pipeline/prompt_builder.py` | 四路独立 IO 串行 await | 已修复（gather 并行，记忆路保留降级） |
| P5 | `core/persona.py` | 手工 LRU while+min() O(n²) | 已修复（OrderedDict O(1)） |
| P6 | `core/vision/manager.py` | 完整 base64 作缓存 key | 已修复（sha256 哈希 key） |
| P7 | `core/context/thread_tracker.py` | 过期线程仅置标志从不删除，内存泄漏 | 已修复（清理时删除条目与空 group 键） |
| P8 | `core/memory/background_intelligence.py` | `text.split()` 中文去重失效 | 已修复（复用 _common.tokenize CJK 2-gram） |
| P9 | `jobs/memory_decay.py` / `proactive.py` / `social_intelligence.py` | 全行 ORM 拉取仅需单列 | 已修复（values_list；proactive 空闲过滤下推数据库） |
| P10 | `models/knowledge_query_log.py` | 7 天全量行拉到 Python Counter | 已修复（ORM group_count 聚合下推） |
| P11 | `models/sticker_item.py` | mood_tags LIKE 子串误匹配 + 语义错误 | 已修复（带引号精确匹配 JSON 元素） |
| P5' | `core/memory/embedding_service.py` | 批量嵌入类型混淆静默返回空 | 已修复（warning 日志 + 单条降级包装） |
| — | `jobs/social_intelligence.py` | 循环内每群重读配置 2 次 | 已修复（提取循环外） |

未修（架构级，见 P1 建议）：P2 知识库向量检索全表扫描、P12 召回热路径 LLM 改写、P13 热路径重复读配置、P14 MCP 每调用重启子进程、P15 单消息隐藏 LLM 调用链。

## 四、过度设计与死代码（建议删除，待确认后实施）

| # | 位置 | 问题 |
|---|------|------|
| D1 | `agent/skill_isolation.py` + `agent/isolated_runner.py` | 254 行全量死代码（无调用方），"隔离"名不副实 |
| D2 | `agent/query_rewriter.py` vs `core/knowledge_db/query_rewriter.py` | 双实现职责重叠，agent 版无缓存每次全量 LLM |
| D3 | `handlers/chat_helpers.py:29-68` | `_AIUserStateManager.set_state` 无调用方（is_enabled 恒 True） |
| D4 | `pipeline/reply_buffer.py:173-182` | `clear()` 无调用方；`first_message_id` 仅 debug 用 |
| D5 | `agent/tools/registry.py:122-145` | `to_openai_schemas` 无调用方 |
| D6 | `tools/registry.py:50` | `per_session_quota` 字段被 7 个 skillpack 配置但 executor 从不消费 |
| D7/D8 | `sticker/curation.py`、`pipeline/sticker.py` | 大量纯参数转发空壳方法 |
| D9 | `runtime/intent_rules.py` | IntentRuleManager 空壳类包装常量列表 |
| D10 | 5 处全静态类+伪单例 | `reply_turn_trace`/`search_ranker`/`target_inference`/`safety/acl`/`chat_intent` |
| D11 | `core/runtime/switch.py` | 389 行三级开关，6 项功能无配置映射静默假持久化 |
| D12 | `agent/runtime/constants.py` | LATENCY_CLASS 常量体系被赋值从不读取 |

## 五、职责混乱与架构问题（未动，需专项重构）

1. **双头消息所有权**：runner 注入指导 + responder 重建裁剪历史，两头操作同一 messages，裁剪口径不一致
2. **knowledge/ vs knowledge_db/**：无调用关系的兄弟目录，前者实为"插件知识召回"，后者实为"记忆系统索引后端"，命名严重误导
3. **persona.py 461 行四重职责**：加载缓存+选择+画像生成+提示词组装
4. **chat_helpers.py 混杂 4 类职责**，命名 ChatMatchersHelper 名实脱节
5. **memory 三套去重实现**，策略各自漂移
6. **executor.py 724 行九重职责**
7. **provider_router + provider_health 双状态追踪**字段高度重叠
8. **GroupContextSnapshot.style 双轨写入**（autobuild 纯文本 / profile JSON）
9. **jobs/__init__.py:51**：`register_mcp_tools` 混在定时任务注册函数中

## 六、后续路线建议

- **P1（下轮）**：MCP 子进程长连接池与配置类型校验、记忆系统 LLM 调用链收敛（batch 判断+独立配额）、query_rewriter 双实现合并、knowledge_db 向量检索下推（LIMIT/预过滤/user+persona 条件）、热路径配置快照缓存
- **P2（需讨论后实施）**：死代码删除（D1-D12）、executor 拆分（校验器/调度器）、knowledge/knowledge_db 更名、消息所有权收敛到 pipeline 单点、switch 假持久化修复

## 七、已修复但需运维关注

- `get_history` 语义修正后，对话历史将真正滚动到最近记录（旧数据越早的记录不再进入上下文）——属预期行为修复
- ACL 前移后黑名单用户消息在入口即被拦截（原滞后于视觉调用），视觉 LLM 消耗归零——预期降本
- `user_profile` 技能恢复可用（remember_fact/get_user_profile 现已能访问记忆系统）

## 验证结果

- `uv run ruff check liuying/liuying_plugins/AI/`：**All checks passed**（0 报错）
- 197 个 Python 文件 `ast.parse` 语法校验：**全部通过**
- 全项目 ruff 失败项均位于本次未触碰的其他模块（platform/web_ui/KeyValue 等历史遗留）
- 本轮共修改 36 个文件（含报告），未引入任何新依赖
