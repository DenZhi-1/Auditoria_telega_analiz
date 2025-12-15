import os
from typing import List

class Config:
    # Telegram Bot
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    
    # Администраторы бота
    ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "1688115040").split(",") if x.strip().isdigit()]
    
    # VK API
    VK_API_VERSION = "5.199"
    VK_SERVICE_TOKEN = os.getenv("VK_SERVICE_TOKEN", "")
    REQUEST_DELAY = float(os.getenv("REQUEST_DELAY", "0.34"))
    VK_API_TIMEOUT = int(os.getenv("VK_API_TIMEOUT", "30"))
    
    # Database
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///vk_analytics.db")
    
    # AI и конкурентный анализ
    ENABLE_AI_ANALYSIS = os.getenv("ENABLE_AI_ANALYSIS", "true").lower() == "true"
    ENABLE_COMPETITOR_ANALYSIS = os.getenv("ENABLE_COMPETITOR_ANALYSIS", "true").lower() == "true"
    
    # Настройки анализа конкурентов
    MAX_COMPETITORS = int(os.getenv("MAX_COMPETITORS", "10"))
    MIN_SIMILARITY_SCORE = float(os.getenv("MIN_SIMILARITY_SCORE", "0.3"))
    
    # Настройки AI-анализа
    MIN_TEXT_LENGTH = int(os.getenv("MIN_TEXT_LENGTH", "100"))
    
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
        
        if self.MAX_COMPETITORS < 1 or self.MAX_COMPETITORS > 20:
            errors.append("MAX_COMPETITORS должен быть между 1 и 20")
        
        if self.MIN_SIMILARITY_SCORE < 0 or self.MIN_SIMILARITY_SCORE > 1:
            errors.append("MIN_SIMILARITY_SCORE должен быть между 0 и 1")
        
        if errors:
            raise ValueError("; ".join(errors))


# Создаем экземпляр конфигурации
config = Config()
