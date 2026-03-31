from fastapi import FastAPI
from routers import triggers, process

app = FastAPI(title="Voice Assistant AI Server", version="0.1.0")

app.include_router(triggers.router, prefix="/trigger", tags=["triggers"])
app.include_router(process.router, prefix="/api", tags=["process"])


@app.get("/health")
def health():
    return {"status": "ok"}
