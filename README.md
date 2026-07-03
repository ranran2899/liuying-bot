# 流萤机器人（liuying-bot）

基于 NoneBot2 v2.5.0 构建的多适配器聊天机器人，集成 AI 对话核心、经济系统、管理员体系与 WebUI 控制台。

- 当前版本：`v0.1.4-b`
- 框架：NoneBot2 `>=2.5.0,<2.6.0` | SQLAlchemy `2.0.49` | Python `>=3.11`
- 包管理：Poetry | 许可证：AGPL-3.0

## 功能特性

### 核心能力

- 多适配器：OneBot V11 / OneBot V12 / QQ 官方 / Minecraft
- 驱动：`fastapi + httpx + websockets`
- 多数据库：SQLite / MySQL / PostgreSQL，支持主库 + 辅助库 + 可选同步
- 统一缓存：内存 / Redis 双后端（`liuying/services/cache`）
- HTML 渲染：基于 Playwright（`liuying/services/renderer`）
- 统一图床 `bed_layout`：本地/阿里云/百度云/华为云/腾讯云/AWS
- APScheduler 任务调度（`liuying/utils/apscheduler`）
- 多级权限与限流：超管 / 平台超管 / 群管 / 用户 ACL
- 完善日志体系：行为/性能/调度/银行等独立表

### 流萤 AI 插件（`liuying_plugins/AI`）

- AI 对话核心 + Agent 工具调用 + 拟人化发送
- 4 层记忆系统：工作/情节/语义/背景记忆，RRF 融合检索
- 用户级人格隔离：每人独立切换 bot 人格，对话/记忆/情绪完全隔离
- 多模态：图片理解、生成、视频理解；TTS 语音、贴纸、表情包
- 主动行为：定时日记、记忆巩固/衰减、社交智能、知识刷新
- 安全网关：内容审核、Token 配额、ACL 控制器、响应复审
- 内置 Agent 工具：搜索/知识库/记忆/群组/媒体/上下文/技能包
- 公开 API：`register_external_tool` 供第三方注册自定义工具
- WebUI 控制台（`liuying/plugins/AI_webui`）

### 经济与娱乐

- 流萤银行：存取款/兑换/转账/定期/贷款
- 商店与拍卖行：道具、个人商店、比价搜索
- 签到、今日运势、每日 wife、漂流瓶、自动点赞订阅

### 管理与平台

- 管理员与超管体系：ban、广播、SQL 执行、插件开关、数据清理
- UI 管理：主题切换、主题商店、个人主题
- 插件商店：添加/移除/搜索/更新
- QQ 双通道适配 + 机器人配置管理 + 流萤 AI 空间工具
- 免配置网络搜索：Bing/Wikipedia/SearXNG/DuckDuckGo 兜底

## 快速开始

### 1. 环境要求

- Python `3.11+`、Poetry
- 可选：Redis（缓存）、Playwright（HTML 渲染）

### 2. 安装 Poetry

```bash
# 推荐：pipx
pip install pipx && pipx ensurepath
pipx install poetry

# 或：官方脚本
curl -sSL https://install.python-poetry.org | python3 -
```

国内镜像加速：

```bash
poetry source add --priority=primary aliyun https://mirrors.aliyun.com/pypi/simple/
```

### 3. 克隆与安装

```bash
git clone https://gitee.com/shiranranran/liuying-bot.git
cd liuying-bot/liuying_bot0.1.4
poetry install                  # 基础安装
poetry install --extras redis   # 启用 Redis 缓存
poetry run playwright install chromium   # 首次使用 HTML 渲染
```

### 4. 配置 `.env`

根目录 `.env` 已含完整示例与中文注释，关键项：

| 配置项 | 说明 | 示例 |
| --- | --- | --- |
| `COMMAND_START` | 命令起始符 | `[""]` |
| `SUPERUSERS` | 全局超级用户 | `["123456789"]` |
| `DB_URL` | 主数据库 | `sqlite+aiosqlite:///data/db/liuying.db` |
| `CACHE_MODE` | 缓存模式 | `MEMORY` / `REDIS` / `NONE` |
| `HOST` / `PORT` | 监听地址 | `0.0.0.0` / `8080` |
| `QQ_BOTS` | QQ 官方机器人配置 | JSON 字符串 |

数据库示例：

```ini
DB_URL = "sqlite+aiosqlite:///data/db/liuying.db"
# DB_URL = "mysql+asyncmy://user:pass@127.0.0.1:3306/db"
# DB_URL = "postgresql+asyncpg://user:pass@127.0.0.1:5432/db"
```

### 5. 启动

```bash
poetry run python bot.py          # 命令行
poetry run nb run --reload        # 热重载（开发）
# Windows：双击 win启动.bat
```

协议端连接地址：

| 适配器 | 地址 |
| --- | --- |
| OneBot V11 | `ws://127.0.0.1:8080/onebot/v11/ws` |
| OneBot V12 | `ws://127.0.0.1:8080/onebot/v12/ws` |
| QQ 官方 | 由 `QQ_BOTS` 决定 |
| Minecraft | 由适配器决定 |

## 项目架构

```
liuying_bot0.1.4/
├── bot.py                    # 入口
├── pyproject.toml            # Poetry + ruff
├── .env                      # 环境变量
└── liuying/
    ├── configs/              # 全局配置
    ├── models/               # 数据库模型（按业务域分）
    │   ├── _bot/ _group/ _llm/ _log/ _user/
    ├── services/             # 核心服务
    │   ├── cache/            #   统一缓存（内存/Redis）
    │   ├── liuying_db/       #   数据库服务
    │   └── renderer/         #   HTML 渲染
    ├── ui/                   # UI 构建器与模型
    ├── utils/                # 通用工具
    │   ├── LLM/ apscheduler/ bed_layout/ bot/
    │   ├── http/ image/ manager/ repo_utils/ user/
    ├── liuying_plugins/      # 主插件目录
    │   ├── AI/ admin/ auction/ bank/ bottle/
    │   ├── fortune/ help/ hooks/ init/ platform/
    │   ├── plugin_store/ shop/ signIn/ statistics/
    │   ├── superuser/ ui_manager/ user_info/ wife/
    │   └── withdraw.py record_request.py
    └── plugins/              # 自定义插件
        ├── AI_webui/ qq_bot_config/ qzone/
        ├── web_search/ zan/
```

## 插件清单

### 业务插件

| 插件 | 主要指令 |
| --- | --- |
| 流萤 AI | `@bot [消息]`、`bot对话/人格/记忆/说`、`我的画像`、`流萤AI状态/开关/体检` |
| 流萤银行 | `存款/取款`、`兑换`、`转账`、`定期`、`贷款`、`还款`、`排行`、`记录` |
| 商店 | `商店 [名]`、`购买/使用道具`、`开店`、`上架/下架/改价` |
| 拍卖行 | `拍卖行`、`购买/上架/下架/搜索`、`我的拍卖`、`比价` |
| 签到 | `签到` |
| 今日运势 | `今日运势`、`刷新今日运势` |
| 每日 wife | `抽wife`、`查找wife`、`添加wife` |
| 漂流瓶 | `扔/捡/评论/点赞瓶子` |
| 用户信息 | `我的信息` |
| UI 管理 | `我的主题`、`切换主题`、`主题商店`、`ui reload` |
| 统计 | `功能调用统计`、`日/周/月功能调用统计` |
| 自动点赞 | `点赞我`、`订阅赞`、`取消订阅赞` |
| 消息撤回 | `[引用消息] 撤回` |

### 管理插件

| 插件 | 入口 |
| --- | --- |
| 管理员帮助 | `管理员帮助`（ban/权限/群管/敏感词/金币等） |
| 超级用户帮助 | `超级用户帮助`（bot管理/广播/清理/SQL/群管理） |
| 帮助菜单 | `功能 [名称]`、`详细帮助` |
| 插件商店 | `插件商店/添加/移除/搜索/更新` |
| QQ 配置 | `qq配置添加/查询/修改/删除/意图/状态` |
| 流萤 AI 空间 | `流萤AI空间 [set/clear]`、`流萤AI空间状态` |
| 流萤 AI WebUI | 浏览器 `http://<bot>:<port>/ai/` |

## 开发说明

### 代码规范

- PEP 8 / PEP 484，Google 风格文档字符串
- 单行 ≤ 88 字符，使用 ruff
- 函数/参数/返回值添加类型提示
- 顶部导入：标准库 → 第三方 → 项目内部，禁止通配导入
- 中文对话与注释，禁止 emoji

### 常用命令

```bash
poetry run ruff check
poetry run ruff format
poetry run python -m py_compile <file>
poetry run nb run --reload
```

### 添加新插件

1. 在 `liuying/liuying_plugins/` 或 `liuying/plugins/` 创建包
2. 用 `PluginMetadata` 声明元数据
3. 通过 `PluginExtraData` 配置命令，通过 `PriorityLifecycle` 注册启动优先级
4. 使用 `MessageUtils.build_message(...).send(...)` 发送消息
5. 数据库模型遵循「一表一模块」，存放于 `liuying/models/` 子包

### 注册 Agent 工具

```python
from liuying_plugins.AI import register_external_tool, AgentTool

class MyTool(AgentTool):
    name = "my_tool"
    description = "自定义工具"

    async def execute(self, **kwargs) -> str:
        return "ok"

register_external_tool(MyTool())
```

## 注意事项

- 启动前确认 `.env` 配置完整（数据库/超管）
- SQLite 默认启用 WAL 避免 `database is locked`
- Redis 需先 `poetry install --extras redis`
- 渲染需 `poetry run playwright install chromium`
- AI 插件依赖外部 LLM Provider，需配置 API Key
- 协议端与机器人不同服务器时，将 `IMAGE_TO_BYTES` 设为 `True`
- AI 插件优先级为 2，需在数据库/LLM/缓存就绪后加载

## 贡献与反馈

- 仓库：[gitee.com/shiranranran/liuying-bot](https://gitee.com/shiranranran/liuying-bot)
- 反馈：[Issues](https://gitee.com/shiranranran/liuying-bot/issues)
- 提交前运行 `poetry run ruff check` 与 `poetry run python -m py_compile`

## 更新记录

### v0.1.4-b

- 重构 AI 插件分层：config → models → core → agent → pipeline → handlers → jobs → tts
- 新增用户级人格隔离、4 层记忆系统（RRF 融合）、Agent 工具调用、多模态、WebUI
- 重构统一缓存（`liuying/services/cache`）与数据库服务层
- 新增 HTML 渲染、UI 构建器、图床 `bed_layout`、APScheduler 封装
- 新增 HTTP 工具集、QQ 配置管理、AI 空间工具、自动点赞
- 升级 NoneBot2 v2.5.0、SQLAlchemy 2.0.49

### v0.0.5

- 优化数据库模块，支持 SQLite / MySQL / PostgreSQL

### v0.0.4

- 重置帮助 HTML 模板

### v0.0.3 ~ v0.0.1

- 性能优化、细节调整、初始版本
