import json
import httpx
from .base import LLMAdapter


class OllamaAdapter(LLMAdapter):
    def __init__(self, url: str, model: str):
        self.url = url.rstrip("/")
        self.model = model

    async def stream_chat(self, messages: list[dict], tools: list[dict] | None = None):
        """
        Yields ("text", token) for each streamed text token.
        Yields ("tool_call", {"name": ..., "args": ...}) if a tool is called.
        """
        payload = {"model": self.model, "messages": messages, "stream": True}
        if tools:
            payload["tools"] = tools

        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream("POST", f"{self.url}/api/chat", json=payload) as r:
                r.raise_for_status()
                async for line in r.aiter_lines():
                    if not line.strip():
                        continue
                    data = json.loads(line)
                    msg = data.get("message", {})
                    content = msg.get("content", "")
                    if content:
                        yield ("text", content)
                    if data.get("done") and msg.get("tool_calls"):
                        tc = msg["tool_calls"][0]
                        yield ("tool_call", {
                            "name": tc["function"]["name"],
                            "args": tc["function"].get("arguments", {}),
                        })

    async def chat(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        payload: dict = {
            "model": self.model,
            "messages": messages,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools

        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(f"{self.url}/api/chat", json=payload)
            r.raise_for_status()
            data = r.json()

        message = data.get("message", {})
        tool_calls = message.get("tool_calls")
        tool_call = None
        if tool_calls:
            tc = tool_calls[0]
            tool_call = {
                "name": tc["function"]["name"],
                "args": tc["function"].get("arguments", {}),
            }

        return {
            "content": message.get("content", ""),
            "tool_call": tool_call,
        }
