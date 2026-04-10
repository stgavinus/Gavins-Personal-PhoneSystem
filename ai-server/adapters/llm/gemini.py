import json
import httpx
from .base import LLMAdapter


class GeminiAdapter(LLMAdapter):
    def __init__(self, api_key: str, model: str = "gemini-2.0-flash"):
        self.api_key = api_key
        self.model = model
        self.base_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def _convert_messages(self, messages: list[dict]) -> tuple[str, list[dict]]:
        """Convert OpenAI-style messages to Gemini format. Returns (system, contents)."""
        system = ""
        contents = []
        for msg in messages:
            role = msg["role"]
            content = msg.get("content") or ""
            if role == "system":
                system = content
            elif role == "user":
                contents.append({"role": "user", "parts": [{"text": content}]})
            elif role == "assistant":
                tc = msg.get("tool_call")
                if tc:
                    fc_part: dict = {"functionCall": {"name": tc["name"], "args": tc.get("args", {})}}
                    if tc.get("_thought_signature"):
                        fc_part["thoughtSignature"] = tc["_thought_signature"]
                    contents.append({"role": "model", "parts": [fc_part]})
                else:
                    contents.append({"role": "model", "parts": [{"text": content}]})
            elif role == "tool":
                contents.append({
                    "role": "user",
                    "parts": [{"functionResponse": {
                        "name": msg.get("name", ""),
                        "response": {"result": content},
                    }}],
                })
        return system, contents

    def _convert_tools(self, tools: list[dict]) -> list[dict]:
        """Convert OpenAI-style tool schemas to Gemini format."""
        declarations = []
        for tool in tools:
            fn = tool["function"]
            declarations.append({
                "name": fn["name"],
                "description": fn.get("description", ""),
                "parameters": fn.get("parameters", {"type": "object", "properties": {}}),
            })
        return [{"function_declarations": declarations}]

    async def chat(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        system, contents = self._convert_messages(messages)

        payload: dict = {"contents": contents}
        if system:
            payload["system_instruction"] = {"parts": [{"text": system}]}
        if tools:
            payload["tools"] = self._convert_tools(tools)

        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(
                self.base_url,
                params={"key": self.api_key},
                json=payload,
            )
            if not r.is_success:
                raise httpx.HTTPStatusError(
                    f"{r.status_code} {r.text[:500]}",
                    request=r.request,
                    response=r,
                )
            data = r.json()

        candidate = data["candidates"][0]["content"]
        text = ""
        tool_call = None

        for part in candidate.get("parts", []):
            if "text" in part:
                text += part["text"]
            elif "functionCall" in part:
                fc = part["functionCall"]
                tool_call = {
                    "name": fc["name"],
                    "args": fc.get("args", {}),
                }
                # Thinking models include a thoughtSignature that must be
                # preserved and echoed back in multi-turn function call history.
                if "thoughtSignature" in part:
                    tool_call["_thought_signature"] = part["thoughtSignature"]

        return {"content": text.strip(), "tool_call": tool_call}
