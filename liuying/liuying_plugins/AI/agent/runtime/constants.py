"""Agent运行时常量定义

定义循环运行期使用的工具超时与产出标记常量。
旧三段式规划器遗留的证据类型/延迟级别/意图标签常量已随
统一 ReAct 循环与原生 function-calling 的落地一并移除。
"""

# ===== 默认值 =====
DEFAULT_TOOL_TIMEOUT = 30.0
"""默认工具超时（秒）"""

# ===== 工具产出标记 =====
IMAGE_OUTPUT_KIND = "image_url"
"""图片生成类工具的产出标记（metadata.output_kind 的值）"""
