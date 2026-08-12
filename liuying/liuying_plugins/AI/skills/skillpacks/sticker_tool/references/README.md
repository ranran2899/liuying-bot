# sticker_tool 参考资料

## 依赖服务

- `core/sticker.sticker_curation.choose_for_reply(text, persona_mood, mood_hint, group_id, user_id, is_private, force)` → `StickerItem | None`
- `core/sticker.sticker_curation.record_usage(sticker_id, context_text, detected_mood, group_id, user_id)`
- `core/sticker.sticker_library.search_by_text(query, limit)` → `list[StickerItem]`
- `core/sticker.sticker_library.get_stats()` → `LibraryStats`
- `agent/runtime/session_context.get_current_group_id / get_current_user_id`

## StickerItem 关键字段

`id`、`name`、`file_path`、`description`、`mood_tags`、`semantic_tags`、
`usage_count`、`positive_count`、`negative_count`、`is_disabled`

心情标签用 `item.get_mood_tags()` 取（字段内是序列化字符串，不要直接读 `mood_tags`）。

## LibraryStats 字段

`total`、`active`、`disabled`、`by_mood`（dict）、`by_source`（dict）、`total_usage`

## StickerMood 全部取值（18 种）

开心、难过、生气、惊讶、害怕、厌恶、期待、平静、得意、无奈、
害羞、疑惑、撒娇、嘲讽、心疼、想念、鼓励、困倦

这 18 个值由 `_MOOD_VALUES` 自动展开为 `select_sticker` 的 `mood` 参数 `enum`，
新增心情标签时无需改本技能代码。

## 常量

| 常量 | 值 | 说明 |
|---|---|---|
| `_SEARCH_LIMIT` | 5 | 检索返回上限 |
| `_TOP_MOODS` | 5 | 统计中展示的心情分布条数 |
