from abc import ABC, abstractmethod


class LLMAdapter(ABC):
    @abstractmethod
    async def chat(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        """
        Send messages to the LLM and return a response dict with:
          - content: str  (the text response)
          - tool_call: dict | None  (tool name + args if the LLM called one)
        """
