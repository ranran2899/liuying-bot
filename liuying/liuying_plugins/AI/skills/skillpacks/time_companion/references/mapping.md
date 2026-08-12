函数映射

- `impl.date_diff(start, end, timezone)` -> 工具 `date_diff`
- `impl.days_until(target, timezone)` -> 工具 `days_until` / `run(target)`
- `impl.shift_date(base, days, timezone)` -> 工具 `shift_date`
- `impl.time_companion(timezone, mood)` -> 工具 `time_companion`
- `impl.build_time_tools(runtime)` -> `build_tools(runtime)`

暴露工具名：`date_diff`、`days_until`、`shift_date`、`time_companion`

## 意图映射

| 用户表达 | 工具 | 参数要点 |
|---|---|---|
| 「距过年还有几天」 | `days_until` | `target="2027-02-06"` |
| 「从上周一到今天多久」 | `date_diff` | 两端日期 |
| 「三天后是星期几」 | `shift_date` | `base="今天"`, `days=3` |
| 「这么晚还没睡」 | `time_companion` | `mood="tired"` |
| 「刚起床好困」 | `time_companion` | `mood="tired"` |
| 「今天心情不好」 | `time_companion` | `mood="negative"` |
| 「现在几点」 | 不用本技能，走 `get_current_time` |

## 参数陷阱

- `mood` 只接受 `positive` / `negative` / `tired` / `neutral` 四个英文值，
  传中文会被忽略（不报错，只是不附注情绪那句）
- `time_companion` 全部参数可选，不传即按默认时区当前时间
- `days` 绝对值超过 36500 会被拒绝
