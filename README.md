# 流萤机器人（liuying-bot）

基于 NoneBot2 v2.5.0 构建的多适配器聊天机器人项目，集成完整的 AI 对话核心、经济系统、管理员体系与 WebUI 控制台。

- 当前版本：`v0.1.4-b`（开发版）
- 框架：NoneBot2 `>=2.5.0,<2.6.0`
- 数据库：SQLAlchemy `2.0.49`（支持 SQLite / MySQL / PostgreSQL）
- 包管理：Poetry（`package-mode = false`）
- Python：`>=3.11`
- 许可证：AGPL-3.0

## 功能特性

### 核心能力

- 多适配器支持：OneBot V11 / OneBot V12 / QQ 官方适配器 / Minecraft 适配器
- 驱动器：`fastapi + httpx + websockets`
- 多数据库连接与读写分离：主库 + 辅助库（log/bed\_layout 等）+ 可选同步
- 统一缓存层：内存缓存 / Redis 二选一，由 `liuying/services/cache` 统一调度
- HTML 渲染与图片生成：基于 Playwright 与 `liuying/services/renderer`
- 统一图床服务 `bed_layout`：支持本地/阿里云/百度云/华为云/腾讯云/AWS
- 完整 APScheduler 任务调度：`liuying/utils/apscheduler`
- 多级权限与限流：超级用户、平台超管、群组管理员、用户级 ACL
- 完善日志体系：行为日志、性能日志、调度日志、银行日志等独立表

### 流萤 AI 插件（`liuying_plugins/AI`）

- AI 对话核心 + Agent 工具调用 + 拟人化发送
- 完整记忆系统：工作记忆 / 情节记忆 / 语义记忆 / 背景记忆（4 层架构，RRF 融合检索）
- 用户级人格隔离：每个用户可独立切换当前 bot 人格，对话历史/记忆/情绪完全隔离
- 多模态视觉：图片理解、图片生成、视频理解（基于多 LLM Provider 能力发现）
- TTS 语音合成、贴纸系统、表情包库
- 主动行为：定时日记、记忆巩固、记忆衰减、社交智能、知识刷新
- 安全网关：内容审核、Token 配额、ACL 控制器、响应复审
- 内置 Agent 工具：搜索、知识库、记忆、群组、媒体、上下文、技能包（天气/新闻/wiki/游戏/日期）
- 公开 API：`register_external_tool` 供第三方插件注册自定义 Agent 工具
- WebUI 控制台：`liuying/plugins/AI_webui` 提供状态/配置/记忆/开关/人格/Token 统计管理

### 经济与娱乐系统

- **流萤银行**：金币/银币/铜币存取款、兑换、转账、定期存款、贷款及利息结算
- **商店**：系统道具购买/使用、个人商店开店与交易
- **拍卖行**：物品上架、购买、搜索、分页浏览、比价
- **签到**：每日签到，随机金币与好感度奖励，连续签到加成
- **每日 wife**：每日随机二次元老婆抽取与管理
- **漂流瓶**：扔/捡/评论/点赞，附 Web 审核后台
- **今日运势**：每日随机运势
- **自动点赞订阅赞**：每日 0 点定时点赞

### 管理与平台

- **管理员体系**：ban、bot 权限、插件开关、群管、敏感词、金币查询等
- **超级用户体系**：bot 管理、广播、数据清理、SQL 执行、群管理、请求管理
- **UI 管理**：主题切换、主题商店、个人主题选择、UI 渲染服务配置
- **插件商店**：支持添加/移除/搜索/更新插件
- **功能调用统计**：日/周/月功能调用统计可视化
- **平台适配**：QQ OneBot 与 QQ 官方双通道，按适配器动态加载
- **QQ 机器人配置管理**：动态管理 QQ 适配器配置（添加/查询/修改/删除/意图/状态）
- **流萤 AI 空间工具**：QQ 空间协议封装 + Agent 工具 + 管理命令 + WebUI
- **网络搜索免配置客户端**：Bing HTTP / Wikipedia / SearXNG / DuckDuckGo 兜底方案

## 安装与运行

### 1. 环境要求

- Python `3.11+`
- Poetry（最新稳定版）
- 可选：Redis（启用 Redis 缓存时需要）
- 可选：Playwright 浏览器（启用 HTML 渲染与图片生成时需要）

### 2. 安装 Poetry

 Poetry 是本项目的依赖管理工具，必须先安装才能继续后续步骤。
 推荐使用 `pipx` 安装（隔离环境，避免依赖冲突），也可使用官方脚本或 `pip`。

#### 方式一：使用 pipx 安装（推荐）

 `pipx` 会为 Poetry 创建独立的虚拟环境，避免与系统 Python 包冲突。

```bash
# 安装 pipx（若未安装）
# Windows
pip install pipx
pipx ensurepath

# Linux / macOS
python -m pip install --user pipx
python -m pipx ensurepath

# 安装 Poetry
pipx install poetry

# 升级 Poetry
pipx upgrade poetry
```

#### 方式二：使用官方安装脚本

```bash
# Windows（PowerShell）
(Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | python -

# Linux / macOS / WSL
curl -sSL https://install.python-poetry.org | python3 -
```

#### 方式三：使用 pip 安装

```bash
pip install poetry
```

#### 配置国内 PyPI 镜像（可选）

 国内网络环境下，建议配置镜像加速依赖下载。

```bash
poetry source add --priority=primary aliyun https://mirrors.aliyun.com/pypi/simple/
```

#### 验证安装

```bash
poetry --version
```

 输出示例：`Poetry (version 1.8.x)`，表示安装成功。

### 3. 克隆项目
```bash
git clone https://gitee.com/shiranranran/liuying-bot.git
cd liuying-bot/liuying_bot0.1.4
```

### 4. 安装依赖

默认使用阿里云 PyPI 镜像（见 `pyproject.toml` 中 `aliyun` 源）。

```bash
# 基础安装
poetry install

# 启用 Redis 缓存
poetry install --extras redis
```

### 5. 安装 Playwright 浏览器（首次使用）
```bash
poetry run playwright install chromium
```

### 6. 配置 `.env` 文件

项目根目录的 `.env` 文件已包含完整示例与中文注释，按需修改以下关键项：

| 配置项                                                             | 说明            | 示例                                       |
| --------------------------------------------------------------- | ------------- | ---------------------------------------- |
| `COMMAND_START`                                                 | 命令起始符         | `[""]`（默认空，匹配自然语言指令）                     |
| `SUPERUSERS`                                                    | 全局超级用户        | `["123456789"]`                          |
| `PLATFORM_SUPERUSERS`                                           | 平台级超级用户       | JSON 字符串，按 `qq`/`dodo` 等平台分别配置           |
| `NICKNAME`                                                      | 机器人昵称         | `["流萤", "流萤酱"]`                          |
| `HOST` / `PORT`                                                 | 监听地址与端口       | `0.0.0.0` / `8080`                       |
| `DRIVER`                                                        | 驱动器           | `~fastapi+~httpx+~websockets`            |
| `DB_URL`                                                        | 主数据库连接        | `sqlite+aiosqlite:///data/db/liuying.db` |
| `DB_URLS`                                                       | 辅助数据库连接       | JSON 字符串，支持 `log_db`/`bed_layout_db` 等   |
| `DB_SYNC_ENABLED`                                               | 数据库同步开关       | `False`（实验性功能）                           |
| `CACHE_MODE`                                                    | 缓存模式          | `MEMORY` / `REDIS` / `NONE`              |
| `REDIS_HOST` / `REDIS_PORT` / `REDIS_PASSWORD` / `REDIS_EXPIRE` | Redis 配置      | 启用 `REDIS` 时填写                           |
| `ONEBOT_ACCESS_TOKEN`                                           | OneBot 访问令牌   | `abc1234`                                |
| `QQ_BOTS`                                                       | QQ 官方机器人配置    | JSON 字符串，含 id/token/secret/intent        |
| `QQ_RECONNECT_DELAY` / `QQ_MAX_RECONNECT`                       | QQ 重连策略       | `10` / `5`                               |
| `IMAGE_TO_BYTES`                                                | 图片统一 bytes 发送 | `True`（协议端不在同服务器时启用）                     |

#### 数据库连接示例

```ini
# SQLite（推荐一键启动）
DB_URL = "sqlite+aiosqlite:///data/db/liuying.db"

# MySQL
DB_URL = "mysql+asyncmy://user:password@127.0.0.1:3306/database"

# PostgreSQL
DB_URL = "postgresql+asyncpg://user:password@127.0.0.1:5432/database"
```

#### QQ 官方机器人配置示例

```ini
QQ_BOTS='[
  {
    "id": "123456789",
    "token": "your_token",
    "secret": "your_secret",
    "intent": {
      "guilds": true,
      "guild_members": true,
      "guild_messages": false,
      "c2c_group_at_messages": true,
      "at_messages": true,
      "direct_message": false,
      "message_audit": true
    },
    "use_websocket": true
  }
]'
```

### 7. 启动机器人

#### 方式一：命令行启动

```bash
poetry run python bot.py
```

#### 方式二：Windows 一键启动

双击项目根目录的 `win启动.bat` 文件。

#### 方式三：热重载（开发模式）

```bash
poetry run nb run --reload
```

### 8. 连接协议端

机器人默认监听 `http://0.0.0.0:8080`，根据适配器选择对应连接方式：

| 适配器        | 连接地址                                | 说明                    |
| ---------- | ----------------------------------- | --------------------- |
| OneBot V11 | `ws://127.0.0.1:8080/onebot/v11/ws` | 反向 WebSocket          |
| OneBot V12 | `ws://127.0.0.1:8080/onebot/v12/ws` | 反向 WebSocket          |
| QQ 官方      | 由 `QQ_BOTS` 配置决定                    | 通过 `use_websocket` 启用 |
| Minecraft  | 由 Minecraft 适配器决定                   | 需在服务端安装对应模组           |

## 项目架构

```
liuying_bot0.1.4/
├── bot.py                        # 机器人入口
├── __version__                   # 版本号文件
├── pyproject.toml                # Poetry 与 ruff 配置
├── .env                          # 环境变量配置
├── win启动.bat                   # Windows 一键启动脚本
└── liuying/                      # 主包
    ├── configs/                  # 全局配置（BotSetting、ConfigsManager）
    ├── models/                   # 全局数据库模型（按业务域分子包）
    │   ├── _bot/                 #   机器人相关（控制台/好友/消息存储/优先级等）
    │   ├── _group/               #   群组相关（配置/控制台/成员信息）
    │   ├── _llm/                 #   LLM 相关（Token 配额/用量）
    │   ├── _log/                 #   各类日志（行为/性能/调度/银行/商店等）
    │   └── _user/                #   用户相关（银行/经验/好感/媒体/签到/等级等）
    ├── services/                 # 核心服务层
    │   ├── cache/                #   统一缓存（内存/Redis，含击穿防护/批量/降级）
    │   ├── liuying_db/           #   数据库服务（连接池/会话/查询/搜索/监控）
    │   └── renderer/             #   HTML 渲染（主题/引擎/注册表/资源解析）
    ├── ui/                       # UI 构建器与模型（卡片/图表/布局/Markdown）
    ├── utils/                    # 通用工具集
    │   ├── LLM/                  #   LLM 客户端（OpenAI/智谱/Provider 路由/Web 搜索）
    │   ├── apscheduler/          #   任务调度（触发器/混合/注册/查询/告警）
    │   ├── bed_layout/           #   图床服务（本地/阿里/百度/华为/腾讯/AWS + HTTP API）
    │   ├── bot/                  #   机器人版本信息
    │   ├── http/                 #   HTTP 客户端（重试/批量/缓存/浏览器/WS/断点续传）
    │   ├── image/                #   图片工具（合成/特效/二维码/GIF/模板）
    │   ├── manager/              #   管理器集合（消息/撤回/优先级/虚拟环境/限流）
    │   ├── repo_utils/           #   仓库工具（Git/Gitee 文件管理）
    │   └── user/                 #   用户工具（金币/经验/好感/签到/UUID/媒体）
    ├── liuying_plugins/          # 主插件目录
    │   ├── AI/                   #   流萤 AI 插件（核心）
    │   ├── admin/                #   管理员帮助与子插件集合
    │   ├── auction/              #   拍卖行
    │   ├── bank/                 #   流萤银行
    │   ├── bottle/               #   漂流瓶（含 Web 审核后台）
    │   ├── fortune/              #   今日运势
    │   ├── help/                 #   帮助菜单
    │   ├── hooks/                #   事件钩子（权限/封禁/限流/统计/性能/撤回）
    │   ├── init/                 #   启动初始化（缓存/配置/插件/任务）
    │   ├── platform/             #   平台适配（QQ OneBot / QQ 官方）
    │   ├── plugin_store/         #   插件商店
    │   ├── shop/                 #   商店
    │   ├── signIn/               #   每日签到
    │   ├── statistics/           #   功能调用统计
    │   ├── superuser/            #   超级用户管理集合
    │   ├── ui_manager/           #   UI 主题与渲染管理
    │   ├── user_info/            #   用户信息
    │   ├── wife/                 #   每日 wife
    │   ├── withdraw.py           #   消息撤回
    │   └── record_request.py     #   好友/群组请求记录（隐藏）
    └── plugins/                  # 自定义插件目录
        ├── AI_webui/             #   流萤 AI WebUI 控制台
        ├── qq_bot_config/        #   QQ 机器人配置管理
        ├── qzone/                #   流萤 AI 空间工具
        ├── web_search/           #   免配置网络搜索客户端
        └── zan/                  #   自动点赞订阅赞
```

## 插件清单

### 业务插件

| 插件      | 主要指令                                                                                                          |
| ------- | ------------------------------------------------------------------------------------------------------------- |
| 流萤 AI   | `@bot [消息]`、`bot对话`、`bot人格 [名称]`、`我的画像`、`bot记忆`、`清空对话历史`、`bot说 [文本]`、`流萤AI状态`、`流萤AI开关 [功能] [on/off]`、`流萤AI体检` |
| 流萤银行    | `存款/取款 [货币] [金额]`、`银行兑换`、`转账`、`定期存款`、`贷款`、`还款`、`银行排行`、`银行记录`                                                  |
| 商店      | `商店 [商店名]`、`购买道具`、`使用道具`、`我的道具`、`开店`、`商店上架/下架/改价`、`商店热销榜`                                                     |
| 拍卖行     | `拍卖行`、`拍卖行购买/上架/下架/改价`、`拍卖行搜索/翻页`、`我的拍卖`、`拍卖行记录/比价`                                                           |
| 签到      | `签到`                                                                                                          |
| 今日运势    | `今日运势`、`刷新今日运势`（超管）                                                                                           |
| 每日 wife | `抽wife`、`查找wife [名字]`、`添加wife [名字]`（超管）                                                                       |
| 漂流瓶     | `扔瓶子/丢瓶子`、`捡瓶子`、`评论漂流瓶`、`点赞漂流瓶`、`查看漂流瓶`                                                                       |
| 用户信息    | `我的信息`                                                                                                        |
| UI 管理   | `我的主题`、`切换主题 [功能] [主题名]`、`主题商店`、`购买主题`、`ui reload`                                                            |
| 功能调用统计  | `功能调用统计`、`日/周/月功能调用统计`、`我的功能调用统计`                                                                             |
| 自动点赞订阅赞 | `点赞我`、`订阅赞`、`取消订阅赞`                                                                                           |
| 消息撤回    | `[引用消息] 撤回`                                                                                                   |

### 管理/超管插件

| 插件          | 入口指令                                           |
| ----------- | ---------------------------------------------- |
| 管理员帮助       | `管理员帮助`（含 ban、bot 权限、群管、插件开关、敏感词、金币查询等子模块）     |
| 超级用户帮助      | `超级用户帮助`（含 bot 管理、广播、数据清理、SQL 执行、群管理、请求管理等子模块） |
| 帮助菜单        | `功能 [名称]`、`详细帮助`、`功能 -s`（超管）                   |
| 插件商店        | `插件商店`、`添加插件`、`移除插件`、`搜索插件`、`更新插件`、`更新全部插件`    |
| QQ 机器人配置管理  | `qq配置添加/查询/修改/删除/导出/意图/状态`（超管）                 |
| 流萤 AI 空间工具  | `流萤AI空间 [set/clear]`、`流萤AI空间状态`                |
| 流萤 AI WebUI | 浏览器访问 `http://<bot地址>:<端口>/ai/`                |

### 服务/隐藏插件

- `hooks`：权限/封禁/限流/统计/性能/调度等事件钩子集合
- `init`：启动时初始化缓存、配置、插件、任务
- `platform`：按适配器动态加载 QQ OneBot 或 QQ 官方子插件
- `record_request`：自动记录并处理好友/群组请求（隐藏）
- `web_search`：免配置网络搜索客户端，作为正式搜索 Provider 的降级兜底

## 开发说明

### 代码规范

- 符合 PEP 8 / PEP 484，使用 Google 风格文档字符串
- 单行长度不超过 88 字符
- 已配置 `ruff` 进行代码检查与格式化
- 类型提示：函数参数、返回值、变量赋值均建议添加类型提示
- 导入规范：所有 import 必须集中在文件顶部；标准库 → 第三方库 → 项目内部模块

### 常用命令

```bash
# 代码检查
poetry run ruff check

# 代码格式化
poetry run ruff format

# 验证语法
poetry run python -m py_compile <file>

# 热重载开发
poetry run nb run --reload
```

### 添加新插件

1. 在 `liuying/liuying_plugins/` 或 `liuying/plugins/` 目录下创建新插件包
2. 编写 `__init__.py`，使用 `PluginMetadata` 声明插件元数据
3. 通过 `liuying.configs.utils.PluginExtraData` 配置插件信息、命令、配置项
4. 通过 `liuying.utils.manager.priority_manager.PriorityLifecycle` 注册启动优先级
5. 使用 `liuying.utils.message.MessageUtils.build_message(...).send(...)` 发送消息
6. 数据库模型遵循「一表一模块」原则，存放于 `liuying/models/` 对应子包

### 注册自定义 Agent 工具

```python
from liuying_plugins.AI import register_external_tool, AgentTool

class MyTool(AgentTool):
    name = "my_tool"
    description = "自定义工具示例"

    async def execute(self, **kwargs) -> str:
        return "工具执行结果"

register_external_tool(MyTool())
```

## 注意事项

- 启动前请确保 `.env` 中所有配置项已正确填写，特别是数据库连接与超级用户
- SQLite 连接默认启用 WAL 模式以避免 `database is locked` 错误
- 使用 Redis 缓存时需先安装 Redis 服务并执行 `poetry install --extras redis`
- 启用 HTML 渲染功能需先执行 `poetry run playwright install chromium` 安装浏览器
- AI 插件依赖外部 LLM Provider（OpenAI/智谱等），需在配置中填入对应 API Key
- 如流萤与协议端不在同一服务器，请将 `IMAGE_TO_BYTES` 设为 `True`
- 修改 `.env` 后需重启机器人生效
- AI 插件注册优先级为 2，确保在依赖系统（数据库/LLM/缓存）就绪后加载

## 贡献与反馈

- 仓库地址：[https://gitee.com/shiranranran/liuying-bot](https://gitee.com/shiranranran/liuying-bot)
- 如有问题或建议，请通过 [Issues](https://gitee.com/shiranranran/liuying-bot/issues) 反馈
- 项目采用 AGPL-3.0 许可证开源，欢迎参与贡献
- 提交代码前请确保通过 `poetry run ruff check` 与 `poetry run python -m py_compile` 验证

## 更新记录

### v0.1.4-b

- 重构 AI 插件为分层架构：config → models → core → agent → pipeline → handlers → jobs → tts
- 新增用户级人格隔离架构，支持每个用户独立切换当前 bot 人格
- 新增完整 4 层记忆系统（工作/情节/语义/背景）与 RRF 融合检索
- 新增 Agent 工具调用框架，支持第三方插件注册自定义工具
- 新增多模态视觉能力（图片理解/生成、视频理解）
- 新增 WebUI 控制台（`liuying/plugins/AI_webui`）
- 重构统一缓存系统（`liuying/services/cache`），支持内存/Redis 双后端
- 重构数据库服务层（`liuying/services/liuying_db`），含连接池/搜索/监控
- 新增 HTML 渲染服务（`liuying/services/renderer`），支持主题切换
- 新增 UI 构建器（`liuying/ui`）与图表系统
- 新增图床服务 `bed_layout`，支持本地/阿里/百度/华为/腾讯/AWS 多云存储
- 新增 APScheduler 任务调度封装（`liuying/utils/apscheduler`）
- 新增 HTTP 客户端工具集（`liuying/utils/http`），含重试/批量/缓存/断点续传
- 新增 QQ 机器人配置管理插件（`liuying/plugins/qq_bot_config`）
- 新增流萤 AI 空间工具插件（`liuying/plugins/qzone`）
- 新增自动点赞订阅赞插件（`liuying/plugins/zan`）
- 优化管理员与超级用户体系，聚合多个子插件
- 优化消息撤回插件，支持 QQ 官方适配器四种消息类型
- 升级至 NoneBot2 v2.5.0、SQLAlchemy 2.0.49
- 完善权限/限流/统计/性能等事件钩子集合

### v0.0.5

- 优化数据库模块，支持 SQLite、MySQL、PostgreSQL 多数据库连接

### v0.0.4

- 重置帮助的 HTML 模板

### v0.0.3

- 优化性能，修复一些 bug

### v0.0.2

- 优化了一些细节

### v0.0.1

- 初始版本，包含基础功能

