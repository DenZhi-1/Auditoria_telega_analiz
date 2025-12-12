import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Telegram
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    ADMIN_IDS = [int(id.strip()) for id in os.getenv("ADMIN_IDS", "").split(",") if id.strip()]
    
    # VK API
    VK_SERVICE_TOKEN = os.getenv("VK_SERVICE_TOKEN")
    VK_API_VERSION = "5.199"
    
    # Database
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///database.db")
    
    # Redis
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    
    # Limits
    MAX_MEMBERS_PER_GROUP = 10000
    REQUEST_DELAY = 0.34  # ~3 запроса в секунду (ограничение VK)

config = Config()
