游戏资讯技能实现说明

- 生产入口：`scripts/main.py` 的 `build_tools(runtime)`
- 调试入口：`scripts/main.py` 的 `run(game)`
- 核心实现：`scripts/impl.py`

不接入具体游戏平台 API，统一走联网检索，降低配置成本。
