翻译技能实现说明

- 生产入口：`scripts/main.py` 的 `build_tools(runtime)`
- 调试入口：`scripts/main.py` 的 `run(text, target_language)`
- 核心实现：`scripts/impl.py`

设计要点：

- 温度固定 0.2，避免翻译发挥导致语义偏移
- 系统提示用编号硬约束限定输出形态，压制模型加解释的倾向
- 语言别名表 `_LANG_ALIASES` 集中维护，新增别名只改一处

扩展语言：往 `_LANG_ALIASES` 添加映射即可，无需改动调用逻辑。
