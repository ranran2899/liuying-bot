# vision_analyze 意图映射

## 触发场景

| 用户表达 | 工具 | 参数要点 |
|---|---|---|
| 「这是什么」+图 | `analyze_image` | `question` 留空 |
| 「图里写了什么」 | `analyze_image` | `question="图中的文字内容"` |
| 「这只猫什么品种」 | `analyze_image` | `question` 原样传入 |
| 「这两张图有什么区别」 | `analyze_images` | 两个 URL + `question="对比差异"` |
| 「帮我看看这几张」 | `analyze_images` | 全部 URL |

## 不该触发

| 用户表达 | 应走 |
|---|---|
| 「视觉功能能用吗」 | `vision_caller` → `vision_capability` |
| 「发个表情包」 | `sticker_tool` → `select_sticker` |
| 「这张图里的东西现在多少钱」 | `web_search` → `visual_web_search` |
| 「画一张图」 | 图片生成，非本技能 |

## 参数陷阱

- `image_url` 必须是完整可访问 URL，QQ 图床 URL 常无扩展名，格式由魔数判定，无需在 URL 上做判断
- 多图时不要循环调用 `analyze_image`，`analyze_images` 并发更快且配额消耗更低
- `question` 越具体结论越准；泛泛而问会得到泛泛描述
