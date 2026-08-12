日期推算与时段陪伴技能实现说明

- 生产入口：`scripts/main.py` 的 `build_tools(runtime)`（返回 4 个工具）
- 调试入口：`scripts/main.py` 的 `run(target)`
- 核心实现：`scripts/impl.py`
- 时段规则：`scripts/rhythm.py`

设计要点：

- 日期解析集中在 `parse_date`，三个日期工具共用，新增格式只改一处
- 缺省年份走「就近未来」策略，匹配用户问倒计时的真实意图
- 非法时区、非法日期均转为可读提示，不抛异常打断 Agent 循环
- 时段规则表 `rhythm._PHASES` 按 `[起始, 结束)` 小时区间覆盖 0-24 全域，
  `resolve_phase` 对越界小时取模后归入深夜，不会返回 None

`rhythm.py` 对外只暴露 `resolve_phase`、`advise`、`PHASE_NAMES` 三项，
调整时段划分或措辞只改这一个文件，`impl.py` 无需变动。

这是「一个技能包注册多个相关工具」的标准范本。
