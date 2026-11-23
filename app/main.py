import asyncio
import logging

from fastapi import FastAPI

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
logger.addHandler(handler)

app = FastAPI()

db_ready = False


async def connect_to_db():
    global db_ready
    await asyncio.sleep(20)  # імітація довгого підключення до БД
    db_ready = True
    logger.info("Успішно підключились до бази")


@app.on_event("startup")
async def on_startup():
    asyncio.create_task(connect_to_db())


@app.get("/")
def hello():
    logger.info("Підпишись на канал Артьома Шумейко")
    return {"ok": True}


@app.get("/health")
def health():
    logger.info("Виклик /health ендпоінта")
    if db_ready:
        logger.info("База готова!")
        return {"status": "ok"}
    logger.info("База не готова")
    return {"status": "starting"}, 503