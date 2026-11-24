import asyncio
import logging
import os

from fastapi import FastAPI
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
    global db_ready
    await asyncio.sleep(20)  # Imitation long connection to DB
    db_ready = True
    logger.info("DB connection successful")


@app.on_event("startup")
async def on_startup():
    asyncio.create_task(connect_to_db())


@app.get("/")
def hello():
    logger.info("Request successful handled!")
    return {"ok": True, "version": 2}


@app.get("/health")
def health():
    logger.info("Call /health endpoint")
    if db_ready:
        logger.info("DB is ready!")
        return {"status": "ok"}
    logger.info("DB doesn't ready")
    return {"status": "starting"}, 503