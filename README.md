

# 流萤机器人（liuying-bot）

<div align="center">

基于 [NoneBot2](https://nonebot.dev/) 构建的多功能聊天机器人项目，集成 AI 对话核心、经济系统、管理员体系与 WebUI 控制台。

[![license](https://img.shields.io/badge/license-AGPL--3.0-FE7D37)](./LICENSE)
[![Python](https://img.shields.io/badge/Python-3.14%2B-blue?logo=python&logoColor=white)](https://www.python.org)
[![NoneBot](https://img.shields.io/badge/nonebot-v2.5.0-EA5252)](https://nonebot.dev/)
[![OneBot](https://img.shields.io/badge/OneBot-v11/v12-black?style=social&logo=data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAEAAAABABAMAAABYR2ztAAAAIVBMVEUAAAAAAAADAwMHBwceHh4UFBQNDQ0ZGRkoKCgvLy8iIiLWSdWYAAAAAXRSTlMAQObYZgAAAQVJREFUSMftlM0RgjAQhV+0ATYK6i1Xb+iMd0qgBEqgBEuwBOxU2QDKsjvojQPvkJ/ZL5sXkgWrFirK4MibYUdE3OR2nEpuKz1/q8CdNxNQgthZCXYVLjyoDQftaKuniHHWRnPh2GCUetR2/9HsMAXyUT4/3UHwtQT2AggSCGKeSAsFnxBIOuAggdh3AKTL7pDuCyABcMb0aQP7aM4AnAbc/wHwA5D2wDHTTe56gIIOUA/4YYV2e1sg713PXdZJAuncdZMAGkAukU9OAn40O849+0ornPwT93rphWF0mgAbauUrEOthlX8Zu7P5A6kZyKCJy75hhw1Mgr9RAUvX7A3csGqZegEdniCx30c3agAAAABJRU5ErkJggg==)](https://onebot.dev/)
[![Code style](https://img.shields.io/badge/code%20style-ruff-000000?logo=ruff&logoColor=white)](https://github.com/astral-sh/ruff)
[![Types](https://img.shields.io/badge/types-pyright-797952.svg?logo=python&logoColor=edb641)](https://github.com/Microsoft/pyright)

</div>

> “流萤是大家的好朋友！”

本项目符合 [OneBot](https://github.com/howmanybots/onebot) 标准，可与多种协议端及平台无缝对接。

---

## 📦 功能特性

### AI 对话核心
- **多 LLM 支持**：支持 OpenAI、智谱等主流大语言模型接口。
- **Agent 工具系统**：
    - 内置技能包：天气查询、新闻速递、日期工具、计算器、翻译、游戏资讯等。
    - **MCP 桥接**：支持 MCP (Model Context Protocol) 协议扩展。
    - **隔离执行**：支持沙箱环境运行复杂或不可信工具脚本。
- **记忆系统**：
    - 四层记忆架构（工作记忆、情景记忆、语义记忆、摘要记忆）。
    - RRF 融合检索 + 向量检索。
    - 记忆固化与遗忘机制。
- **人格系统**：
    - 14 种内置人格（ Default、中二病、狂妄 CEO、元气少女、冰山总裁、冰雪女王、刘萤、无名少女、御姐、毒舌学姐、沈有厨、小荣语、病娇学妹等）。
    - 用户级人格隔离与动态切换。
    - 情感状态模拟（情绪、能量、关系亲密度）。
- **多模态**：
    - 视觉理解（VQA）。
    - TTS 语音合成。
- **知识库**：基于 FTS 与向量索引的插件/知识检索系统。
- **主动智能**：
    - 定时日记生成。
    - 群组上下文感知与主动发言。
    - 社交场景触发（早安/晚安/新闻推送等）。
- **贴纸系统**：基于情绪识别的自动贴纸反馈与学习。

### 经济系统
- **银行**：存取款、转账、外汇、贷款、定期存款。
- **商店**：道具购买、使用、背包管理。
- **拍卖行**：物品上架、购买、价格对比、历史记录。
- **黑市**：限时稀有物品刷新与购买。
- **交易**：用户间点对点交易。

### 娱乐互动
- **漂流瓶**：扔瓶子、捡瓶子、评论、点赞。
- **今日运势**：随机运势与图片生成。
- **签到**：每日签到、双倍卡、掉落道具。
- **自动点赞**：群内自动点赞互动。

### 权限管理
- **超级用户**：全权限管理。
- **平台超管**：基于平台（QQ等）的管理员。
- **群组管理**：禁言、踢人、权限下发。
- **ACL**：细粒度插件黑白名单、调用频率限制 (CD/频次)。
- **敏感词**：文本过滤与自动处理。

### 基础设施
- **数据库**：SQLite / MySQL / PostgreSQL 支持。
- **缓存**：统一缓存层（内存 / Redis）。
- **调度**：APScheduler 定时任务管理。
- **日志**：行为日志、性能监控、SQL 日志。
- **WebUI**：基于 Vue3 的 Web 控制台（仪表盘、数据库、日志、插件管理）。

---

## 🛠️ 安装与部署

### 环境要求
- **Python**: 3.14 及以上，点击 [python-3.14.7](https://www.python.org/ftp/python/3.14.7/python-3.14.7-amd64.exe) 下载安装。
- **包管理器**: uv
- **协议端**: 推荐 LLOneBot (NTQQ) 或 OneBot 兼容客户端

### 安装步骤

1. **安装 uv**
   ```bash
   pip install uv
   ```

2. **克隆项目**
   ```bash
   git clone https://gitee.com/shiranranran/liuying-bot.git
   cd liuying-bot/
   ```

3. **安装依赖**
   ```bash
   uv sync
   ```

4. **启用 Redis（可选）**
   若需使用 Redis 缓存加速，请执行：
   ```bash
   uv sync --extra redis
   ```

### 配置

在项目根目录创建或修改 `.env` 文件：

```ini
# 数据库配置（SQLite 默认为 data/db/liuying.db）
DB_URL = "sqlite+aiosqlite:///data/db/liuying.db"

# 超级用户列表
SUPERUSERS = ["123456789"]

# 机器人昵称
NICKNAME = ["流萤", "流萤酱"]

# API Key 配置示例
# OPENAI_API_KEY = "sk-..."
# ZHIPU_API_KEY = "..."
```

> 更多配置项（如 LLM Provider 配置、Redis 连接等）请参考项目根目录下的 `.env` 示例文件或代码注释。

### 启动

```bash
# 普通启动
uv run python bot.py

# 开发模式（热重载，推荐开发时使用）
uv run nb run --reload

# Windows 双击启动
win启动.bat
```

### 连接协议端

机器人默认监听 `http://0.0.0.0:8080`，请根据你的协议端配置对应的 WebSocket 连接地址：

| 适配器        | 连接地址                                |
| ---------- | ----------------------------------- |
| OneBot V11 | `ws://127.0.0.1:8080/onebot/v11/ws` |
| OneBot V12 | `ws://127.0.0.1:8080/onebot/v12/ws` |
| QQ 官方      | 由 `QQ_BOTS` 环境变量配置决定             |

---

## 📋 项目结构

```
liuying-bot/
├── bot.py                    # 程序入口
├── pyproject.toml            # 项目配置 (uv)
├── .env                      # 环境变量 (敏感配置)
├── win启动.bat               # Windows 启动脚本
└── liuying/
    ├── configs/              # 全局配置模块
    │   ├── config.py         # 核心配置类
    │   └── utils/            # 配置工具与模型
    ├── liuying_plugins/      # 主插件目录
    │   ├── AI/               # AI 对话核心
    │   │   ├── agent/        # Agent 运行时 (工具调用/MCP/隔离执行)
    │   │   ├── core/         # 核心逻辑 (LLM/记忆/情感/知识库/Pipeline)
    │   │   ├── skills/       # 技能包 (天气/翻译/搜索等)
    │   │   ├── handlers/     # 消息处理器与命令
    │   │   ├── models/       # 数据模型
    │   │   └── personas/     # 人格配置
    │   ├── admin/            # 管理员功能 (封禁/插件开关/面板)
    │   ├── economy/          # 经济系统 (银行/商店/拍卖)
    │   ├── fortune/          # 运势
    │   ├── help/             # 帮助系统
    │   ├── hooks/            # 全局钩子 (认证/日志/限流)
    │   ├── init/             # 初始化迁移
    │   ├── platform/         # 平台适配 (QQ群处理/事件)
    │   ├── signIn/           # 签到系统
    │   ├── statistics/       # 统计面板
    │   ├── superuser/        # 超级用户功能 (广播/执行SQL/插件商店)
    │   ├── user_info/        # 用户信息
    │   ├── web_ui/           # WebUI 后端 API
    │   └── ...
    ├── plugins/              # 自定义/第三方插件存放区
    ├── services/             # 核心服务 (LLM/DB/缓存/渲染)
    └── ui/                   # WebUI 前端构建
```

---

## 🧩 插件清单

### 业务插件
- **流萤 AI**：多 LLM 对话、Agent 工具调用、记忆检索、人格切换。
- **经济**：存取款、转账、贷款、银行面板。
- **商店**：商店购买、背包使用、物品管理。
- **拍卖行**：物品上架、求购、市场浏览。
- **黑市**：稀有物品刷新与交易。
- **娱乐**：
    - 漂流瓶（扔/捡/评论/举报）。
    - 今日运势（运势图片生成）。
    - 签到（每日奖励、连续签到）。
    - 自动点赞、表情包推荐。
- **实用**：用户信息查询、网页搜索。

### 管理插件
- **管理员**：封禁管理、敏感词管理、插件开关、群管工具（禁言/踢人）。
- **超级用户**：
    - 广播系统（支持多平台转发）。
    - 插件商店（在线安装/更新插件）。
    - 系统操作（重启、SQL 执行、数据清理）。
    - 好友/群组请求管理。
- **WebUI**：仪表盘统计、数据库管理、运行时配置、实时日志。

---

## 📝 开发说明

### 代码规范
- **风格**：遵循 PEP 8，使用 `ruff` 进行格式化与检查。
- **类型**：严格遵守 PEP 484，代码必须通过 `pyright` 类型检查。
- **格式**：单行代码不超过 88 字符。
- **文档**：函数需添加 Google 风格文档字符串，推荐使用中文注释。

### 常用命令

```bash
# 代码检查
uv run ruff check

# 代码格式化
uv run ruff format

# 运行机器人 (开发模式)
uv run nb run --reload
```

### 添加新插件

1. 在 `liuying/plugins/` 目录下创建新的插件包。
2. 使用 NoneBot2 的 `PluginMetadata` 声明元数据。
3. 通过 `PluginExtraData` 配置命令参数与权限。
4. 使用 `PriorityLifecycle` 注册启动顺序。

### 注册 Agent 工具

流萤支持注册自定义 Agent 工具供 AI 调用：

```python
from liuying.liuying_plugins.AI import register_external_tool, AgentTool

class MyCustomTool(AgentTool):
    name = "my_tool"
    description = "这是一个自定义工具"
    
    async def execute(self, **kwargs) -> str:
        # 工具逻辑
        return "结果"

# 注册工具
register_external_tool(MyCustomTool())
```

---

## ❔ 注意事项

> 在启动机器人前，请务必确认以下事项，以避免常见问题。

1. **环境配置**：确保 `.env` 文件配置完整，特别是 `SUPERUSERS` 和 `DB_URL`。
2. **数据库模式**：SQLite 默认开启 WAL 模式以提升并发性能。
3. **Redis 缓存**：若未安装 Redis，机器人将自动回退到内存缓存。
4. **AI 依赖**：使用 AI 功能需配置有效的大模型 API Key（如 OpenAI 或智谱）。
5. **协议端兼容性**：如果协议端与机器人不在同一服务器，需将 `IMAGE_TO_BYTES` 配置项设为 `True` 以兼容图片传输。
6. **启动顺序**：AI 插件优先级较高（Priority 20），请确保数据库、LLM 服务在 AI 插件加载前就绪。

---

## 📜 贡献指南

我们欢迎并感谢社区的贡献！请遵循以下流程参与开发：

1. **Fork** 本仓库。
2. **创建分支**：新建特性分支 (`git checkout -b feature/your-feature`)。
3. **提交更改**：遵循项目代码规范（PEP 8 / Type Hints），并添加必要的中文注释。
4. **发起 Pull Request**：详细描述你的改动内容。

---

## 🌟 特别感谢

- [NoneBot2](https://nonebot.dev/)：强大且跨平台的 Python 异步机器人框架。
- [zhenxun-bot (zhenxun\_bot)](https://github.com/zhenxun-org/zhenxun_bot)：流萤机器人的诸多设计灵感与实现完全参考均来源于zhenxun_bot。

---

## 📄 许可证

本项目基于 **AGPL-3.0** 协议开源。在使用本项目时，请严格遵守该协议的相关规定。

---

## 📞 反馈与联系

- **Gitee 仓库**：<https://gitee.com/shiranranran/liuying-bot>
- **问题反馈**：<https://gitee.com/shiranranran/liuying-bot/issues>

> 在提出问题前，建议先阅读 [提问的智慧](https://github.com/ryanhanwu/How-To-Ask-Questions-The-Smart-Way/blob/main/README-zh_CN.md)，这将有助于您获得更快的反馈。