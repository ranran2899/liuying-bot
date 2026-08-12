---
name: vision_analyze
description: 图片与动图内容分析，支持单图问答与多图并发对比
category: vision
---

# 图像分析

看图说话。把 `core/vision` 的图片/GIF 摘要能力暴露成 Agent 工具。

## 工具

| 工具 | 用途 | 配额 |
|---|---|---|
| `analyze_image` | 单张图片描述或按问题作答 | 每会话 4 次 |
| `analyze_images` | 一次并发分析多张图（最多 3 张） | 每会话 2 次 |

## 行为

- **格式分流**：按魔数（非URL扩展名）识别格式，GIF 走 `summarize_gif` 采样关键帧，静态图走 `summarize_image`
- **并发**：`analyze_images` 下载与分析都并发，把 N 轮网络往返压成 1 轮
- **体积保护**：单图超过 8MB 直接拒绝，不消耗视觉模型配额
- **提示词约束**：`question` 截断至 200 字符，提示词明确要求「看不出来就说看不出来」以抑制幻觉

## 边界

- 视觉 provider 可用性诊断 → `vision_caller`
- 表情包挑选 → `sticker_tool`
- 带图检索 → `web_search` 的 `visual_web_search`

本技能不做这三件事，避免重复实现。

## 失败降级

下载失败、超时、视觉模型异常均返回可读中文提示，不抛异常打断 Agent 回合。
`analyze_images` 中单张失败只影响该张的结果行。
