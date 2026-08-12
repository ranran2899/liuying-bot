计算技能实现说明

- 生产入口：`scripts/main.py` 的 `build_tools(runtime)`
- 调试入口：`scripts/main.py` 的 `run(expression)`
- 核心实现：`scripts/impl.py`

为何不用 eval：
`eval` 可通过 `__import__`、属性链等方式逃逸出算术语义。
本技能改为解析成 AST 后按节点类型白名单递归求值，
未列入白名单的节点直接抛 `CalcError`，从结构上排除代码执行。

扩展新函数：把函数加入 `impl._FUNCS` 即可，无需改动求值逻辑。
