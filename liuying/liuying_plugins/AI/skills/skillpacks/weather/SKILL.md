---
name: weather
description: 查询指定城市的天气预报
category: query
entrypoint: scripts/main.py
parameters:
  type: object
  properties:
    city:
      type: string
      description: 城市名
  required:
    - city
---

用于用户询问天气、气温、是否下雨、出门要不要带伞等场景。

- 传入 city 后经联网检索聚合天气结果
- 依赖 `runtime.llm_helper.web_search`，未配置时返回不可用提示
- 返回可直接朗读的简短文本，不含 Markdown 表格

调用建议：

- 城市名保持中文简称（如「杭州」而非「浙江省杭州市」）
- 同一轮对话中不要对同一城市重复调用
