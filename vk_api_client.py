import aiohttp
import asyncio
import logging
from typing import Dict, List, Optional
from urllib.parse import urlparse
import re

from config import config

logger = logging.getLogger(__name__)

class VKAPIClient:
    def __init__(self):
        self.base_url = "https://api.vk.com/method/"
        self.session = None
        self.request_delay = config.REQUEST_DELAY
        
    async def _get_session(self):
        if not self.session:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def _make_request(self, method: str, params: Dict) -> Optional[Dict]:
        """Универсальный метод для запросов к VK API"""
        try:
            session = await self._get_session()
            params.update({
                'access_token': config.VK_SERVICE_TOKEN,
                'v': config.VK_API_VERSION
            })
            
            async with session.get(f"{self.base_url}{method}", params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    if 'error' in data:
                        logger.error(f"VK API error: {data['error']}")
                        return None
                    return data.get('response')
                else:
                    logger.error(f"HTTP error: {response.status}")
                    return None
                    
        except Exception as e:
            logger.error(f"Request error: {e}")
            return None
        finally:
            # Соблюдаем ограничение VK API (3 запроса в секунду)
            await asyncio.sleep(self.request_delay)
    
    def _extract_group_id(self, group_link: str) -> Optional[str]:
        """Извлекает ID или короткое имя группы из ссылки"""
        patterns = [
            r'vk\.com/(?:club|public)(\d+)',
            r'vk\.com/([a-zA-Z0-9_]+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, group_link)
            if match:
                return match.group(1)
        return None
    
    async def get_group_info(self, group_link: str) -> Optional[Dict]:
        """Получает основную информацию о группе"""
        group_id = self._extract_group_id(group_link)
        if not group_id:
            return None
            
        params = {
            'group_id': group_id,
            'fields': 'members_count,description,activity,status'
        }
        
        response = await self._make_request('groups.getById', params)
        if response and isinstance(response, list) and len(response) > 0:
            group = response[0]
            return {
                'id': group.get('id'),
                'name': group.get('name'),
                'screen_name': group.get('screen_name'),
                'members_count': group.get('members_count', 0),
                'description': group.get('description', ''),
                'activity': group.get('activity', '')
            }
        return None
    
    async def get_group_members(self, group_id: str, limit: int = 1000) -> List[Dict]:
        """Получает участников группы с их профилями"""
        members = []
        offset = 0
        count = 1000  # Максимум за запрос
        
        while len(members) < limit:
            params = {
                'group_id': group_id,
                'offset': offset,
                'count': min(count, limit - len(members)),
                'fields': 'sex,bdate,city,country,interests,activities,books,music,movies,games'
            }
            
            response = await self._make_request('groups.getMembers', params)
            if not response:
                break
                
            users = response.get('items', [])
            if not users:
                break
                
            members.extend(users)
            offset += len(users)
            
            if len(users) < count or len(members) >= limit:
                break
        
        return members
    
    async def close(self):
        """Корректно закрывает сессию"""
        if self.session:
            await self.session.close()

# Глобальный экземпляр для использования в боте
vk_client = VKAPIClient()
