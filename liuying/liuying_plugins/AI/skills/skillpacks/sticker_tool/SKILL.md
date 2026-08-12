---
name: sticker_tool
description: 表情包主动挑选、关键词检索与库规模统计
category: expression
---

# 表情包

让模型能**主动**挑表情包，而不只依赖 pipeline 的概率触发。

## 工具

| 工具 | 用途 | 配额 |
|---|---|---|
| `select_sticker` | 按心情挑一个表情包发出去 | 每会话 2 次 |
| `search_sticker` | 按关键词查库里有什么 | 不限 |
| `sticker_stats` | 查库规模与心情分布 | 不限 |

## 安全设计

**身份不作为工具参数。** 群号与用户 ID 从 `session_context` 读取，
模型无法指定。否则模型可以传入他人群号，污染那个群的表情包冷却与偏好数据。

## 与自动触发路径的分工

| 路径 | 触发方式 | 是否受概率/冷却限制 |
|---|---|---|
| pipeline 自动配图 | `should_send()` 概率判定 | 是 |
| 本技能 `select_sticker` | 模型主动决策 | 否（`force=True`） |

模型主动调用即视为已判断该发，所以跳过概率检查；概率控制留给自动路径。
每会话 2 次配额防止模型每句话都配图。

## 检索先于断言

`search_sticker` 的存在是为了让模型回答「你有没有 XX 表情包」时**先查证**。
工具描述中显式写了「不要凭空说有或没有」——这类问题模型极易幻觉。

## 使用记录

`select_sticker` 选中后会调 `record_usage` 写使用记录，供反馈学习器
后续调整偏好权重。`search_sticker` 与 `sticker_stats` 是只读的，不写记录。
