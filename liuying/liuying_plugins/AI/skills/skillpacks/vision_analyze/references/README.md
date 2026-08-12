# vision_analyze 参考资料

## 依赖服务

- `core/vision.summarize_image(data, mime, llm_helper, prompt=)` → `ImageSummary(description, success, error)`
- `core/vision.summarize_gif(data, llm_helper, cache_key=)` → `GifSummary(summary, frame_count, sampled_frames, success, error)`
- `skills/media.fetch_image / fetch_images / is_gif`

`summarize_image` 内部已通过 `vision_router` 路由到支持视觉的 provider，
路由失败自动降级到默认 `llm_helper.chat`，本技能无需重复处理。

## 常量

| 常量 | 值 | 说明 |
|---|---|---|
| `_MAX_IMAGES` | 3 | 单次最多分析图片数 |
| `_ANALYZE_TIMEOUT` | 45.0 | 单张分析超时（秒） |
| `_QUESTION_LIMIT` | 200 | 问题文本截断长度 |
| `MAX_IMAGE_BYTES` | 8MB | 单图体积上限（在 `skills/media.py`） |

## 缓存

`summarize_gif` 自带 `cache_key` 级缓存。静态图不缓存——同一 URL 重复分析的
场景少，且不同 `question` 需要不同结论，缓存收益低于失效风险。
