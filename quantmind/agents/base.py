from __future__ import annotations

from abc import ABC, abstractmethod

from quantmind.schemas import AgentState


class BaseAgent(ABC):
    """所有 Agent 的统一接口。"""

    name: str
    role: str

    @abstractmethod
    def run(self, state: AgentState) -> AgentState:
        """读取并更新 AgentState。"""
        raise NotImplementedError
