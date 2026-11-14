"""
Mem0 wrapper — long-term personal memory via semantic search.
Initialised once at startup, shared across all requests.
"""
import asyncio
import logging
import os

log = logging.getLogger(__name__)

_DATA_DIR = os.environ.get("DATA_DIR", "/home/ubuntu/VoiceProject/data")

_mem0 = None


def init_mem0(api_key: str, model: str = "gemini-2.0-flash-lite"):
    global _mem0
    try:
        from mem0 import Memory  # type: ignore
        config = {
            "llm": {
                "provider": "gemini",
                "config": {"model": model, "api_key": api_key},
            },
            "embedder": {
                "provider": "gemini",
                "config": {
                    "model": "models/gemini-embedding-001",
                    "api_key": api_key,
                    "embedding_dims": 768,
                },
            },
            "vector_store": {
                "provider": "chroma",
                "config": {
                    "collection_name": "assistant",
                    "path": os.path.join(_DATA_DIR, "chroma"),
                },
            },
        }
        _mem0 = Memory.from_config(config)
        log.info("[mem0] initialised with Gemini embeddings + ChromaDB")
    except Exception as e:
        log.warning(f"[mem0] init failed — long-term memory disabled: {e}")
        _mem0 = None


def search_memory(query: str, user_id: str = "default") -> list[str]:
    if _mem0 is None:
        return []
    try:
        results = _mem0.search(query, user_id=user_id, limit=6)
        # mem0 returns a dict with a "results" key in newer versions
        items = results.get("results", results) if isinstance(results, dict) else results
        return [r.get("memory", str(r)) for r in items if r]
    except Exception as e:
        log.warning(f"[mem0] search error: {e}")
        return []


def add_to_memory(messages: list[dict], user_id: str = "default"):
    """Fire-and-forget: extract facts from this turn's messages."""
    if _mem0 is None:
        return
    try:
        _mem0.add(messages, user_id=user_id)
    except Exception as e:
        log.warning(f"[mem0] add error: {e}")


async def add_to_memory_async(messages: list[dict], user_id: str = "default"):
    """Run add_to_memory in a thread so it doesn't block the event loop."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, add_to_memory, messages, user_id)
