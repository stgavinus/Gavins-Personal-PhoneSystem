from contextlib import asynccontextmanager

from fastapi import FastAPI

import scheduler
from brain import memory, mem0_client
from brain.agent import get_brain
from config import settings
from routers import triggers, process, converse, chat


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialise SQLite tables
    memory.init_db()
    # Initialise Mem0 long-term memory
    mem0_client.init_mem0(api_key=settings.gemini_api_key, model=settings.brain_gemini_model)
    # Warm up the brain singleton
    get_brain()
    # Start wake-up scheduler
    scheduler.start()
    yield
    scheduler.stop()


app = FastAPI(title="Voice Assistant AI Server", version="0.1.0", lifespan=lifespan)

app.include_router(triggers.router, prefix="/trigger", tags=["triggers"])
app.include_router(process.router, prefix="/api", tags=["process"])
app.include_router(converse.router, prefix="/api/converse", tags=["converse"])
app.include_router(chat.router, prefix="/chat", tags=["chat"])
# app.include_router(web.router, tags=["web"])  # re-enable when UI is ready


@app.get("/health")
def health():
    return {"status": "ok"}
