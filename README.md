# NoneBot 机器人项目

这是一个基于 NoneBot 2.4.3 的机器人项目，集成了 OneBot V11 适配器和 QQ 适配器。


## 功能特性

- 集成了 OneBot V11 适配器和 QQ 适配器
- 使用 fastapi + httpx + websockets 作为驱动器
- 包含基础的命令响应功能
- 提供HTML渲染和图片生成工具
- 使用 Poetry 进行依赖管理

## 安装与运行

1. 确保已安装 Python 3.11+ 环境和 Poetry

2. 安装依赖
   ```bash
   poetry install
   ```
 
3. 修改 `.env` 文件中的配置
   - 替换 `QQ_BOTS` 中的机器人信息
   - 根据需要调整其他配置项

4. 运行机器人
   ```bash
   poetry run python bot.py
   ```

## 使用说明

- 机器人默认监听端口 8080
- ws://127.0.0.1:8080/onebot/v11/ws 为 OneBot V11 适配器的 WebSocket 地址
- ws://127.0.0.1:8080/onebot/v12/ws 为 OneBot V12 适配器的 WebSocket 地址

## Poetry 基本命令

- 安装依赖: `poetry install`
- 添加新依赖: `poetry add package_name`
- 移除依赖: `poetry remove package_name`
- 更新依赖: `poetry update`
- 查看当前环境: `poetry env info`
- 运行命令: `poetry run command`
- 命令前缀为 `/`
- 内置命令：
  - `/echo [内容]` - 重复你发送的内容
  - `/hello` - 机器人向你问好
  - `/ping` - 机器人回复 pong


## 注意事项

- 实际使用前请确保在 `.env` 文件中配置了正确的机器人信息
- 如需添加新功能，请在 `plugins` 目录下创建新的插件文件
- 开发过程中可以使用 `nb run --reload` 命令实现热重载


## 贡献与反馈

- 如有问题或建议，请通过 Issues 反馈
- 项目采用 AGPL-3.0 许可证开源，欢迎参与贡献

## 更新记录

### v0.0.5
- 优化了数据库模块，支持sqlite、mysql、postgresql多数据库连接

### v0.0.4
- 重置了帮助的html模板

### v0.0.3
- 优化性能，修复一些 bug

### v0.0.2
- 优化了一些细节

### v0.0.1
- 初始版本，包含基础功能
