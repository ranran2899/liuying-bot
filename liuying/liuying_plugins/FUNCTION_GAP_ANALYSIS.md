# 流萤AI插件 功能差异分析与优化路线图

> 对比对象：`liuying_plugins/AI` vs `nonebot_plugin_personification`（参考插件）
> 生成日期：2026-06-28

---

## 一、总体概览

| 维度 | 流萤AI插件 | 参考插件 |
|------|-----------|---------|
| 核心文件数 | ~50个 .py | ~120+个 .py |
| 配置项数 | 44项 | 140+项 |
| 数据模型 | 12个 SQLAlchemy 模型 | 内嵌 SQLite |
| 架构模式 | 分层架构（config→models→core→agent→pipeline→handlers→jobs） | 扁平 + 服务工厂模式 |
| 内置技能包 | 极少量 | 18个 |
| 优势 | 架构清晰、模块职责明确、深度整合流萤本体 | 功能丰富、生态完善、拟人化细节到位 |

---

## 二、逐模块功能差异明细

### 2.1 核心对话与Agent系统

| 功能 | 流萤AI | 参考插件 | 差异评估 |
|------|--------|---------|---------|
| Agent循环（规划-执行-响应） | ✅ 三层架构 | ✅ 更丰富的Agent runtime | 🟡 基本对齐 |
| 回合规划器 shadow模式 | ❌ | ✅ | 🔴 缺失 |
| 证据合成器 | ✅ evidence.py | ✅ 可配置 | 🟡 对齐 |
| 交叉验证 | ❌ | ✅ cross_verify | 🔴 缺失 |
| 响应审查 | ❌ | ✅ response_review.py | 🔴 缺失 |
| 主动学习 | ❌ | ✅ active_learning.py | 🔴 缺失 |
| 记忆进化 | ❌ | ✅ evolves.py | 🔴 缺失 |

### 2.2 记忆系统

| 功能 | 流萤AI | 参考插件 | 差异评估 |
|------|--------|---------|---------|
| 记忆存储 | ✅ manager.py | ✅ memory_store.py | 🟡 对齐 |
| 记忆衰减 | ✅ memory_decay.py | ✅ | 🟡 对齐 |
| 记忆策展 | ✅ memory_curation.py | ✅ | 🟡 对齐 |
| 记忆巩固 | ✅ | ✅ | 🟡 对齐 |
| 记忆摘要 | ❌ | ✅ memory_summarizer.py | 🔴 缺失 |
| 多层级记忆 | ❌ | ✅ memory_tier.py | 🔴 缺失 |
| 记忆召回 | ✅ 5条 | ✅ RRF多路融合 | 🟡 差距 |
| 向量嵌入索引 | ❌ | ✅ embedding_index.py | 🔴 缺失 |
| 实体索引 | ❌ | ✅ entity_index.py | 🔴 缺失 |

### 2.3 情绪系统

| 功能 | 流萤AI | 参考插件 | 差异评估 |
|------|--------|---------|---------|
| 情绪状态管理 | ✅ emotion/ | ✅ emotion_state.py | 🟡 对齐 |
| 好感度系统 | ✅ 整合流萤本体 | ✅ | 🟡 对齐 |

### 2.4 上下文管理

| 功能 | 流萤AI | 参考插件 | 差异评估 |
|------|--------|---------|---------|
| 上下文压缩 | ✅ context/policy.py | ✅ | 🟡 对齐 |
| 上下文清理 | ❌ | ✅ context_cleanup.py | 🔴 缺失 |
| 会话存储 | ❌ | ✅ session_store.py | 🔴 缺失 |
| 时间上下文 | ❌ | ✅ time_ctx.py | 🔴 缺失 |

### 2.5 群聊功能

| 功能 | 流萤AI | 参考插件 | 差异评估 |
|------|--------|---------|---------|
| 群成员管理 | ✅ members.py | ✅ | 🟡 对齐 |
| 群禁言感知 | ✅ mute.py | ✅ | 🟡 对齐 |
| 群风格分析 | ✅ profile.py | ✅ | 🟡 对齐 |
| 群知识抽取 | ✅ profile.py | ✅ | 🟡 对齐 |
| 群聊摘要 | ✅ profile.py | ✅ | 🟡 对齐 |
| 群关系图谱 | ✅ social.py | ✅ | 🟡 对齐 |
| 群角色识别 | ✅ social.py | ✅ | 🟡 对齐 |
| 群知识自动构建 | ❌ 仅手动 | ✅ autobuild | 🔴 缺失 |
| 群风格自动构建 | ❌ 仅手动 | ✅ autobuild | 🔴 缺失 |

### 2.6 贴纸/表情包系统

| 功能 | 流萤AI | 参考插件 | 差异评估 |
|------|--------|---------|---------|
| 贴纸库 | ✅ library.py | ✅ | 🟡 对齐 |
| 贴纸策展 | ✅ curation.py | ✅ | 🟡 对齐 |
| 贴纸反馈 | ✅ 模型 | ✅ | 🟡 对齐 |
| 贴纸语义分析 | ❌ | ✅ sticker_semantics.py | 🔴 缺失 |
| 贴纸缓存 | ❌ | ✅ sticker_cache.py | 🔴 缺失 |
| 贴纸自动标注 | ❌ | ✅ sticker_labeler | 🔴 缺失 |

### 2.7 视觉/多媒体理解

| 功能 | 流萤AI | 参考插件 | 差异评估 |
|------|--------|---------|---------|
| 图片理解 | ✅ vision/manager.py | ✅ | 🟡 对齐 |
| GIF理解 | ✅ vision/manager.py | ✅ | 🟡 对齐 |
| 视频理解 | ❌ | ✅ | 🔴 缺失 |
| 图片生成 | ❌ | ✅ image_gen | 🔴 缺失 |
| 图片引用追踪 | ❌ | ✅ image_refs.py | 🔴 缺失 |
| 图片结果缓存 | ❌ | ✅ image_result_cache.py | 🔴 缺失 |

### 2.8 安全与合规

| 功能 | 流萤AI | 参考插件 | 差异评估 |
|------|--------|---------|---------|
| 安全过滤 | ✅ safety/filter.py | ✅ | 🟡 对齐 |
| 访问控制 | ✅ safety/acl.py | ✅ | 🟡 对齐 |
| 黑名单/白名单 | ✅ 依赖流萤本体 | ✅ | 🟡 通过本体实现 |
| 内容审核 | ❌ | ✅ moderation_handlers.py | 🔴 缺失 |

### 2.9 拟人化发送

| 功能 | 流萤AI | 参考插件 | 差异评估 |
|------|--------|---------|---------|
| 打字延迟 | ✅ humanize.py | ✅ | 🟡 对齐 |
| 碎片化输出 | ✅ humanize.py | ✅ | 🟡 对齐 |
| 错别字注入 | ✅ humanize.py | ✅ | 🟡 对齐 |
| 表情表态（Reaction） | ❌ | ✅ reaction.py | 🔴 缺失 |
| 拍一拍回复 | ❌ | ✅ poke_back | 🔴 缺失 |
| 输入状态显示 | ❌ | ✅ input_status | 🔴 缺失 |
| 引用回复 | ❌ | ✅ quote_reply | 🔴 缺失 |
| @回复 | ❌ | ✅ @回复 | 🔴 缺失 |

### 2.10 社交智能

| 功能 | 流萤AI | 参考插件 | 差异评估 |
|------|--------|---------|---------|
| 早晚问候 | ✅ social_intelligence.py | ✅ | 🟡 对齐 |
| 节日祝福 | ✅ social_intelligence.py | ✅ | 🟡 对齐 |
| 新闻推送 | ✅ social_intelligence.py | ✅ | 🟡 对齐 |
| 话题延续 | ✅ social_intelligence.py | ✅ | 🟡 对齐 |
| LLM闸门 | ❌ | ✅ gate.py | 🔴 缺失 |
| 配额管理 | ❌ | ✅ quota.py | 🔴 缺失 |
| 待处理话题 | ❌ | ✅ pending_topics.py | 🔴 缺失 |

### 2.11 主动行为

| 功能 | 流萤AI | 参考插件 | 差异评估 |
|------|--------|---------|---------|
| 群空闲发话 | ✅ proactive.py | ✅ | 🟡 对齐 |
| 私聊主动问候 | ✅ proactive.py | ✅ | 🟡 对齐 |
| 同伴感知 | ❌ | ✅ peer_awareness.py | 🔴 缺失 |
| 跟队形（复读跟随） | 🟡 基础检测 | ✅ 完整版 | 🟡 部分实现 |
| 热聊保护 | ❌ | ✅ hot_chat_min_pass_rate | 🔴 缺失 |
| 群聊活跃窗口 | ❌ | ✅ group_chat_active | 🔴 缺失 |

### 2.12 QZone（QQ空间）

| 功能 | 流萤AI | 参考插件 | 差异评估 |
|------|--------|---------|---------|
| 基础发说说 | ✅ qzone/service.py | ✅ | 🟡 对齐 |
| 入站（读取好友动态） | ❌ | ✅ qzone_inbound | 🔴 缺失 |
| 出站回复 | ❌ | ✅ qzone_outbound_reply | 🔴 缺失 |
| 社交互动（点赞评论） | ❌ | ✅ qzone_social | 🔴 缺失 |
| 第三方插话 | ❌ | ✅ third_party_chime_in | 🔴 缺失 |
| Cookie管理 | ✅ 基本 | ✅ 自动刷新 | 🟡 对齐 |

### 2.13 TTS（语音合成）

| 功能 | 流萤AI | 参考插件 | 差异评估 |
|------|--------|---------|---------|
| 基础TTS | ✅ tts/service.py | ✅ | 🟡 对齐 |
| 自动TTS | ✅ 配置 | ✅ | 🟡 对齐 |
| LLM决策TTS | ❌ | ✅ tts_llm_decision | 🔴 缺失 |
| 风格规划TTS | ❌ | ✅ tts_style_planner | 🔴 缺失 |
| 声音克隆 | ❌ | ✅ voice_clone | 🔴 缺失 |
| 内置安全 | ❌ | ✅ builtin_safety | 🔴 缺失 |

### 2.14 技能包系统（Skill Runtime）

| 功能 | 流萤AI | 参考插件 | 差异评估 |
|------|--------|---------|---------|
| 基础加载 | ✅ skill_runtime.py | ✅ | 🟡 对齐 |
| 内置skillpack | ❌ 极少量 | ✅ 18个 | 🔴 严重缺失 |
| 远程加载 | ❌ | ✅ GitHub/ZIP | 🔴 缺失 |
| MCP协议 | ❌ | ✅ mcp/bridge.py | 🔴 缺失 |
| 隔离执行 | ❌ | ✅ skill_isolation.py | 🔴 缺失 |
| 技能审查 | ❌ | ✅ remote_skill_review.py | 🔴 缺失 |
| 技能覆盖 | ❌ | ✅ skill_overrides.py | 🔴 缺失 |

### 2.15 工具系统

| 功能 | 流萤AI | 参考插件 | 差异评估 |
|------|--------|---------|---------|
| 工具注册表 | ✅ agent/tools.py | ✅ | 🟡 对齐 |
| 联网搜索 | ✅ tools/web.py | ✅ | 🟡 对齐 |
| 网页抓取 | ✅ tools/web.py | ✅ | 🟡 对齐 |
| 免配置搜索引擎 | ❌ | ✅ free_search.py | 🔴 缺失 |
| 搜索排序 | ❌ | ✅ search_ranker.py | 🔴 缺失 |
| 网络内容关联 | ❌ | ✅ web_grounding.py | 🔴 缺失 |
| 并行研究 | ❌ | ✅ parallel_research | 🔴 缺失 |
| 游戏信息 | ❌ | ✅ game_info | 🔴 缺失 |
| Wiki集成 | ❌ | ✅ wiki/fandom | 🔴 缺失 |
| 插件调用 | ❌ | ✅ plugin_invoker | 🔴 缺失 |
| 好友请求 | ❌ | ✅ friend_request_tool | 🔴 缺失 |

### 2.16 插件知识库

| 功能 | 流萤AI | 参考插件 | 差异评估 |
|------|--------|---------|---------|
| 基础存储 | ✅ knowledge/store.py | ✅ | 🟡 对齐 |
| 构建器 | ✅ knowledge/builder.py | ✅ | 🟡 对齐 |
| 运行时扫描 | ❌ | ✅ runtime_scan.py | 🔴 缺失 |
| 知识分析 | ❌ | ✅ analysis.py | 🔴 缺失 |
| 知识打包 | ❌ | ✅ bundle.py | 🔴 缺失 |
| 快照管理 | ❌ | ✅ snapshot.py | 🔴 缺失 |

### 2.17 运行时管理

| 功能 | 流萤AI | 参考插件 | 差异评估 |
|------|--------|---------|---------|
| 运行时开关 | ✅ runtime/switch.py | ✅ | 🟡 对齐 |
| 协议扩展 | ✅ runtime/protocol.py | ✅ | 🟡 对齐 |
| 运行时组装 | ❌ | ✅ runtime_assembly.py | 🔴 缺失 |
| 运行时构建器 | ❌ | ✅ runtime_builder.py | 🔴 缺失 |
| 运行时引导 | ❌ | ✅ runtime_bootstrap.py | 🔴 缺失 |
| 运行时集成 | ❌ | ✅ runtime_integrations.py | 🔴 缺失 |
| 服务工厂 | ❌ | ✅ service_factory.py | 🔴 缺失 |

### 2.18 管理与运维

| 功能 | 流萤AI | 参考插件 | 差异评估 |
|------|--------|---------|---------|
| 管理员命令 | ✅ admin_commands.py | ✅ | 🟡 对齐 |
| WebUI | ✅ webui/app.py | ✅ | 🟡 基本对齐 |
| WebUI认证 | ❌ | ✅ webui_auth_store.py | 🔴 缺失 |
| 审计日志 | ❌ | ✅ webui_audit_log.py | 🔴 缺失 |
| 系统诊断 | ❌ | ✅ diagnostics.py | 🔴 缺失 |
| 性能指标 | ❌ | ✅ metrics.py | 🔴 缺失 |
| 提供商健康 | ❌ | ✅ provider_health.py | 🔴 缺失 |
| 通知系统 | ❌ | ✅ notify.py | 🔴 缺失 |
| Git自动更新 | ❌ | ✅ git_auto_update | 🔴 缺失 |
| 数据迁移 | ❌ | ✅ migration.py | 🔴 缺失 |
| 帮助注册 | ❌ | ✅ help_registry.py | 🔴 缺失 |
| 用户任务 | ❌ | ✅ tasks_service.py | 🔴 缺失 |
| 线程跟踪 | ❌ | ✅ thread_tracker.py | 🔴 缺失 |
| 消息关系 | ❌ | ✅ message_relations.py | 🔴 缺失 |
| 插件运行时日志 | ❌ | ✅ plugin_runtime_logs.py | 🔴 缺失 |
| OneBot缓存 | ❌ | ✅ onebot_cache.py | 🔴 缺失 |

### 2.19 人格/画像系统

| 功能 | 流萤AI | 参考插件 | 差异评估 |
|------|--------|---------|---------|
| 人格管理 | ✅ persona.py + YAML | ✅ | 🟡 对齐 |
| 用户画像 | ✅ models/user_persona.py | ✅ | 🟡 对齐 |
| 画像服务 | ❌ | ✅ profile_service.py | 🔴 缺失 |
| 人设知识 | ❌ | ✅ persona_knowledge.py | 🔴 缺失 |
| 知识书（Lorebook） | ❌ | ✅ lorebook | 🔴 缺失 |

### 2.20 LLM/模型管理

| 功能 | 流萤AI | 参考插件 | 差异评估 |
|------|--------|---------|---------|
| LLM Helper | ✅ llm/helper.py | ✅ | 🟡 对齐 |
| Provider路由 | ✅ llm/provider_router.py | ✅ | 🟡 对齐 |
| Token记账 | ✅ llm/token_ledger.py | ✅ | 🟡 对齐 |
| 轻量模型 | ❌ | ✅ lite_model | 🔴 缺失 |
| 严格主模型模式 | ❌ | ✅ strict_main_model | 🔴 缺失 |
| Provider动态优先级 | ❌ | ✅ dynamic_priority | 🔴 缺失 |
| 月度额度 | ❌ | ✅ quota_monthly_tokens | 🔴 缺失 |
| 提示词加载器 | ❌ | ✅ prompt_loader.py | 🔴 缺失 |
| 提示词钩子 | ❌ | ✅ prompt_hooks.py | 🔴 缺失 |
| 内置钩子 | ❌ | ✅ builtin_hooks.py | 🔴 缺失 |
| 回复风格策略 | ❌ | ✅ reply_style_policy.py | 🔴 缺失 |
| 回复文本策略 | ❌ | ✅ reply_text_policy.py | 🔴 缺失 |
| 回复轮次追踪 | ❌ | ✅ reply_turn_trace.py | 🔴 缺失 |
| QQ表情名称 | ❌ | ✅ qq_face_names.py | 🔴 缺失 |

### 2.21 后台智能

| 功能 | 流萤AI | 参考插件 | 差异评估 |
|------|--------|---------|---------|
| 后台智能处理 | ❌ | ✅ background_intelligence.py | 🔴 缺失 |
| 主动诊断 | ❌ | ✅ proactive_diagnostics.py | 🔴 缺失 |
| 梗百科 | ❌ | ✅ meme_dictionary.py | 🔴 缺失 |

### 2.22 其他

| 功能 | 流萤AI | 参考插件 | 差异评估 |
|------|--------|---------|---------|
| 日记系统 | ✅ diary.py | ✅ | 🟡 对齐 |
| YAML管道 | ❌ | ✅ yaml_pipeline/ | 🔴 缺失 |
| 文件发送 | ❌ | ✅ file_sender.py | 🔴 缺失 |
| 环境写入 | ❌ | ✅ env_writer.py | 🔴 缺失 |
| 按时区时间 | ✅ 依赖本体 | ✅ | 🟡 对齐 |

---

## 三、统计汇总

| 类别 | 已对齐 | 部分实现 | 完全缺失 |
|------|--------|---------|---------|
| 核心对话与Agent | 2 | 0 | 5 |
| 记忆系统 | 4 | 1 | 4 |
| 情绪系统 | 2 | 0 | 0 |
| 上下文管理 | 1 | 0 | 3 |
| 群聊功能 | 7 | 0 | 2 |
| 贴纸/表情包 | 3 | 0 | 3 |
| 视觉/多媒体 | 2 | 0 | 4 |
| 安全与合规 | 2 | 1 | 1 |
| 拟人化发送 | 3 | 0 | 5 |
| 社交智能 | 4 | 0 | 3 |
| 主动行为 | 2 | 1 | 3 |
| QZone | 2 | 0 | 4 |
| TTS | 2 | 0 | 4 |
| 技能包系统 | 1 | 0 | 6 |
| 工具系统 | 3 | 0 | 8 |
| 插件知识库 | 2 | 0 | 4 |
| 运行时管理 | 2 | 0 | 5 |
| 管理与运维 | 2 | 0 | 14 |
| 人格/画像 | 2 | 0 | 3 |
| LLM/模型管理 | 3 | 0 | 11 |
| 后台智能 | 0 | 0 | 3 |
| 其他 | 2 | 0 | 3 |
| **合计** | **53** | **3** | **98** |

---

## 四、优化路线图

### 第一阶段：核心体验增强（P0，预计1-2周）

| 序号 | 功能 | 说明 | 技术路线 |
|------|------|------|---------|
| 1 | 表情表态（Reaction） | NO_REPLY时贴表情代替沉默 | 参考 `reaction.py`，需 NapCat/LLOneBot 扩展API |
| 2 | 引用回复 | 跨楼回复时带引用 | 参考 `quote_reply`，OneBot v11标准reply段 |
| 3 | @回复 | 多人混战时@回复对象 | 参考 `@回复` 实现，与引用互斥 |
| 4 | 输入状态显示 | 私聊回复前显示"正在输入" | 参考 `input_status`，需 NapCat 系支持 |
| 5 | 跟队形完善 | 复读检测+TTL缓存+聚类 | 参考 `repeat_follow.py` 完整实现 |
| 6 | 同伴感知 | 检测其他机器人避免互相对话 | 参考 `peer_awareness.py` |
| 7 | 热聊保护 | 热聊时降低随机发言概率 | 添加 `hot_chat_min_pass_rate` 配置 |
| 8 | 回复审查 | 发送前LLM二次审查响应质量 | 参考 `response_review.py` |
| 9 | 记忆摘要 | 长记忆自动压缩摘要 | 参考 `memory_summarizer.py` |

### 第二阶段：智能深度提升（P1，预计2-3周）

| 序号 | 功能 | 说明 | 技术路线 |
|------|------|------|---------|
| 10 | 主动学习 | LLM不确定时自主查证学习 | 参考 `active_learning.py` |
| 11 | 记忆进化 | 关系分析（替换/补充/确认/质疑） | 参考 `evolves.py` |
| 12 | 多层级记忆 | working/episodic/semantic/background | 参考 `memory_tier.py` |
| 13 | 向量嵌入索引 | 支持语义向量检索 | 参考 `embedding_index.py`，集成外部embedding |
| 14 | 社交LLM闸门 | 发送前LLM二次决策时机 | 参考 `gate.py` |
| 15 | 社交配额管理 | 每用户每日主动消息配额 | 参考 `quota.py` |
| 16 | 图片生成 | AI图片生成（DALL-E/Gemini） | 参考 `image_gen` skill |
| 17 | 视频理解 | 视频内容分析 | 参考视频fallback实现 |
| 18 | 轻量模型 | lite_model用于intent分类等 | 参考 `lite_model` 配置 |
| 19 | 回复轮次追踪 | 追踪回复轮次与质量 | 参考 `reply_turn_trace.py` |

### 第三阶段：生态与工具扩展（P2，预计2-3周）

| 序号 | 功能 | 说明 | 技术路线 |
|------|------|------|---------|
| 20 | 核心Skillpack补齐 | news/weather/datetime_tool等 | 参考参考插件18个skillpack |
| 21 | 远程Skill加载 | GitHub/ZIP远程skill源 | 参考 `skill_runtime/custom_loader.py` |
| 22 | MCP协议 | Model Context Protocol支持 | 参考 `mcp/bridge.py` |
| 23 | 免配置搜索引擎 | Wikipedia/SearXNG/DuckDuckGo | 参考 `free_search.py` |
| 24 | 并行研究 | 多worker并行深度研究 | 参考 `parallel_research` |
| 25 | 游戏信息 | 游戏更新/攻略聚合 | 参考 `game_info` skill |
| 26 | Wiki集成 | 维基/Fandom查询 | 参考wiki/fandom实现 |
| 27 | 梗百科 | 网络梗数据库 | 参考 `meme_dictionary.py` |
| 28 | 搜索排序 | 搜索结果排序 | 参考 `search_ranker.py` |
| 29 | 网络内容关联 | 文本与网络内容关联 | 参考 `web_grounding.py` |
| 30 | 插件调用 | 代为执行其他插件命令 | 参考 `plugin_invoker` |

### 第四阶段：运维与平台化（P3，预计2-3周）

| 序号 | 功能 | 说明 | 技术路线 |
|------|------|------|---------|
| 31 | 系统诊断 | 功能健康体检 | 参考 `diagnostics.py` |
| 32 | 性能指标 | 性能指标收集 | 参考 `metrics.py` |
| 33 | Provider健康 | 动态提供商健康监控 | 参考 `provider_health.py` |
| 34 | WebUI认证 | 设备审批/登录验证 | 参考 `webui_auth_store.py` |
| 35 | 审计日志 | WebUI操作审计 | 参考 `webui_audit_log.py` |
| 36 | 用户任务 | 用户定时任务（"每天8点提醒"） | 参考 `tasks_service.py` |
| 37 | QZone完善 | 入站/出站/社交/第三方插话 | 参考qzone系列模块 |
| 38 | TTS完善 | LLM决策/风格规划/声音克隆 | 参考tts系列模块 |
| 39 | 通知系统 | 管理员通知推送 | 参考 `notify.py` |
| 40 | 文件发送 | 文件发送功能 | 参考 `file_sender.py` |

### 第五阶段：架构优化（P4，长期）

| 序号 | 功能 | 说明 |
|------|------|------|
| 41 | 服务工厂模式 | 引入依赖注入降低耦合 |
| 42 | 运行时组装 | 动态运行时组装 |
| 43 | 数据迁移工具 | 数据格式升级迁移 |
| 44 | Git自动更新 | 插件自动更新 |
| 45 | 上下文清理 | 过期上下文自动清理 |
| 46 | 会话存储 | 会话级状态持久化 |
| 47 | 时间上下文 | 时间感知（工作日/假期/时段） |
| 48 | 提示词加载器 | 统一提示词模板加载 |
| 49 | 提示词钩子 | 提示词前后处理钩子 |
| 50 | 内置钩子 | 事件触发自定义代码 |
| 51 | 实体索引 | 命名实体提取与索引 |
| 52 | 贴纸语义分析 | 基于语义的贴纸匹配 |
| 53 | 贴纸自动标注 | 基于视觉LLM的贴纸打标 |
| 54 | 图片引用追踪 | 图片引用关系管理 |
| 55 | 图片结果缓存 | 图片理解结果缓存 |
| 56 | 人设知识 | 人设专属知识库 |
| 57 | 知识书（Lorebook） | 额外上下文知识注入 |
| 58 | 回复风格策略 | 独立风格策略 |
| 59 | 回复文本策略 | 独立文本策略 |
| 60 | QQ表情名称 | QQ表情编号→中文名映射 |
| 61 | 内容审核 | 独立内容审核模块 |
| 62 | 后台智能处理 | 异步后台智能分析 |
| 63 | 主动诊断 | 主动预测和解决潜在问题 |
| 64 | 插件运行时日志 | 运行时日志捕获 |
| 65 | 消息关系 | 消息间依赖关系维护 |
| 66 | 线程跟踪 | 多线程任务跟踪 |
| 67 | 帮助注册 | 统一帮助系统 |
| 68 | 环境写入 | 环境变量写入 |
| 69 | YAML管道 | YAML风格响应管道 |
| 70 | 群知识自动构建 | 自动触发群知识构建 |
| 71 | 群风格自动构建 | 自动触发群风格分析 |
| 72 | 插件知识库运行时扫描 | 自动扫描插件变化 |
| 73 | 插件知识库分析/打包/快照 | 知识库高级管理 |
| 74 | 贴纸缓存 | 贴纸访问缓存 |
| 75 | 技能隔离执行 | 子进程隔离执行不可信skill |
| 76 | 技能审查 | 远程技能安全审查 |
| 77 | 技能覆盖 | 运行时覆盖默认技能 |
| 78 | OneBot缓存 | OneBot协议缓存 |
| 79 | 好友请求 | 自动好友请求处理 |
| 80 | 拍一拍回复 | 被拍后自动拍回 |

---

## 五、技术架构建议

1. **保持现有分层架构**：AI插件的分层架构（config→models→core→agent→pipeline→handlers→jobs）比参考插件的扁平化设计更清晰，应继续保持。

2. **新增功能优先放入现有子包**：新增功能应按职责归入现有子包，如"回复审查"放入 `core/safety/` 或新建 `core/review/`。

3. **Skillpack是最大短板**：参考插件18个内置skillpack是功能丰富度的关键。优先补齐 `news`、`weather`、`datetime_tool`、`game_info`、`wiki` 等核心skillpack。

4. **避免过度拆分**：每个模块代码量建议不超过600行，新增功能时注意模块粒度。

5. **复用流萤本体能力**：群管理、黑名单、白名单、权限等功能已通过流萤本体实现，无需重复开发。

6. **拟人化是体验核心**：第一阶段（P0）的拟人化增强直接影响用户感知，应优先完成。