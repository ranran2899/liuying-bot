---
name: game_info
description: 查询游戏信息（攻略/介绍）
category: query
entrypoint: scripts/main.py
parameters:
  type: object
  properties:
    game:
      type: string
      description: 游戏名
  required:
    - game
---

用于用户询问某款游戏的玩法、玩家评价、上线情况、攻略要点。

- 依赖 `runtime.llm_helper.web_search` 聚合游戏站点结果
- 返回介绍与攻略要点的混合摘要

调用建议：

- game 传游戏正式名或广为人知的简称
- 需要具体版本更新公告时改用 `web_search` 并带上版本号
