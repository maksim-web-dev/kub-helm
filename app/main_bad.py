import asyncio
import logging
import os

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
logger.addHandler(handler)

app = FastAPI()

Instrumentator().instrument(app).expose(app)

POD_NAME = os.getenv("POD_NAME", "unknown")
db_ready = False


async def connect_to_db():
    # BUG: db_ready never set to True — health check always returns 503
    logger.error("DB connection failed!")


@app.on_event("startup")
async def on_startup():
    asyncio.create_task(connect_to_db())


@app.get("/")
def hello():
    return {"ok": True, "version": "v3-bad"}


@app.get("/health")
def health():
    if db_ready:
        return {"status": "ok"}
    return JSONResponse(content={"status": "starting"}, status_code=503)