"""隔离运行器入口脚本

在子进程中执行，从stdin读取JSON payload，
加载技能模块并调用指定函数，将结果以JSON写入stdout。

此脚本由 skill_isolation.py 通过子进程调用，
不依赖主进程的内存状态，实现技能隔离执行。
"""

import asyncio
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any


def _load_module(
    script_path: str, sys_paths: list[str]
) -> Any:
    """加载技能模块

    参数:
        script_path: 脚本路径
        sys_paths: 额外的sys.path路径

    返回:
        Any: 模块对象
    """
    path = Path(script_path).resolve()
    if not path.is_absolute():
        raise ValueError("脚本路径必须是绝对路径")
    if not path.exists():
        raise FileNotFoundError(f"脚本不存在: {path}")
    for p in sys_paths:
        if p and Path(p).is_absolute() and p not in sys.path:
            sys.path.insert(0, p)
    module_name = f"_isolated_skill_{path.stem}_{hash(str(path))}"
    spec = importlib.util.spec_from_file_location(
        module_name, path
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载技能模块: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


async def _run_handler(
    module: Any, function_name: str, kwargs: dict[str, Any]
) -> Any:
    """执行技能函数

    参数:
        module: 技能模块
        function_name: 函数名
        kwargs: 函数参数

    返回:
        Any: 执行结果
    """
    func = getattr(module, function_name, None)
    if func is None:
        raise AttributeError(
            f"技能模块无 {function_name} 函数"
        )
    result = func(**kwargs)
    if asyncio.iscoroutine(result):
        result = await result
    return result


def main() -> int:
    """主入口

    从stdin读取payload，执行技能函数，输出JSON结果。

    返回:
        int: 退出码（0成功，1失败）
    """
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        module = _load_module(
            str(payload.get("script_path", "")),
            list(payload.get("sys_paths", [])),
        )
        result = asyncio.run(
            _run_handler(
                module,
                str(payload.get("function", "run")),
                dict(payload.get("kwargs", {})),
            )
        )
        sys.stdout.write(
            json.dumps(
                {"ok": True, "result": result},
                ensure_ascii=False,
                default=str,
            )
        )
        return 0
    except Exception as e:
        sys.stdout.write(
            json.dumps(
                {"ok": False, "error": f"{type(e).__name__}: {e}"},
                ensure_ascii=False,
            )
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
