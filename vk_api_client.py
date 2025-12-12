import aiohttp
import asyncio
import logging
from typing import Dict, List, Optional, Any, Union
import re

from config import config

logger = logging.getLogger(__name__)

class VKAPIClient:
    def __init__(self):
        self.base_url = "https://api.vk.com/method/"
        self.session = None
        self.request_counter = 0
        
    async def _get_session(self):
        if not self.session or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=30)
            self.session = aiohttp.ClientSession(timeout=timeout)
        return self.session
    
    def _extract_group_id(self, group_link: str) -> Optional[str]:
        if not group_link:
            return None
            
        group_link = group_link.strip()
        
        patterns = [
            r'(?:https?://)?(?:www\.)?(?:m\.)?vk\.com/(?:club|public|event)(\d+)',
            r'(?:https?://)?(?:www\.)?(?:m\.)?vk\.com/([a-zA-Z0-9_.]+[a-zA-Z0-9_])',
            r'@([a-zA-Z0-9_.]+[a-zA-Z0-9_])'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, group_link, re.IGNORECASE)
            if match:
                return match.group(1)
        
        if re.match(r'^[a-zA-Z0-9_.]+$', group_link):
            return group_link
            
        return None
    
    async def _make_request(self, method: str, params: Dict) -> Optional[Union[Dict, List]]:
        self.request_counter += 1
        request_id = self.request_counter
        
        try:
            session = await self._get_session()
            
            request_params = params.copy()
            request_params.update({
                'access_token': config.VK_SERVICE_TOKEN,
                'v': config.VK_API_VERSION,
                'lang': 'ru'
            })
            
            if config.DEBUG:
                safe_params = {k: v for k, v in request_params.items() if k != 'access_token'}
                logger.debug(f"[Request #{request_id}] {method}: {safe_params}")
            
            async with session.get(
                f"{self.base_url}{method}", 
                params=request_params,
                headers={'User-Agent': 'VKAnalyzerBot/1.0'}
            ) as response:
                
                if response.status != 200:
                    logger.error(f"[Request #{request_id}] HTTP {response.status}")
                    return None
                
                data = await response.json()
                
                if config.DEBUG:
                    logger.debug(f"[Request #{request_id}] Response: {data}")
                
                if 'error' in data:
                    error = data['error']
                    error_code = error.get('error_code', 'unknown')
                    error_msg = error.get('error_msg', 'Нет описания')
                    
                    logger.error(f"[Request #{request_id}] VK API error {error_code}: {error_msg}")
                    
                    if error_code == 5:
                        logger.critical("❌ НЕВЕРНЫЙ ТОКЕН VK!")
                    elif error_code == 15:
                        logger.warning("Группа недоступна")
                    elif error_code == 18:
                        logger.warning("Группа удалена")
                    elif error_code == 100:
                        logger.warning("Неверный ID группы")
                    
                    return None
                
                return data.get('response')
                
        except aiohttp.ClientError as e:
            logger.error(f"[Request #{request_id}] Network error: {e}")
            return None
        except asyncio.TimeoutError:
            logger.error(f"[Request #{request_id}] Timeout")
            return None
        except Exception as e:
            logger.error(f"[Request #{request_id}] Unexpected: {e}", exc_info=True)
            return None
        finally:
            await asyncio.sleep(config.REQUEST_DELAY)
    
    async def get_group_info(self, group_link: str) -> Optional[Dict[str, Any]]:
        logger.info(f"Getting group info: {group_link}")
        
        group_id = self._extract_group_id(group_link)
        if not group_id:
            logger.error(f"Invalid link format: {group_link}")
            return None
        
        params = {
            'group_id': group_id,
            'fields': 'members_count,description,activity,status,is_closed,type'
        }
        
        response = await self._make_request('groups.getById', params)
        
        if response is None:
            logger.error(f"No response for group {group_id}")
            return None
        
        if isinstance(response, list):
            if len(response) == 0:
                logger.error(f"Empty list for group {group_id}")
                return None
            group_data = response[0]
        elif isinstance(response, dict):
            group_data = response
        else:
            logger.error(f"Unknown response format: {type(response)}")
            return None
        
        if 'id' not in group_data or 'name' not in group_data:
            logger.error(f"Missing required fields: {group_data}")
            return None
        
        return {
            'id': group_data.get('id'),
            'name': group_data.get('name'),
            'screen_name': group_data.get('screen_name', group_id),
            'members_count': group_data.get('members_count', 0),
            'description': group_data.get('description', ''),
            'activity': group_data.get('activity', ''),
            'status': group_data.get('status', ''),
            'is_closed': group_data.get('is_closed', 1),
            'type': group_data.get('type', 'group')
        }
    
    async def get_group_members(self, group_id: str, limit: int = 1000) -> List[Dict[str, Any]]:
        logger.info(f"Getting members for group {group_id}, limit: {limit}")
        
        members = []
        offset = 0
        batch_size = 1000
        
        group_info = await self.get_group_info(f"vk.com/{group_id}")
        if not group_info:
            logger.error(f"No info for group {group_id}")
            return []
        
        if group_info.get('is_closed', 1) != 0:
            logger.warning(f"Group {group_id} is closed/private")
            return []
        
        total_members = group_info.get('members_count', 0)
        if total_members == 0:
            logger.warning(f"No members in group {group_id}")
            return []
        
        limit = min(limit, total_members, 10000)
        
        while len(members) < limit:
            current_batch = min(batch_size, limit - len(members))
            
            params = {
                'group_id': group_id,
                'offset': offset,
                'count': current_batch,
                'fields': 'sex,bdate,city,country,interests,activities,books,music,movies,games'
            }
            
            response = await self._make_request('groups.getMembers', params)
            
            if not response:
                logger.warning(f"Empty response at offset {offset}")
                break
            
            items = []
            if isinstance(response, dict):
                items = response.get('items', [])
            elif isinstance(response, list):
                items = response
            
            if not items:
                break
            
            members.extend(items)
            offset += len(items)
            
            if len(items) < current_batch or len(members) >= limit:
                break
        
        logger.info(f"Retrieved {len(members)} members")
        return members
    
    async def test_connection(self) -> Dict[str, Any]:
        logger.info("Testing VK API connection...")
        
        response = await self._make_request('users.get', {'user_ids': '1'})
        
        if response is None:
            return {
                'success': False,
                'message': 'Нет ответа от VK API',
                'details': 'Проверьте токен и интернет'
            }
        
        if isinstance(response, list) and len(response) > 0:
            user = response[0]
            return {
                'success': True,
                'message': f'✅ Подключение успешно! Токен работает.',
                'user_info': user
            }
        else:
            return {
                'success': False,
                'message': 'Неожиданный ответ от VK API',
                'response': response
            }
    
    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()
            logger.info("VK API session closed")

vk_client = VKAPIClient()
