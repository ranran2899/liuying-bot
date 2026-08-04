<div align="center">

# 流萤机器人（liuying-bot）

基于 NoneBot2 构建的多功能聊天机器人项目，集成 AI 对话核心、经济系统、管理员体系与 WebUI 控制台。

[![license](https://img.shields.io/badge/license-AGPL--3.0-FE7D37)](./LICENSE)
[![python](https://img.shields.io/badge/Python-3.11%2B-blue)](https://www.python.org/)
[![nonebot](https://img.shields.io/badge/nonebot-v2.5.0-EA5252)](https://nonebot.dev/)
[![onebot](https://img.shields.io/badge/OneBot-v11%2Fv12-black)](https://onebot.dev/)
[![QQ](https://img.shields.io/badge/QQ-Bot-lightgrey)](https://bot.q.qq.com/wiki/)
[![ruff](https://img.shields.io/badge/code%20style-ruff-000000)](https://github.com/astral-sh/ruff)

</div>

> “流萤是大家的好朋友！”

本项目符合 [OneBot](https://github.com/howmanybots/onebot) 标准，可基于以下项目与机器人框架/平台进行交互。

| 项目地址 | 平台 | 备注 |
| --- | --- | --- |
| [LLOneBot](https://github.com/LLOneBot/LLOneBot) | NTQQ | 可用 |
| [Napcat](https://github.com/NapNeko/NapCatQQ) | NTQQ | 可用 |
| [Lagrange.Core](https://github.com/LagrangeDev/Lagrange.Core) | NTQQ | 可用 |
| [QQ 官方适配器](https://github.com/nonebot/adapter-qq) | QQ 官方 | 内置支持 |
| [Minecraft 适配器](https://github.com/nonebot/adapter-minecraft) | Minecraft | 内置支持 |

---

## 📦 功能特性

### AI 对话

- 多 LLM Provider 支持
- Agent 工具调用
- 四层记忆系统（RRF 融合）
- 用户级人格隔离
- 多模态视觉理解
- TTS 语音合成
- WebUI 控制台

### 经济系统

- 银行：存取款、兑换、转账、贷款、定期存款
- 商店系统
- 拍卖行
- 典当行
- 黑市
- 签到与每日 wife

### 娱乐互动

- 漂流瓶
- 今日运势
- 自动点赞
- 表情包与贴纸

### 权限管理

- 超级用户
- 平台超管
- 群组管理员
- 用户级 ACL

### 基础设施

- 多数据库支持（SQLite / MySQL / PostgreSQL）
- 统一缓存（内存 / Redis）
- HTML 渲染
- 图床
- APScheduler 调度
- 行为 / 性能 / 调度 / 银行日志

---

## 🛠️ 安装与部署

### 环境要求

- Python >= 3.11
- uv 包管理器

### 安装步骤

```bash
# 1. 安装 uv
pip install uv

# 2. 克隆项目
git clone https://gitee.com/shiranranran/liuying-bot.git
cd liuying-bot/

# 3. 安装依赖（默认使用阿里云 PyPI 镜像）
uv sync

# 4. 启用 Redis 缓存（可选）
uv sync --extra redis
```

### 配置

在项目根目录创建或修改 `.env` 文件：

```ini
# 数据库配置（SQLite 推荐）
DB_URL = "sqlite+aiosqlite:///data/db/liuying.db"

# 超级用户
SUPERUSERS = ["123456789"]

# 机器人昵称
NICKNAME = ["流萤", "流萤酱"]
```

> 更多配置项请参考 `.env` 文件中的详细注释。

### 启动

```bash
# 普通启动
uv run python bot.py

# 开发模式（热重载）
uv run nb run --reload

# Windows 双击启动
win启动.bat
```

### 连接协议端

机器人默认监听 `http://0.0.0.0:8080`，根据适配器选择对应连接方式：

| 适配器 | 连接地址 |
| --- | --- |
| OneBot V11 | `ws://127.0.0.1:8080/onebot/v11/ws` |
| OneBot V12 | `ws://127.0.0.1:8080/onebot/v12/ws` |
| QQ 官方 | 由 `QQ_BOTS` 配置决定 |

---

## 📋 项目结构

```
liuying-bot/
├── bot.py                    # 入口文件
├── pyproject.toml            # uv 配置
├── .env                      # 环境变量配置
└── liuying/
    ├── configs/              # 全局配置
    ├── models/               # 数据库模型
    │   ├── _bot/ _economy/ _group/ _llm/ _log/ _user/
    ├── services/             # 核心服务
    │   ├── cache/            # 统一缓存
    │   ├── liuying_db/       # 数据库服务
    │   └── renderer/         # HTML 渲染
    ├── ui/                   # UI 构建器
    ├── utils/                # 通用工具
    ├── liuying_plugins/      # 主插件目录
    │   ├── AI/ admin/ bottle/ economy/
    │   ├── fortune/ help/ hooks/ init/
    │   ├── platform/ signIn/ statistics/
    │   ├── superuser/ ui_manager/
    │   ├── user_info/ wife/ withdraw.py
    └── plugins/              # 自定义插件
```

---

## 🧩 插件清单

### 业务插件

- 流萤 AI（多 LLM 对话）
- 银行系统
- 商店、拍卖行、典当行、黑市
- 签到、今日运势、每日 wife
- 漂流瓶、用户信息
- UI 管理、统计、自动点赞
- 消息撤回

### 管理插件

- 管理员帮助、超级用户帮助
- 帮助菜单
- 插件商店
- QQ 配置
- AI 空间、AI WebUI

---

## 📝 开发说明

### 代码规范

- PEP 8 / PEP 484
- Google 风格文档字符串
- 单行 ≤ 88 字符
- 函数 / 参数 / 返回值添加类型提示
- 中文注释与对话

### 常用命令

```bash
uv run ruff check
uv run ruff format
uv run nb run --reload
```

### 添加新插件

1. 在 `liuying/plugins/` 创建插件包
2. 使用 `PluginMetadata` 声明元数据
3. 通过 `PluginExtraData` 配置命令
4. 使用 `PriorityLifecycle` 注册启动优先级

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

---

## ❔ 注意事项

> Tip
>
> 启动前请确认以下事项，避免常见问题。

- 启动前确认 `.env` 配置完整
- SQLite 默认启用 WAL 模式
- Redis 需先执行 `uv sync --extra redis`
- AI 插件依赖外部 LLM Provider，需配置 API Key
- 协议端与机器人不同服务器时，将 `IMAGE_TO_BYTES` 设为 `True`
- AI 插件优先级为 2，需在数据库 / LLM / 缓存就绪后加载

---

## 📜 贡献指南

欢迎参与项目贡献，请遵循以下流程：

1. Fork 本仓库
2. 创建特性分支（`git checkout -b feature/your-feature`）
3. 提交更改（遵循 PEP 8 与项目代码规范）
4. 发起 Pull Request

---

## 🌟 特别感谢

- [NoneBot2](https://nonebot.dev/)：跨平台 Python 异步机器人框架
- [OneBot](https://github.com/howmanybots/onebot)：超棒的机器人协议
- [nonebot-plugin-alconna](https://github.com/noneplugin/nonebot-plugin-alconna)：命令解析插件
- [nonebot-plugin-uninfo](https://github.com/NoneStudio/nonebot-plugin-uninfo)：会话信息插件

---

## 📄 许可证

本项目基于 [AGPL-3.0](./LICENSE) 协议开源。

---

## 📞 反馈与联系

- 仓库地址：https://gitee.com/shiranranran/liuying-bot
- 问题反馈：https://gitee.com/shiranranran/liuying-bot/issues

> 发起 issue 前，希望您能了解 [提问的智慧](https://github.com/ryanhanwu/How-To-Ask-Questions-The-Smart-Way/blob/main/README-zh_CN.md)。
