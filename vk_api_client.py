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
        
    async def _get_session(self) -> aiohttp.ClientSession:
        """Создание сессии с таймаутами для Railway"""
        if not self.session or self.session.closed:
            timeout = aiohttp.ClientTimeout(
                total=60,
                connect=30,
                sock_read=30
            )
            connector = aiohttp.TCPConnector(
                limit=100,
                force_close=True,
                enable_cleanup_closed=True
            )
            self.session = aiohttp.ClientSession(
                timeout=timeout,
                connector=connector,
                headers={
                    'User-Agent': 'VKAnalyzerBot/1.0 (Railway)',
                    'Accept': 'application/json',
                    'Accept-Encoding': 'gzip, deflate'
                }
            )
        return self.session
    
    def _extract_group_id(self, group_link: str) -> Optional[str]:
        """Извлекает ID или короткое имя группы из ссылки"""
        if not group_link:
            return None
            
        group_link = group_link.strip().lower()
        
        patterns = [
            # Для числовых ID: club123456, public123456
            r'(?:https?://)?(?:www\.)?(?:m\.)?vk\.com/(?:club|public|event)(\d+)',
            # Для коротких имен: vk.com/groupname
            r'(?:https?://)?(?:www\.)?(?:m\.)?vk\.com/([a-zA-Z0-9_][a-zA-Z0-9_.-]*)',
            # Для упоминаний: @groupname
            r'@([a-zA-Z0-9_][a-zA-Z0-9_.-]*)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, group_link, re.IGNORECASE)
            if match:
                extracted = match.group(1)
                logger.debug(f"Извлечен ID: {extracted} из {group_link}")
                return extracted
        
        # Если это уже ID или короткое имя
        if re.match(r'^[a-zA-Z0-9_.-]+$', group_link):
            return group_link
            
        logger.warning(f"Не удалось извлечь ID из {group_link}")
        return None
    
    async def _make_request(self, method: str, params: Dict) -> Optional[Union[Dict, List]]:
        """Безопасный запрос к VK API"""
        self.request_counter += 1
        request_id = self.request_counter
        
        try:
            session = await self._get_session()
            
            # Подготавливаем параметры
            request_params = params.copy()
            request_params.update({
                'access_token': config.VK_SERVICE_TOKEN,
                'v': config.VK_API_VERSION,
                'lang': 'ru'
            })
            
            # Логируем без токена
            safe_params = {k: v for k, v in request_params.items() if k != 'access_token'}
            logger.debug(f"[Req #{request_id}] {method} params: {safe_params}")
            
            async with session.get(
                f"{self.base_url}{method}", 
                params=request_params
            ) as response:
                
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"[Req #{request_id}] HTTP {response.status}: {error_text[:200]}")
                    return None
                
                data = await response.json()
                
                # Проверяем ошибки VK API
                if 'error' in data:
                    error = data['error']
                    error_code = error.get('error_code', 'unknown')
                    error_msg = error.get('error_msg', 'No message')
                    
                    logger.error(f"[Req #{request_id}] VK API error {error_code}: {error_msg}")
                    
                    if error_code == 100:
                        # Детальный лог для ошибки параметров
                        logger.error(f"[Req #{request_id}] Invalid params details: {safe_params}")
                    
                    return None
                
                # Возвращаем успешный ответ
                return data.get('response')
                
        except asyncio.TimeoutError:
            logger.error(f"[Req #{request_id}] Timeout")
            return None
        except aiohttp.ClientError as e:
            logger.error(f"[Req #{request_id}] Network error: {e}")
            return None
        except Exception as e:
            logger.error(f"[Req #{request_id}] Unexpected error: {e}", exc_info=True)
            return None
        finally:
            # Соблюдаем лимиты VK API
            await asyncio.sleep(config.REQUEST_DELAY)
    
    async def get_group_info(self, group_link: str) -> Optional[Dict[str, Any]]:
        """Получает информацию о группе с поддержкой всех форматов"""
        logger.info(f"Запрос информации о группе: {group_link}")
        
        group_identifier = self._extract_group_id(group_link)
        if not group_identifier:
            logger.error(f"Не удалось извлечь ID из ссылки: {group_link}")
            return None
        
        logger.info(f"Извлечен идентификатор: {group_identifier}")
        
        # Для коротких имен (screen_name) используем специальную обработку
        if group_identifier.isdigit():
            # Это числовой ID
            params = {
                'group_id': group_identifier,
                'fields': 'members_count,description,activity,status,is_closed,type'
            }
        else:
            # Это короткое имя (screen_name)
            params = {
                'group_ids': group_identifier,  # Используем group_ids для screen_name
                'fields': 'members_count,description,activity,status,is_closed,type'
            }
        
        response = await self._make_request('groups.getById', params)
        
        if response is None:
            logger.error(f"Нет ответа от VK API для {group_identifier}")
            return None
        
        # Обработка ответа для разных форматов
        group_data = None
        
        if isinstance(response, list):
            if len(response) > 0:
                group_data = response[0]
            else:
                logger.error(f"Пустой список в ответе для {group_identifier}")
                return None
        elif isinstance(response, dict):
            # Иногда VK возвращает {'count': X, 'items': [...]}
            if 'items' in response:
                items = response.get('items', [])
                if items:
                    group_data = items[0]
            else:
                group_data = response
        
        if not group_data or 'id' not in group_data or 'name' not in group_data:
            logger.error(f"Неполные данные группы {group_identifier}: {group_data}")
            return None
        
        # VK возвращает отрицательные ID для групп
        group_id_value = group_data.get('id')
        if isinstance(group_id_value, int) and group_id_value < 0:
            group_id_value = abs(group_id_value)
        
        result = {
            'id': str(group_id_value),
            'name': group_data.get('name', ''),
            'screen_name': group_data.get('screen_name', group_identifier),
            'members_count': group_data.get('members_count', 0),
            'description': group_data.get('description', ''),
            'activity': group_data.get('activity', ''),
            'status': group_data.get('status', ''),
            'is_closed': group_data.get('is_closed', 1),
            'type': group_data.get('type', 'group')
        }
        
        logger.info(f"✅ Получена информация о группе: {result['name']} (ID: {result['id']}), участников: {result['members_count']}")
        return result
    
    async def get_group_members(self, group_id: str, limit: int = 500) -> List[Dict[str, Any]]:
        """Получает участников группы"""
        logger.info(f"Запрос участников группы {group_id}, лимит: {limit}")
        
        # Преобразуем в строку и проверяем, что это числовой ID
        group_id_str = str(group_id)
        if not group_id_str.lstrip('-').isdigit():
            logger.error(f"Group ID должен быть числом для метода getMembers: {group_id_str}")
            return []
        
        # Берем абсолютное значение
        group_id_num = abs(int(group_id_str))
        limit = min(limit, 1000)
        
        try:
            # Проверяем доступность группы
            group_info = await self.get_group_info(str(group_id_num))
            if not group_info:
                logger.error(f"Группа {group_id_num} не найдена")
                return []
            
            if group_info.get('is_closed', 1) != 0:
                logger.warning(f"Группа {group_id_num} закрыта, участники недоступны")
                return []
            
            total_members = group_info.get('members_count', 0)
            if total_members == 0:
                logger.warning(f"У группы {group_id_num} нет участников")
                return []
            
            real_limit = min(limit, total_members, 1000)
            logger.info(f"Сбор {real_limit} участников из {total_members}")
            
            members = []
            offset = 0
            batch_size = 250
            
            while len(members) < real_limit:
                current_batch = min(batch_size, real_limit - len(members))
                
                params = {
                    'group_id': group_id_num,
                    'offset': offset,
                    'count': current_batch,
                    'fields': 'sex,bdate,city,country,interests'
                }
                
                response = await self._make_request('groups.getMembers', params)
                
                if not response:
                    logger.warning(f"Пустой ответ при offset={offset}")
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
                
                if len(items) < current_batch or len(members) >= real_limit:
                    break
            
            logger.info(f"✅ Собрано {len(members)} участников")
            return members
            
        except Exception as e:
            logger.error(f"Ошибка при сборе участников {group_id}: {e}", exc_info=True)
            return []
    
    async def test_connection(self) -> Dict[str, Any]:
        """Тестирование подключения к VK API с реальными тестами"""
        logger.info("Тестирование подключения к VK API...")
        
        test_results = []
        
        # Тест 1: Базовый запрос (проверка токена)
        try:
            logger.info("Тест 1: Базовый запрос к API (проверка токена)")
            params = {'user_ids': '1', 'fields': 'first_name,last_name'}
            response = await self._make_request('users.get', params)
            
            if response and isinstance(response, list) and len(response) > 0:
                user = response[0]
                test_results.append({
                    'test': 'Проверка токена VK',
                    'success': True,
                    'message': f"✅ Токен рабочий: {user.get('first_name', '')} {user.get('last_name', '')}"
                })
            else:
                test_results.append({
                    'test': 'Проверка токена VK',
                    'success': False,
                    'message': '❌ Токен не работает или нет доступа'
                })
        except Exception as e:
            test_results.append({
                'test': 'Проверка токена VK',
                'success': False,
                'message': f'❌ Ошибка: {str(e)[:100]}'
            })
        
        # Тест 2: Запрос группы по числовому ID (публичная группа)
        try:
            logger.info("Тест 2: Запрос группы по ID (public1)")
            # Используем публичную группу с ID 1 (ВКонтакте API)
            group_info = await self.get_group_info("vk.com/public1")
            
            if group_info:
                test_results.append({
                    'test': 'Запрос группы по числовому ID',
                    'success': True,
                    'message': f"✅ Группа найдена: {group_info['name']} ({group_info['members_count']} участников)"
                })
            else:
                test_results.append({
                    'test': 'Запрос группы по числовому ID',
                    'success': False,
                    'message': '❌ Группа не найдена или недоступна'
                })
        except Exception as e:
            test_results.append({
                'test': 'Запрос группы по числовому ID',
                'success': False,
                'message': f'❌ Ошибка: {str(e)[:100]}'
            })
        
        # Тест 3: Попытка запроса по короткому имени
        try:
            logger.info("Тест 3: Запрос группы по короткому имени")
            # Пробуем разные варианты
            test_groups = [
                "durov",           # Павел Дуров
                "club1",           # Альтернативный ID
                "hobby_universe"   # Группа из ошибки пользователя
            ]
            
            success = False
            details = []
            
            for test_group in test_groups:
                try:
                    logger.debug(f"Пробуем группу: {test_group}")
                    group_info = await self.get_group_info(f"vk.com/{test_group}")
                    
                    if group_info:
                        success = True
                        details.append(f"✅ {test_group}: {group_info['name']} ({group_info['members_count']} участников)")
                        break  # Останавливаемся на первой успешной
                    else:
                        details.append(f"❌ {test_group}: не найдена")
                except Exception as e:
                    details.append(f"⚠️ {test_group}: ошибка {str(e)[:50]}")
            
            if success:
                test_results.append({
                    'test': 'Запрос группы по короткому имени',
                    'success': True,
                    'message': f"✅ Успешно: найдена рабочая группа\n" + "\n".join(details)
                })
            else:
                test_results.append({
                    'test': 'Запрос группы по короткому имени',
                    'success': False,
                    'message': f"❌ Не удалось найти ни одну группу по короткому имени\n" + "\n".join(details)
                })
        except Exception as e:
            test_results.append({
                'test': 'Запрос группы по короткому имени',
                'success': False,
                'message': f'❌ Общая ошибка: {str(e)[:100]}'
            })
        
        # Анализ результатов
        success_count = sum(1 for r in test_results if r['success'])
        total_tests = len(test_results)
        
        if success_count == total_tests:
            return {
                'success': True,
                'message': f'✅ Отлично! Все {total_tests} теста пройдены. VK API полностью доступен.',
                'details': test_results
            }
        elif success_count >= 2:
            return {
                'success': True,
                'message': f'⚠️ Частичная доступность: {success_count}/{total_tests} тестов пройдены. Основные функции работают.',
                'details': test_results
            }
        elif success_count >= 1:
            return {
                'success': True,
                'message': f'⚠️ Ограниченная доступность: {success_count}/{total_tests} тестов пройдены. Токен работает, но могут быть проблемы с группами.',
                'details': test_results
            }
        else:
            return {
                'success': False,
                'message': '❌ Критическая проблема: VK API недоступен. Проверьте токен и настройки.',
                'details': test_results
            }
    
    async def close(self):
        """Корректное закрытие сессии"""
        if self.session and not self.session.closed:
            await self.session.close()
            logger.info("Сессия VK API закрыта")

# Глобальный экземпляр
vk_client = VKAPIClient()
