"""
Wake-up agent — manages the conversation state for a single wake-up call.
Keeps the conversation history and decides when the user is confirmed awake.
"""
from tools.registry import TOOL_SCHEMAS


SYSTEM_PROMPT = """You are a friendly but persistent wake-up assistant.
Your job is to make sure the user is genuinely awake and ready to start their day.

Guidelines:
- Be warm and encouraging, not annoying
- Vary your messages each call so it doesn't feel robotic
- Ask them something simple to prove they're alert (what day is it, what's their plan today, etc.)
- Once you're convinced they're truly awake and coherent, call confirm_awake
- If they ask you to stop or say they'll get up, give them one more check then confirm
- Keep responses SHORT — this is a phone call, not an essay
"""


class WakeupAgent:
    def __init__(self, llm_adapter):
        self.llm = llm_adapter
        self.history: list[dict] = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]

    async def greet(self) -> str:
        """Generate the opening message for the call."""
        self.history.append({
            "role": "user",
            "content": "[Call just connected. Give a brief, energetic good morning greeting and ask if they're awake.]"
        })
        # No tools on greeting — user hasn't spoken yet, nothing to confirm
        response = await self.llm.chat(self.history, tools=None)
        self.history.append({"role": "assistant", "content": response["content"]})
        return response["content"]

    async def respond_streaming(self, user_text: str):
        """
        Streaming version of respond().
        Yields ("sentence", text) for each complete sentence as it arrives.
        Yields ("tool", tool_result) if a tool was called.
        Yields ("done", None) when complete.
        """
        import re
        import inspect
        from tools.registry import get_tool

        self.history.append({"role": "user", "content": user_text})

        buffer = ""
        full_content = ""
        tool_result = None

        async for event_type, data in self.llm.stream_chat(self.history, tools=TOOL_SCHEMAS):
            if event_type == "text":
                buffer += data
                full_content += data
                # Yield complete sentences as they form
                while True:
                    match = re.search(r'(?<=[.!?])\s+', buffer)
                    if not match:
                        break
                    sentence = buffer[:match.start() + 1].strip()
                    buffer = buffer[match.end():]
                    if sentence:
                        yield ("sentence", sentence)

            elif event_type == "tool_call":
                tool = get_tool(data["name"])
                if tool:
                    raw_args = data.get("args", {})
                    accepted = inspect.signature(tool).parameters
                    filtered_args = {k: v for k, v in raw_args.items() if k in accepted}
                    tool_result = tool(**filtered_args)

        # Yield any remaining text that didn't end with punctuation
        if buffer.strip():
            yield ("sentence", buffer.strip())

        self.history.append({"role": "assistant", "content": full_content})

        if tool_result:
            yield ("tool", tool_result)

        yield ("done", None)

    async def respond(self, user_text: str) -> tuple[str, dict | None]:
        """
        Process user speech and return (response_text, tool_result).
        tool_result is non-None when the LLM called a tool (confirm_awake / end_call).
        """
        self.history.append({"role": "user", "content": user_text})
        response = await self.llm.chat(self.history, tools=TOOL_SCHEMAS)
        self.history.append({"role": "assistant", "content": response["content"]})

        tool_result = None
        if response.get("tool_call"):
            import inspect
            from tools.registry import get_tool
            tool = get_tool(response["tool_call"]["name"])
            if tool:
                raw_args = response["tool_call"].get("args", {})
                accepted = inspect.signature(tool).parameters
                filtered_args = {k: v for k, v in raw_args.items() if k in accepted}
                tool_result = tool(**filtered_args)

        return response["content"], tool_result
