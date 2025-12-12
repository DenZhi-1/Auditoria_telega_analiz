import json
from datetime import datetime
from typing import Dict, List, Optional
import aiosqlite
import asyncpg
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import Column, Integer, String, JSON, DateTime, Text
import sqlalchemy

from config import config

Base = declarative_base()

class AnalysisResult(Base):
    __tablename__ = 'analyses'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, index=True)
    group_id = Column(String)
    group_name = Column(String)
    analysis_data = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)

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
        
    async def init_db(self):
        if config.DATABASE_URL.startswith('postgresql'):
            self.engine = create_async_engine(
                config.DATABASE_URL.replace('postgresql://', 'postgresql+asyncpg://'),
                echo=False
            )
        else:
            self.engine = create_async_engine(
                'sqlite+aiosqlite:///database.db',
                echo=False
            )
        
        self.async_session = sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )
        
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    
    async def save_analysis(self, user_id: int, group_id: str, group_name: str, analysis: Dict):
        async with self.async_session() as session:
            analysis_record = AnalysisResult(
                user_id=user_id,
                group_id=group_id,
                group_name=group_name,
                analysis_data=analysis
            )
            session.add(analysis_record)
            
            stats = await session.get(UserStats, user_id)
            if not stats:
                stats = UserStats(user_id=user_id)
                session.add(stats)
            
            stats.total_analyses += 1
            stats.last_activity = datetime.utcnow()
            
            await session.commit()
    
    async def get_user_stats(self, user_id: int) -> Dict:
        async with self.async_session() as session:
            stats = await session.get(UserStats, user_id)
            if not stats:
                return {'total_analyses': 0, 'saved_reports': 0}
            
            result = await session.execute(
                sqlalchemy.select(AnalysisResult)
                .where(AnalysisResult.user_id == user_id)
                .order_by(AnalysisResult.created_at.desc())
                .limit(5)
            )
            last_analyses = result.scalars().all()
            
            return {
                'total_analyses': stats.total_analyses,
                'saved_reports': stats.saved_reports,
                'last_analyses': [
                    {
                        'group_name': a.group_name,
                        'created_at': a.created_at
                    } for a in last_analyses
                ]
            }
    
    async def get_analysis_history(self, user_id: int, limit: int = 10) -> List[Dict]:
        async with self.async_session() as session:
            result = await session.execute(
                sqlalchemy.select(AnalysisResult)
                .where(AnalysisResult.user_id == user_id)
                .order_by(AnalysisResult.created_at.desc())
                .limit(limit)
            )
            analyses = result.scalars().all()
            
            return [
                {
                    'id': a.id,
                    'group_name': a.group_name,
                    'group_id': a.group_id,
                    'created_at': a.created_at,
                    'analysis': a.analysis_data
                } for a in analyses
            ]
