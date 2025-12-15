import logging
import json
from datetime import datetime
from typing import Dict, List, Optional, Any
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import Column, Integer, String, JSON, DateTime, select, text
import sqlalchemy

from config import config

logger = logging.getLogger(__name__)
Base = declarative_base()

class AnalysisResult(Base):
    __tablename__ = 'analyses'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, index=True)
    group_id = Column(String, index=True)  # Используем String для VK ID
    group_name = Column(String)
    analysis_data = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<AnalysisResult(user_id={self.user_id}, group_id={self.group_id})>"

class UserStats(Base):
    __tablename__ = 'user_stats'
    
    user_id = Column(Integer, primary_key=True)
    total_analyses = Column(Integer, default=0)
    saved_reports = Column(Integer, default=0)
    last_activity = Column(DateTime, default=datetime.utcnow)

class Database:
    def __init__(self):
        self.engine = None
        self.async_session = None
    
    def _normalize_db_url(self, db_url: str) -> str:
        """Нормализация URL базы данных для SQLAlchemy"""
        if not db_url:
            logger.warning("DATABASE_URL пустой, используется SQLite")
            return "sqlite+aiosqlite:///database.db"
        
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)
            logger.info("Конвертирован postgres:// в postgresql+asyncpg://")
        elif db_url.startswith("postgresql://"):
            db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        
        if "localhost" in db_url or "127.0.0.1" in db_url or "::1" in db_url:
            logger.warning(f"Обнаружен localhost в DATABASE_URL, используется SQLite")
            return "sqlite+aiosqlite:///database.db"
        
        return db_url
    
    async def init_db(self) -> bool:
        """Инициализация базы данных"""
        try:
            db_url = self._normalize_db_url(config.DATABASE_URL)
            logger.info(f"Инициализация БД с URL: {db_url[:50]}...")
            
            self.engine = create_async_engine(
                db_url,
                echo=False,
                pool_size=10,
                max_overflow=20,
                pool_pre_ping=True,
                connect_args={"server_settings": {"jit": "off"}} if "postgresql" in db_url else {}
            )
            
            self.async_session = sessionmaker(
                self.engine,
                class_=AsyncSession,
                expire_on_commit=False
            )
            
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            
            # Проверяем соединение
            async with self.async_session() as session:
                await session.execute(select(1))
            
            logger.info("✅ База данных успешно инициализирована")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации базы данных: {e}")
            
            # Fallback на SQLite
            try:
                logger.info("Создается in-memory SQLite база")
                self.engine = create_async_engine(
                    "sqlite+aiosqlite:///:memory:",
                    echo=False
                )
                self.async_session = sessionmaker(
                    self.engine,
                    class_=AsyncSession,
                    expire_on_commit=False
                )
                
                async with self.engine.begin() as conn:
                    await conn.run_sync(Base.metadata.create_all)
                
                logger.info("✅ In-memory SQLite база создана")
                return True
            except Exception as sqlite_error:
                logger.error(f"❌ Ошибка создания SQLite базы: {sqlite_error}")
                return False
    
    async def save_analysis(self, user_id: int, group_id: int, 
                           group_name: str, analysis: Dict[str, Any]) -> bool:
        """
        Сохраняет результат анализа в базу данных
        
        Args:
            user_id: ID пользователя Telegram
            group_id: ID группы ВК (может быть int или str)
            group_name: Название группы
            analysis: Данные анализа
            
        Returns:
            bool: Успешно ли сохранено
        """
        try:
            async with self.async_session() as session:
                # Явно преобразуем group_id в строку для PostgreSQL
                group_id_str = str(group_id)
                
                analysis_record = AnalysisResult(
                    user_id=user_id,
                    group_id=group_id_str,  # Всегда строка
                    group_name=group_name[:255],  # Ограничиваем длину
                    analysis_data=analysis,
                    created_at=datetime.utcnow()
                )
                session.add(analysis_record)
                
                # Обновляем статистику пользователя
                stats = await session.get(UserStats, user_id)
                if not stats:
                    stats = UserStats(user_id=user_id)
                    session.add(stats)
                
                stats.total_analyses += 1
                stats.last_activity = datetime.utcnow()
                
                await session.commit()
                logger.info(f"✅ Анализ сохранен: user_id={user_id}, group_id={group_id_str}")
                return True
                
        except sqlalchemy.exc.IntegrityError as e:
            logger.error(f"❌ Ошибка целостности данных при сохранении анализа: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения анализа: {e}", exc_info=True)
            return False
    
    async def save_analysis_with_fallback(self, user_id: int, group_id: int, 
                                         group_name: str, analysis: Dict[str, Any]) -> bool:
        """
        Сохраняет анализ с обработкой ошибок типов данных для PostgreSQL
        """
        try:
            async with self.async_session() as session:
                # Используем сырой SQL для явного указания типов
                group_id_str = str(group_id)
                
                # Формируем запрос с явным приведением типов
                query = text("""
                    INSERT INTO analyses (user_id, group_id, group_name, analysis_data, created_at)
                    VALUES (:user_id, :group_id, :group_name, :analysis_data, :created_at)
                    RETURNING id
                """)
                
                result = await session.execute(query, {
                    'user_id': user_id,
                    'group_id': group_id_str,  # Строка
                    'group_name': group_name[:255],
                    'analysis_data': json.dumps(analysis, ensure_ascii=False),
                    'created_at': datetime.utcnow()
                })
                
                # Обновляем статистику
                stats_query = text("""
                    INSERT INTO user_stats (user_id, total_analyses, last_activity)
                    VALUES (:user_id, 1, :now)
                    ON CONFLICT (user_id) DO UPDATE SET
                    total_analyses = user_stats.total_analyses + 1,
                    last_activity = :now
                """)
                
                await session.execute(stats_query, {
                    'user_id': user_id,
                    'now': datetime.utcnow()
                })
                
                await session.commit()
                logger.info(f"✅ Анализ сохранен (raw SQL): user_id={user_id}, group_id={group_id_str}")
                return True
                
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения анализа (raw SQL): {e}", exc_info=True)
            
            # Пробуем сохранить без статистики
            try:
                async with self.async_session() as session:
                    query = text("""
                        INSERT INTO analyses (user_id, group_id, group_name, analysis_data, created_at)
                        VALUES (:user_id, :group_id, :group_name, :analysis_data, :created_at)
                    """)
                    
                    await session.execute(query, {
                        'user_id': user_id,
                        'group_id': str(group_id),
                        'group_name': group_name[:255],
                        'analysis_data': json.dumps(analysis, ensure_ascii=False),
                        'created_at': datetime.utcnow()
                    })
                    
                    await session.commit()
                    logger.info(f"✅ Анализ сохранен (упрощенный): user_id={user_id}")
                    return True
            except Exception as e2:
                logger.error(f"❌ Критическая ошибка сохранения: {e2}")
                return False
    
    async def get_user_stats(self, user_id: int) -> Dict[str, Any]:
        """Получает статистику пользователя"""
        try:
            async with self.async_session() as session:
                stats = await session.get(UserStats, user_id)
                
                if not stats:
                    return {
                        'total_analyses': 0,
                        'saved_reports': 0,
                        'last_analyses': []
                    }
                
                # Получаем последние анализы
                query = select(AnalysisResult).where(
                    AnalysisResult.user_id == user_id
                ).order_by(
                    AnalysisResult.created_at.desc()
                ).limit(5)
                
                result = await session.execute(query)
                last_analyses = result.scalars().all()
                
                return {
                    'total_analyses': stats.total_analyses,
                    'saved_reports': stats.saved_reports,
                    'last_analyses': [
                        {
                            'group_name': a.group_name,
                            'created_at': a.created_at.strftime('%d.%m.%Y %H:%M'),
                            'group_id': a.group_id
                        } for a in last_analyses
                    ]
                }
                
        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики: {e}")
            return {
                'total_analyses': 0,
                'saved_reports': 0,
                'last_analyses': []
            }
    
    async def get_analyses_count(self, user_id: int) -> int:
        """Получает количество анализов пользователя"""
        try:
            async with self.async_session() as session:
                query = select(sqlalchemy.func.count(AnalysisResult.id)).where(
                    AnalysisResult.user_id == user_id
                )
                result = await session.execute(query)
                return result.scalar() or 0
        except Exception as e:
            logger.error(f"Ошибка получения количества анализов: {e}")
            return 0
    
    async def get_recent_analyses(self, user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Получает последние анализы пользователя"""
        try:
            async with self.async_session() as session:
                query = select(AnalysisResult).where(
                    AnalysisResult.user_id == user_id
                ).order_by(
                    AnalysisResult.created_at.desc()
                ).limit(limit)
                
                result = await session.execute(query)
                analyses = result.scalars().all()
                
                return [
                    {
                        'id': a.id,
                        'group_id': a.group_id,
                        'group_name': a.group_name,
                        'created_at': a.created_at,
                        'has_data': bool(a.analysis_data)
                    } for a in analyses
                ]
        except Exception as e:
            logger.error(f"Ошибка получения последних анализов: {e}")
            return []
    
    async def get_analysis_by_id(self, analysis_id: int) -> Optional[AnalysisResult]:
        """Получает анализ по ID"""
        try:
            async with self.async_session() as session:
                query = select(AnalysisResult).where(AnalysisResult.id == analysis_id)
                result = await session.execute(query)
                return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Ошибка получения анализа по ID: {e}")
            return None
    
    async def check_db_health(self) -> Dict[str, Any]:
        """Проверяет здоровье базы данных"""
        try:
            async with self.async_session() as session:
                # Проверяем подключение
                await session.execute(select(1))
                
                # Получаем статистику таблиц
                analyses_count = await self.get_total_analyses_count()
                users_count = await self.get_total_users_count()
                
                return {
                    'status': 'healthy',
                    'analyses_count': analyses_count,
                    'users_count': users_count,
                    'timestamp': datetime.utcnow().isoformat()
                }
        except Exception as e:
            logger.error(f"Ошибка проверки здоровья БД: {e}")
            return {
                'status': 'unhealthy',
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }
    
    async def get_total_analyses_count(self) -> int:
        """Получает общее количество анализов"""
        try:
            async with self.async_session() as session:
                query = select(sqlalchemy.func.count(AnalysisResult.id))
                result = await session.execute(query)
                return result.scalar() or 0
        except Exception as e:
            logger.error(f"Ошибка получения общего количества анализов: {e}")
            return 0
    
    async def get_total_users_count(self) -> int:
        """Получает количество уникальных пользователей"""
        try:
            async with self.async_session() as session:
                query = select(sqlalchemy.func.count(sqlalchemy.distinct(AnalysisResult.user_id)))
                result = await session.execute(query)
                return result.scalar() or 0
        except Exception as e:
            logger.error(f"Ошибка получения количества пользователей: {e}")
            return 0
    
    async def cleanup_old_data(self, days: int = 30) -> int:
        """Очищает старые данные"""
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            async with self.async_session() as session:
                # Удаляем старые анализы
                delete_query = text("""
                    DELETE FROM analyses 
                    WHERE created_at < :cutoff_date
                """)
                
                result = await session.execute(delete_query, {'cutoff_date': cutoff_date})
                deleted_count = result.rowcount
                
                if deleted_count > 0:
                    logger.info(f"Удалено {deleted_count} старых анализов")
                
                await session.commit()
                return deleted_count
        except Exception as e:
            logger.error(f"Ошибка очистки старых данных: {e}")
            return 0
    
    async def close(self):
        """Закрывает соединения с базой данных"""
        try:
            if self.engine:
                await self.engine.dispose()
                logger.info("✅ Соединения с базой данных закрыты")
        except Exception as e:
            logger.error(f"Ошибка при закрытии соединений с БД: {e}")

# Создаем глобальный экземпляр
db = Database()
