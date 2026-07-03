# 流萤机器人（liuying-bot）

基于 NoneBot2 v2.5.0 构建的多适配器聊天机器人项目，集成完整的 AI 对话核心、经济系统、管理员体系与 WebUI 控制台。

- 当前版本：`v0.1.4-b`（开发版）
- 框架：NoneBot2 `>=2.5.0,<2.6.0`
- 数据库：SQLAlchemy `2.0.49`（支持 SQLite / MySQL / PostgreSQL）
- 包管理：Poetry（`package-mode = false`）
- Python：`>=3.11`
- 许可证：AGPL-3.0

## 功能特性

- **AI 对话**：多 LLM Provider、Agent 工具调用、四层记忆系统、用户级人格隔离、多模态视觉、TTS、WebUI 控制台
- **经济系统**：银行存取/兑换/转账/贷款、商店、拍卖行、签到、每日 wife
- **娱乐互动**：漂流瓶、今日运势、自动点赞、表情包与贴纸
- **权限管理**：超级用户、平台超管、群组管理员、用户级 ACL
- **平台适配**：OneBot V11/V12、QQ 官方、Minecraft 适配器
- **基础设施**：多数据库（SQLite/MySQL/PostgreSQL）、统一缓存（内存/Redis）、HTML 渲染、图床、APScheduler 调度、行为/性能/调度/银行日志

## 安装与启动

### 1. 安装 Poetry

```bash
pip install poetry
```

### 2. 克隆项目

```bash
git clone https://gitee.com/shiranranran/liuying-bot.git
cd liuying-bot/
```

### 3. 安装依赖

默认使用阿里云 PyPI 镜像（见 `pyproject.toml` 中 `aliyun` 源）。

```bash
# 基础安装
poetry install

# 启用 Redis 缓存 （可以跳过）
poetry install --extras redis
```

### 4. 配置 `.env` 文件

项目根目录的 `.env` 文件已包含完整示例与中文注释，按需修改关键项即可。

```ini
# SQLite（推荐一键启动）
DB_URL = "sqlite+aiosqlite:///data/db/liuying.db"

# 超级用户
SUPERUSERS = ["123456789"]

# 机器人昵称
NICKNAME = ["流萤", "流萤酱"]
```

数据库、Redis、QQ 机器人、OneBot 访问令牌等其余配置参考 `.env` 内注释。

### 5. 启动机器人

```bash
poetry run python bot.py
```

Windows 可直接双击项目根目录的 `win启动.bat`。开发模式支持热重载：

```bash
poetry run nb run --reload
```

### 6. 连接协议端

机器人默认监听 `http://0.0.0.0:8080`，根据适配器选择对应连接方式：

| 适配器        | 连接地址                                | 说明                    |
| ---------- | ----------------------------------- | --------------------- |
| OneBot V11 | `ws://127.0.0.1:8080/onebot/v11/ws` | 反向 WebSocket          |
| OneBot V12 | `ws://127.0.0.1:8080/onebot/v12/ws` | 反向 WebSocket          |
| QQ 官方      | 由 `QQ_BOTS` 配置决定                    | 通过 `use_websocket` 启用 |
| Minecraft  | 由 Minecraft 适配器决定                   | 需在服务端安装对应模组           |

### 可选配置

- **Redis**：启用 Redis 缓存前需执行 `poetry install --extras redis`
- **Playwright 浏览器**：项目首次使用 HTML 渲染功能时会自动检测并安装 Chromium，无需手动操作

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

流萤 AI、流萤银行、商店、拍卖行、签到、今日运势、每日 wife、漂流瓶、用户信息、UI 管理、统计、自动点赞、消息撤回。

### 管理插件

管理员帮助、超级用户帮助、帮助菜单、插件商店、QQ 配置、流萤 AI 空间、流萤 AI WebUI。

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

1. 在  `liuying/plugins/` 创建包
2. 用 `PluginMetadata` 声明元数据
3. 通过 `PluginExtraData` 配置命令，通过 `PriorityLifecycle` 注册启动优先级
4. 占位
5. 占位2

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
- AI 插件依赖外部 LLM Provider，需配置 API Key
- 协议端与机器人不同服务器时，将 `IMAGE_TO_BYTES` 设为 `True`
- AI 插件优先级为 2，需在数据库/LLM/缓存就绪后加载

## 贡献与反馈

- 仓库：[gitee.com/shiranranran/liuying-bot](https://gitee.com/shiranranran/liuying-bot)
- 反馈：[Issues](https://gitee.com/shiranranran/liuying-bot/issues)

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

### v0.0.3 \~ v0.0.1

- 性能优化、细节调整、初始版本

