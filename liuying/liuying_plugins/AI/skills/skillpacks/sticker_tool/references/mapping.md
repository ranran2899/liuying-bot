# sticker_tool 意图映射

## 触发场景

| 用户表达 | 工具 | 参数要点 |
|---|---|---|
| 「发个表情包」 | `select_sticker` | `mood` 按当下情绪填 |
| 「来个开心的」 | `select_sticker` | `mood="开心"` |
| 想用表情强化情绪表达 | `select_sticker` | `context` 填即将发出的回复 |
| 「你有没有猫猫的表情包」 | `search_sticker` | `query="猫"` |
| 「有生气的吗」 | `search_sticker` | `query="生气"` |
| 「你有多少表情包」 | `sticker_stats` | 无参数 |
| 「你最常用什么表情」 | `sticker_stats` | 无参数 |

## 不该触发

| 用户表达 | 应走 |
|---|---|
| 「这个表情包啥意思」+图 | `vision_analyze` → `analyze_image` |
| 「画个表情包」 | 图片生成，非本技能 |
| 「把这个存进表情库」 | 表情包导入，走命令而非 Agent 工具 |

## 参数陷阱

- `mood` 必须取 `enum` 中的 18 个中文值之一，传英文或自造词会被忽略
- `select_sticker` 不接受群号/用户 ID 参数，身份自动从会话上下文取
- `search_sticker` 命中后**要如实转述**结果条数与名称，不要夸大成「有很多」
- `limit` 超过 5 会被截断到 5
