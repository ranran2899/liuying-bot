---
name: news
description: 查询最新新闻，支持分类general/tech/finance/sports/entertainment/world
category: query
entrypoint: scripts/main.py
parameters:
  type: object
  properties:
    category:
      type: string
      description: 新闻分类，默认general
      default: general
  required: []
---

用于用户想知道「最近发生了什么」「有什么新闻」时的时事检索。

- category 取值：general / tech / finance / sports / entertainment / world
- 依赖 `runtime.llm_helper.web_search` 联网聚合
- 返回条目化摘要，条数受技能内部上限约束

调用建议：

- 用户未指明领域时使用默认 general，不要臆测分类
- 需要针对具体事件深挖时改用 `web_search`，而非重复调用本技能
