---
name: datetime_tool
description: 获取当前日期时间（支持时区）
category: query
entrypoint: scripts/main.py
parameters:
  type: object
  properties:
    timezone:
      type: string
      description: 时区名，默认 Asia/Shanghai
      default: Asia/Shanghai
  required: []
---

用于需要精确当前时间的场景：算日期差、判断节假日、回答「现在几点」。

- 纯本地计算，不联网、无外部依赖，延迟可忽略
- timezone 使用 IANA 时区名（如 Asia/Shanghai、UTC）
- 非法时区名回退到默认时区

调用建议：

- 只要涉及「今天/现在/还有几天」的推理，先调用本技能拿准时间
- 不要凭上下文猜测当前日期
