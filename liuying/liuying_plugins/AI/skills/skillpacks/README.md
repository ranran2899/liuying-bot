技能包开发规范

本目录下每个子目录是一个独立技能包，由 `skills/loader.py` 自动发现并注册。
新增技能不需要修改任何主插件代码，放好目录即生效。

一、标准五件套结构

    <skill_name>/
        SKILL.md              必需  人类可读说明，含 YAML frontmatter 兜底元数据
        skill.yaml            必需  机器可读元数据，权威来源
        agents/openai.yaml    可选  展示元数据 display_name / description / icon
        references/README.md  推荐  实现说明与设计取舍
        references/mapping.md 推荐  函数到工具名的映射表
        scripts/main.py       必需  入口，三段式接口
        scripts/impl.py       推荐  核心实现，与入口分离

目录名即技能名，禁止以 `_` 或 `.` 开头（会被加载器跳过）。

二、skill.yaml 字段

    name          技能名，缺省取目录名
    description   描述，用于技能清单展示
    category      分类：query / compute / research / memory / language /
                  vision / expression / general
    entrypoint    入口相对路径，缺省按 scripts/main.py > run.py > skill.py 探测
    enabled       是否启用，false 时跳过加载
    parameters    单函数技能（run 形式）的 JSON Schema
    isolation     子进程隔离配置，mode: process / timeout / inherit_env

元数据合并规则：`skill.yaml` 优先，其缺失的字段由 `SKILL.md`
的 frontmatter 兜底，`agents/openai.yaml` 只补充展示字段。

三、scripts/main.py 三段式接口

加载器按 `register` > `build_tools` > `run` 的优先级选用其中一个。

1. `build_tools(runtime) -> list[AgentTool]`（推荐）
   自行构造工具，可一个技能包注册多个相关工具。
   范本：`time_companion`（4 个工具）、`sticker_tool`（3 个工具）。

2. `register(runtime, registry) -> None`
   需要直接操作注册表的高级场景，自行调用 `registry.register`。

3. `run(**kwargs) -> str`
   最简单函数技能，加载器按 `skill.yaml` 的 `parameters` 合成工具。
   同时建议保留 `run` 作为调试入口，便于脱离 Bot 单测。

四、runtime 可用服务

`SkillRuntime`（`skills/api.py`）是访问主插件服务的唯一通道，
禁止在技能包内直接导入主插件全局单例：

    runtime.config(key, default)  读插件配置
    runtime.logger                日志器
    runtime.get_now()             当前时间
    runtime.llm_helper            chat / chat_text / embedding / tts /
                                  image_generate / web_search
    runtime.memory_manager        add / get_memory_summary / build_memory_prompt
    runtime.knowledge_base        插件知识库
    runtime.persona_manager       人格管理
    runtime.data_dir              数据目录
    runtime.scheduler             定时任务调度器
    runtime.get_bots()            全部 bot 实例

服务可能为 None（未配置），必须用 `getattr(runtime, "x", None)`
取值并在为 None 时返回可读的不可用提示。

五、工具定义要点

`AgentTool` 的元数据字段直接影响调度效率，必须如实填写：

    intent_tags        意图标签，决定工具是否进入本轮候选集
    latency_class      fast / network / slow，影响并发编排与超时
    requires_network   需要外网
    requires_image     需要图片输入
    evidence_kind      tool 产生新证据 / context 只读上下文
    per_session_quota  每会话调用上限，0 为不限；重型工具务必设置

六、会话身份获取

涉及用户身份的技能，一律从 `agent/runtime/session_context` 取：

    get_current_user_id() / get_current_group_id() / get_current_persona_name()

禁止把 user_id 做成工具参数，否则模型可被诱导越权读写他人数据。

七、异常处理约束

- 外部不确定性（网络、LLM、检索）允许 try-except 降级为可读提示
- 纯数据库 ORM 操作、字典访问、纯计算禁止 try-except，让异常上抛
- 工具永远不要返回空串，无结果时也要给出明确说明供模型判断

八、编写 SKILL.md 的要求

SKILL.md 会随技能清单进入模型视野，直接决定调用准确率，必须包含：

- 何时该调用、何时不该调用
- 与其他相似技能的分工边界
- 参数格式的具体示例
- 配额与截断等硬性边界

九、技能层公共工具

跨技能复用的底层能力放在 `skills/` 而非某个技能包内，避免重复实现：

    skills/media.py   fetch_image / fetch_images / detect_mime / is_gif
                      图片按魔数判定格式、体积上限保护、并发拉取

`vision_analyze`、`web_search` 都复用 `skills/media.py`，
新增视觉类技能不要再各自写下载逻辑。

十、避免与内置工具重名

`agent/tools/builtin/` 已注册一批内置工具（含 `web_search`、
`get_current_time` 等）。注册表对同名工具**静默覆盖**，
重名会让内置实现失效且难以定位。新增工具前先确认名字未被占用，
定位相近时用更具体的名字区分（如 `visual_web_search`）。

十一、自检清单

- [ ] `uv run ruff check` 通过
- [ ] 所有函数有 Google 风格中文文档字符串
- [ ] 单行不超过 88 字符，无 emoji
- [ ] 服务为 None 时有降级分支
- [ ] 重型工具设置了 `per_session_quota`
- [ ] `references/mapping.md` 列出了实际暴露的工具名
