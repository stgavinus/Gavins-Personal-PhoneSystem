from contextlib import asynccontextmanager

from fastapi import FastAPI

import scheduler
from routers import triggers, process, converse, web


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.start()
    yield
    scheduler.stop()


app = FastAPI(title="Voice Assistant AI Server", version="0.1.0", lifespan=lifespan)

app.include_router(triggers.router, prefix="/trigger", tags=["triggers"])
app.include_router(process.router, prefix="/api", tags=["process"])
app.include_router(converse.router, prefix="/api/converse", tags=["converse"])
app.include_router(web.router, tags=["web"])


@app.get("/health")
def health():
    return {"status": "ok"}
