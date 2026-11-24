import asyncio
import logging
import os
import signal

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
shutting_down = False


def _handle_sigterm(*_):
    global shutting_down
    shutting_down = True
    logger.info("SIGTERM received, draining connections...")


signal.signal(signal.SIGTERM, _handle_sigterm)


async def connect_to_db():
    global db_ready
    await asyncio.sleep(20)  # Imitation long connection to DB
    db_ready = True
    logger.info("DB connection successful")
    # To simulate a failed deployment, replace the body above with:
    # logger.error("DB connection failed!")


@app.on_event("startup")
async def on_startup():
    asyncio.create_task(connect_to_db())


@app.get("/")
def hello():
    logger.info("Request successful handled!")
    return {"ok": True, "version": 9}


@app.get("/health")
def health():
    logger.info("Call /health endpoint")
    if shutting_down:
        logger.info("Shutting down, returning 503")
        return JSONResponse(content={"status": "shutting down"}, status_code=503)
    if db_ready:
        logger.info("DB is ready!")
        return {"status": "ok"}
    logger.info("DB doesn't ready")
    return JSONResponse(content={"status": "starting"}, status_code=503)