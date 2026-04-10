"""
BrainAgent — the personal AI assistant core.
One singleton shared across all channels (phone, Telegram, etc.).
"""
import asyncio
import logging
from adapters.llm.gemini import GeminiAdapter
from brain import mem0_client, memory
from brain.tools.registry import BRAIN_TOOL_SCHEMAS, execute_tool
from config import settings

log = logging.getLogger(__name__)

_brain: "BrainAgent | None" = None


def get_brain() -> "BrainAgent":
    global _brain
    if _brain is None:
        _brain = BrainAgent()
    return _brain


class BrainAgent:
    def __init__(self):
        self._llm = GeminiAdapter(
            api_key=settings.gemini_api_key,
            model=settings.brain_gemini_model,
        )

    def _build_system(self, memories: list[str], channel: str) -> str:
        lines = [
            "You are a personal AI assistant with a friendly, natural personality. "
            "You help with reminders, notes, calendar, and general conversation.",
        ]

        if memories:
            lines.append("\nWhat you remember about the user:")
            for m in memories:
                lines.append(f"- {m}")

        if channel == "phone":
            lines.append(
                "\nYou're on a phone call. Keep responses concise — 1 to 2 sentences. "
                "Avoid lists or formatting."
            )
        else:
            lines.append("\nRespond naturally. More detail is fine when it's helpful.")

        lines.append(
            "\nYou have tools to create and search notes. "
            "Use create_note when the user asks you to note or record something. "
            "Use search_notes when they ask about something they previously asked you to record."
        )


        return "\n".join(lines)

    async def chat(
        self,
        text: str,
        session_id: str,
        channel: str = "phone",
        user_id: str = "default",
    ) -> tuple[str, str]:
        """
        Process one turn. Returns (response_text, action).
        action is always "continue" for now; "end_call" reserved for future use.
        """
        # Special case: phone call connected — generate a greeting
        if text == "[call_connected]":
            text = "Please greet me warmly and ask how you can help. Keep it to one sentence."

        # 1. Search long-term memory for context
        memories = await asyncio.get_event_loop().run_in_executor(
            None, mem0_client.search_memory, text, user_id
        )
        if memories:
            log.info(f"[brain] {len(memories)} memories injected")

        # 2. Load recent session history
        history = memory.get_recent_messages(session_id, limit=12)

        # 3. Build message list for this turn
        system_text = self._build_system(memories, channel)
        turn_messages = [{"role": "system", "content": system_text}]
        turn_messages.extend(history)
        turn_messages.append({"role": "user", "content": text})

        # 4. Persist user message (skip synthetic greet prompt)
        if not text.startswith("Please greet me warmly"):
            memory.add_message(session_id, "user", text)

        # 5. Tool-calling loop (max 5 iterations)
        response_text = ""
        for _ in range(5):
            try:
                result = await self._llm.chat(turn_messages, tools=BRAIN_TOOL_SCHEMAS)
            except Exception as e:
                log.error(f"[brain] LLM error: {e}")
                response_text = "Sorry, I'm having trouble reaching my AI service right now. Please try again in a moment."
                break

            tool_call = result.get("tool_call")
            content = result.get("content", "")

            if tool_call:
                # Execute the tool
                tool_name = tool_call["name"]
                tool_args = tool_call.get("args", {})
                log.info(f"[brain] tool call: {tool_name}({tool_args})")
                tool_result = execute_tool(tool_name, tool_args)

                # Append the tool exchange to in-memory messages only
                turn_messages.append({
                    "role": "assistant",
                    "content": content,
                    "tool_call": tool_call,
                })
                turn_messages.append({
                    "role": "tool",
                    "name": tool_name,
                    "content": tool_result,
                })
                continue

            # No tool call — this is the final response
            response_text = content
            break

        if not response_text:
            response_text = "I'm not sure how to help with that. Could you rephrase?"

        # 6. Persist assistant response
        memory.add_message(session_id, "assistant", response_text)

        # 7. Feed this turn to Mem0 in the background (non-blocking)
        mem0_messages = [
            {"role": "user", "content": text},
            {"role": "assistant", "content": response_text},
        ]
        asyncio.create_task(mem0_client.add_to_memory_async(mem0_messages, user_id))

        return response_text, "continue"
