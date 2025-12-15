import os
from typing import List

class Config:
    # Telegram Bot
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    
    # Администраторы бота (список ID пользователей Telegram)
    ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "1688115040").split(",") if x.strip().isdigit()]
    
    # VK API
    VK_API_VERSION = "5.199"
    VK_SERVICE_TOKEN = os.getenv("VK_SERVICE_TOKEN", "")
    REQUEST_DELAY = float(os.getenv("REQUEST_DELAY", "0.34"))  # ~3 запроса в секунду
    VK_API_TIMEOUT = int(os.getenv("VK_API_TIMEOUT", "30"))  # Таймаут в секундах
    
    # Database
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///vk_analytics.db")
    
    # Logging
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    
    def validate(self):
        """Валидация конфигурационных параметров"""
        errors = []
        
        if not self.TELEGRAM_BOT_TOKEN:
            errors.append("TELEGRAM_BOT_TOKEN не установлен")
        
        if not self.VK_SERVICE_TOKEN:
            errors.append("VK_SERVICE_TOKEN не установлен")
        
        if self.REQUEST_DELAY < 0.34:
            errors.append("REQUEST_DELAY должен быть не менее 0.34 для соблюдения лимитов VK API")
        
        if self.VK_API_TIMEOUT < 10:
            errors.append("VK_API_TIMEOUT должен быть не менее 10 секунд")
        
        if not self.ADMIN_IDS:
            errors.append("ADMIN_IDS не установлен - бот не будет иметь администраторов")
        
        if errors:
            raise ValueError("; ".join(errors))


# Создаем экземпляр конфигурации
config = Config()
