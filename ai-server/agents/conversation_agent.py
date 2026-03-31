"""
General conversation agent — free-form AI assistant over the phone.
Supports tool calling for things like reminders and calendar (add tools to
CONVERSATION_TOOL_SCHEMAS / conversation_tools registry as needed).
"""

SYSTEM_PROMPT = """You are a helpful, friendly AI assistant on a phone call with your owner.
Keep responses concise — this is a voice call, not a text chat.
One or two sentences is usually enough. Be natural and conversational.
You can help with reminders, notes, questions, and general conversation."""

# Add tool schemas here as they are built
CONVERSATION_TOOL_SCHEMAS: list[dict] = []


def _active_prompt() -> str:
    """Return stored prompt if set, otherwise the built-in default."""
    try:
        import data_store
        stored = data_store.load().get("prompts", {}).get("conversation", "")
        return stored if stored.strip() else SYSTEM_PROMPT
    except Exception:
        return SYSTEM_PROMPT


class ConversationAgent:
    def __init__(self, llm_adapter):
        self.llm = llm_adapter
        self.history: list[dict] = [
            {"role": "system", "content": _active_prompt()}
        ]

    async def greet(self) -> str:
        self.history.append({
            "role": "user",
            "content": "[Call just connected. Give a brief friendly greeting and ask how you can help.]"
        })
        response = await self.llm.chat(self.history, tools=None)
        self.history.append({"role": "assistant", "content": response["content"]})
        return response["content"]

    async def respond(self, user_text: str) -> tuple[str, dict | None]:
        self.history.append({"role": "user", "content": user_text})
        tools = CONVERSATION_TOOL_SCHEMAS or None
        response = await self.llm.chat(self.history, tools=tools)
        self.history.append({"role": "assistant", "content": response["content"]})

        tool_result = None
        if response.get("tool_call") and CONVERSATION_TOOL_SCHEMAS:
            import inspect
            from tools.registry import get_tool
            tool = get_tool(response["tool_call"]["name"])
            if tool:
                raw_args = response["tool_call"].get("args", {})
                accepted = inspect.signature(tool).parameters
                filtered_args = {k: v for k, v in raw_args.items() if k in accepted}
                tool_result = tool(**filtered_args)

        return response["content"], tool_result
