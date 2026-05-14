from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.server_api import ServerApi
from backend.config import settings

_client: AsyncIOMotorClient = None


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(settings.MONGODB_URI, server_api=ServerApi("1"))
    return _client


def get_db():
    return get_client()[settings.MONGODB_DB_NAME]


async def ping():
    await get_client().admin.command("ping")
    return True


async def close():
    global _client
    if _client:
        _client.close()
        _client = None
