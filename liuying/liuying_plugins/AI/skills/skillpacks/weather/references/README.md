天气技能实现说明

- 生产入口：`scripts/main.py` 的 `build_tools(runtime)`
- 调试入口：`scripts/main.py` 的 `run(city)`
- 核心实现：`scripts/impl.py`

设计取舍：不接入具体天气 API，改用联网检索聚合，
避免为单一技能引入额外密钥配置与配额管理。
