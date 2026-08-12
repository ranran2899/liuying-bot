# web_search 参考资料

## 依赖服务

- `core/vision.summarize_image(data, mime, llm_helper, prompt=)` → `ImageSummary`
- `llm_helper.web_search(query, count=)` → `list[dict]`
- `skills/media.fetch_images`

检索结果条目字段：`title`、`url` 或 `link`、`snippet` 或 `content`。
字段名不统一是引擎差异导致的，格式化时两种都要兜。

## 常量

| 常量 | 值 | 说明 |
|---|---|---|
| `_MAX_IMAGES` | 2 | 参与线索抽取的图片数上限 |
| `_RESULT_COUNT` | 5 | 检索结果条数 |
| `_SNIPPET_LIMIT` | 200 | 单条摘要截断长度 |
| `_CLUE_LIMIT` | 60 | 单张图线索截断长度 |
| `_TOTAL_TIMEOUT` | 40.0 | 抽取加检索总超时（秒） |

## 线索抽取提示词要点

- 只输出关键词，空格分隔，不超过 6 词
- 优先输出图中明确文字、商品名、作品名、地标
- **认不出具体名称时输出空字符串**——这条很重要，否则视觉模型会
  用「一只猫 动物 可爱」这类泛词污染查询，检索结果全是噪声

## 去重逻辑

`build_query` 按小写词做去重，避免线索里重复出现原查询已有的词。
中文不分词，靠空格切分——视觉模型输出的中文关键词本身以空格分隔，够用。
