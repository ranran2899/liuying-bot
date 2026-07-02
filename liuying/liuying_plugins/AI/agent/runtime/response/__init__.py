"""Agent角色化响应子包

基于回合规划与证据合成结果生成最终角色化回复。
"""

from .responder import PersonaResponder, PersonaResponse

__all__ = [
    "PersonaResponder",
    "PersonaResponse",
]
