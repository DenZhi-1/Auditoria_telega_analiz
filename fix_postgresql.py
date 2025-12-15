import asyncio
import asyncpg
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def fix_postgresql_structure():
    """Исправляет структуру PostgreSQL базы данных"""
    
    # Получаем DATABASE_URL из переменных окружения
    DATABASE_URL = os.getenv("DATABASE_URL")
    
    if not DATABASE_URL:
        logger.error("❌ DATABASE_URL не найден в переменных окружения")
        return
    
    print(f"Подключаемся к PostgreSQL: {DATABASE_URL[:50]}...")
    
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        
        # 1. Проверяем существование таблицы analyses
        table_exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'analyses'
            )
        """)
        
        if not table_exists:
            print("Таблица 'analyses' не существует. Создаем...")
            await conn.execute("""
                CREATE TABLE analyses (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    group_id VARCHAR(255) NOT NULL,
                    group_name VARCHAR(255) NOT NULL,
                    analysis_data JSONB NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            print("✅ Таблица 'analyses' создана")
        else:
            print("✅ Таблица 'analyses' существует")
            
            # Проверяем тип столбца group_id
            column_info = await conn.fetchrow("""
                SELECT column_name, data_type, character_maximum_length
                FROM information_schema.columns 
                WHERE table_name = 'analyses' AND column_name = 'group_id'
            """)
            
            if column_info:
                current_type = column_info['data_type']
                print(f"Текущий тип group_id: {current_type}")
                
                if current_type == 'integer':
                    print("⚠️  Обнаружен неправильный тип INTEGER для group_id")
                    print("Исправляем на VARCHAR...")
                    
                    # Создаем временную таблицу
                    await conn.execute("""
                        CREATE TABLE analyses_new (
                            id SERIAL PRIMARY KEY,
                            user_id INTEGER NOT NULL,
                            group_id VARCHAR(255) NOT NULL,
                            group_name VARCHAR(255) NOT NULL,
                            analysis_data JSONB NOT NULL,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
                    
                    # Копируем данные с преобразованием типа
                    await conn.execute("""
                        INSERT INTO analyses_new (id, user_id, group_id, group_name, analysis_data, created_at)
                        SELECT 
                            id, 
                            user_id, 
                            group_id::VARCHAR, 
                            group_name, 
                            analysis_data, 
                            created_at
                        FROM analyses
                    """)
                    
                    # Удаляем старую таблицу
                    await conn.execute("DROP TABLE analyses CASCADE")
                    
                    # Переименовываем новую таблицу
                    await conn.execute("ALTER TABLE analyses_new RENAME TO analyses")
                    
                    print("✅ Тип столбца group_id исправлен на VARCHAR")
                else:
                    print(f"✅ Тип group_id уже правильный: {current_type}")
            else:
                print("❌ Столбец group_id не найден в таблице analyses")
        
        # 2. Проверяем таблицу user_stats
        user_stats_exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'user_stats'
            )
        """)
        
        if not user_stats_exists:
            print("Создаем таблицу user_stats...")
            await conn.execute("""
                CREATE TABLE user_stats (
                    user_id INTEGER PRIMARY KEY,
                    total_analyses INTEGER DEFAULT 0,
                    saved_reports INTEGER DEFAULT 0,
                    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            print("✅ Таблица user_stats создана")
        
        # 3. Создаем индексы
        print("Создаем индексы...")
        
        # Проверяем существование индексов
        indexes = await conn.fetch("""
            SELECT indexname, indexdef 
            FROM pg_indexes 
            WHERE tablename = 'analyses'
        """)
        
        if not any('idx_analyses_user_id' in idx['indexname'] for idx in indexes):
            await conn.execute("CREATE INDEX idx_analyses_user_id ON analyses(user_id)")
            print("✅ Создан индекс idx_analyses_user_id")
        
        if not any('idx_analyses_group_id' in idx['indexname'] for idx in indexes):
            await conn.execute("CREATE INDEX idx_analyses_group_id ON analyses(group_id)")
            print("✅ Создан индекс idx_analyses_group_id")
        
        if not any('idx_analyses_created_at' in idx['indexname'] for idx in indexes):
            await conn.execute("CREATE INDEX idx_analyses_created_at ON analyses(created_at)")
            print("✅ Создан индекс idx_analyses_created_at")
        
        print("\n🎯 Структура базы данных успешно проверена и исправлена!")
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if 'conn' in locals():
            await conn.close()

if __name__ == "__main__":
    asyncio.run(fix_postgresql_structure())
