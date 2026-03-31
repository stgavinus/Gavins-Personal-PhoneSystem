import json
import httpx
from .base import LLMAdapter


class GroqAdapter(LLMAdapter):
    def __init__(self, api_key: str, model: str = "llama-3.3-70b-versatile"):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://api.groq.com/openai/v1/chat/completions"

    async def chat(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        payload: dict = {"model": self.model, "messages": messages}
        if tools:
            payload["tools"] = tools

        headers = {"Authorization": f"Bearer {self.api_key}"}

        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(self.base_url, json=payload, headers=headers)
            r.raise_for_status()
            data = r.json()

        message = data["choices"][0]["message"]
        tool_call = None
        if message.get("tool_calls"):
            tc = message["tool_calls"][0]
            args = tc["function"].get("arguments", "{}")
            tool_call = {
                "name": tc["function"]["name"],
                "args": json.loads(args) if isinstance(args, str) else args,
            }

        return {
            "content": message.get("content") or "",
            "tool_call": tool_call,
        }
