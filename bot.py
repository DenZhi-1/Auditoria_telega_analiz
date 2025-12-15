import asyncio
import logging
import json
import time
import html
from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.enums import ParseMode

from config import config
from vk_api_client import vk_client
from analytics import AudienceAnalyzer
from text_analyzer import TextAnalyzer
from database import Database
from competitor_analysis import CompetitorAnalyzer

# Настройка логирования
log_level = getattr(logging, config.LOG_LEVEL.upper(), logging.INFO)
logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Уменьшаем логирование внешних библиотек
logging.getLogger('aiogram').setLevel(logging.WARNING)
logging.getLogger('aiohttp').setLevel(logging.WARNING)
logging.getLogger('asyncio').setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# Валидация конфигурации при запуске
try:
    config.validate()
    logger.info("Конфигурация проверена успешно")
except ValueError as e:
    logger.error(f"Ошибка конфигурации: {e}")
    raise

# Инициализация компонентов бота
bot = Bot(
    token=config.TELEGRAM_BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()
db = Database()
analyzer = AudienceAnalyzer()
text_analyzer = TextAnalyzer()
competitor_analyzer = CompetitorAnalyzer()

# Словарь для хранения временных данных пользователей
user_sessions = {}

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def create_back_button(callback_data: str = "back_to_report") -> InlineKeyboardMarkup:
    """Создает кнопку 'Назад'"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data=callback_data)]
        ]
    )
    return keyboard

def create_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру главного меню"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔍 Анализ группы", callback_data="analyze_group")],
            [InlineKeyboardButton(text="🥊 Анализ конкурентов", callback_data="competitors_help")],
            [InlineKeyboardButton(text="🧠 AI-анализ текста", callback_data="text_analysis_help")],
            [
                InlineKeyboardButton(text="📊 Статистика", callback_data="user_stats"),
                InlineKeyboardButton(text="📚 Помощь", callback_data="full_help")
            ]
        ]
    )
    return keyboard

def format_number(num: int) -> str:
    """Форматирует число с разделителями тысяч"""
    return f"{num:,}".replace(",", " ")

def get_quality_stars(score: float) -> str:
    """Возвращает звезды для оценки качества"""
    stars_count = min(5, max(1, int(score / 20)))
    return "⭐" * stars_count + "☆" * (5 - stars_count)

def create_competitor_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру для анализа конкурентов"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔍 Найти конкурентов", callback_data="find_competitors"),
                InlineKeyboardButton(text="📊 Сравнить всех", callback_data="compare_all_competitors")
            ],
            [
                InlineKeyboardButton(text="📈 ТОП-5 конкурентов", callback_data="top_competitors"),
                InlineKeyboardButton(text="💡 Рекомендации", callback_data="competitor_recommendations")
            ],
            [
                InlineKeyboardButton(text="📤 Экспорт данных", callback_data="export_competitor_data"),
                InlineKeyboardButton(text="🔙 В главное меню", callback_data="main_menu")
            ]
        ]
    )
    return keyboard

def create_text_analysis_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру для AI-анализа текста"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📊 Тональность", callback_data="text_sentiment"),
                InlineKeyboardButton(text="🔑 Ключевые слова", callback_data="text_keywords")
            ],
            [
                InlineKeyboardButton(text="📚 Темы", callback_data="text_topics"),
                InlineKeyboardButton(text="😊 Эмоции", callback_data="text_emotions")
            ],
            [
                InlineKeyboardButton(text="💡 Рекомендации", callback_data="text_recommendations"),
                InlineKeyboardButton(text="🔙 В главное меню", callback_data="main_menu")
            ]
        ]
    )
    return keyboard

def escape_html(text: str) -> str:
    """Экранирует HTML-спецсимволы для безопасной вставки в HTML"""
    return html.escape(text)

def safe_format_percentage(value: float) -> str:
    """Безопасное форматирование процентов с экранированием"""
    return escape_html(f"{value}%")

async def cleanup_old_sessions():
    """Очищает старые сессии пользователей"""
    current_time = time.time()
    timeout = 3600  # 1 час
    
    to_remove = []
    for user_id, session in user_sessions.items():
        session_time = session.get('created_at', 0)
        if current_time - session_time > timeout:
            to_remove.append(user_id)
    
    for user_id in to_remove:
        del user_sessions[user_id]
        logger.debug(f"Очищена устаревшая сессия пользователя {user_id}")

# ==================== ОСНОВНЫЕ КОМАНДЫ БОТА ====================

@dp.message(Command("start"))
async def cmd_start(message: Message):
    """Приветственное сообщение и список команд"""
    welcome_text = """
👋 <b>Привет! Я бот для глубокого анализа аудитории ВКонтакте.</b>

🚀 <b>НОВЫЕ ВОЗМОЖНОСТИ:</b>
• 🥊 <b>Анализ конкурентов</b> - автоматический поиск и анализ похожих групп
• 🧠 <b>AI-анализ текста</b> - определение тональности и тематик
• 📊 <b>Расширенная аналитика</b> - еще больше метрик и рекомендаций

🎯 <b>Основные команды:</b>
• /analyze [ссылка] — полный анализ аудитории
• /competitors [ссылка] — найти и проанализировать конкурентов
• /text_analysis [ссылка] — AI-анализ текстового контента
• /compare [ссылка1] [ссылка2] — сравнить две группы
• /quick [ссылка] — быстрый анализ
• /stats — ваша статистика
• /help — подробная справка

📝 <b>Примеры:</b>
<code>/analyze https://vk.com/vk</code>
<code>/competitors vk.com/public1</code>
<code>/text_analysis vk.com/groupname</code>

💡 <b>Совет:</b> Используйте команду /competitors для поиска и анализа похожих групп!
"""
    
    await message.answer(welcome_text, reply_markup=create_main_menu_keyboard())

@dp.message(Command("help"))
async def cmd_help(message: Message):
    """Подробная справка по использованию бота"""
    help_text = """
<b>📚 ПОЛНАЯ СПРАВКА ПО ИСПОЛЬЗОВАНИЮ БОТА</b>

<b>Основные команды:</b>

<code>/analyze ссылка_на_группу</code>
<b>Полный анализ аудитории</b>
• Глубокий анализ всех метрик
• Оценка качества аудитории
• Детальные рекомендации

<code>/competitors ссылка_на_группу</code>
<b>Анализ конкурентов (НОВОЕ!)</b>
• Автоматический поиск похожих групп
• Сравнение с конкурентами
• Определение конкурентных преимуществ
• Рекомендации по развитию

<code>/text_analysis ссылка_на_группу</code>
<b>AI-анализ текста (НОВОЕ!)</b>
• Анализ тональности контента
• Определение основных тематик
• Анализ ключевых слов
• Оценка эмоциональной окраски

<code>/quick ссылка_на_группу</code>
<b>Быстрый анализ</b>
• Основные метрики за 1 минуту
• Быстрая оценка аудитории

<code>/compare ссылка1 ссылка2</code>
<b>Сравнение двух групп</b>
• Сравнение демографии
• Сравнение интересов
• Оценка схожести

<code>/stats</code>
<b>Ваша статистика</b>
• Количество анализов
• История запросов
• Сохраненные отчеты

<code>/export [id]</code>
<b>Экспорт данных</b>
• Экспорт анализа в текстовый формат
• Полный отчет с детализацией

<b>🥊 АНАЛИЗ КОНКУРЕНТОВ:</b>
Бот автоматически найдет похожие группы по тематике и проведет их анализ:
1. Поиск конкурентов по ключевым словам
2. Анализ их аудитории
3. Сравнение с вашей группой
4. Выявление сильных и слабых сторон
5. Рекомендации по улучшению

<b>🧠 AI-АНАЛИЗ ТЕКСТА:</b>
Анализ текстового контента группы:
• Тональность (позитивная/негативная/нейтральная)
• Основные темы и категории
• Ключевые слова и фразы
• Эмоциональная окраска
• Рекомендации по контенту

<b>📋 ПОДДЕРЖИВАЕМЫЕ ФОРМАТЫ ССЫЛОК:</b>
• Полная ссылка: <code>https://vk.com/public123456</code>
• Сокращенная: <code>vk.com/club123456</code>
• Короткое имя: <code>https://vk.com/durov</code>
• Упоминание: <code>@durov</code>
• ID группы: <code>public1</code>

<b>⚠️ ОГРАНИЧЕНИЯ:</b>
• Только открытые группы ВК
• Максимум 1000 участников за анализ
• Лимиты VK API
• Анализ может занять 3-5 минут

<b>💡 СОВЕТЫ:</b>
1. Используйте /competitors для исследования рынка
2. Анализируйте текст с помощью /text_analysis
3. Сохраняйте интересные отчеты через /export
4. Сравнивайте группы через /compare
"""
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🥊 Анализ конкурентов", callback_data="start_competitors"),
                InlineKeyboardButton(text="🧠 AI-анализ текста", callback_data="start_text_analysis")
            ],
            [
                InlineKeyboardButton(text="🔍 Начать анализ", callback_data="start_analysis"),
                InlineKeyboardButton(text="🔙 В начало", callback_data="back_to_start")
            ]
        ]
    )
    
    await message.answer(help_text, reply_markup=keyboard, disable_web_page_preview=True)

@dp.message(Command("analyze"))
async def cmd_analyze(message: Message, command: CommandObject = None):
    """Полный анализ аудитории группы ВК"""
    try:
        # ФИКС: Безопасное получение аргументов
        if command is None:
            # Команда вызвана без использования CommandObject
            parts = message.text.split()
            if len(parts) < 2:
                await message.answer(
                    "❌ <b>Укажите ссылку на группу ВК</b>\n\n"
                    "Пример: <code>/analyze https://vk.com/public123</code>\n"
                    "Или: <code>/analyze vk.com/groupname</code>\n\n"
                    "Для быстрого анализа используйте: <code>/quick ссылка</code>"
                )
                return
            group_link = parts[1].strip()
        else:
            # Команда вызвана с CommandObject
            if not command.args:
                await message.answer(
                    "❌ <b>Укажите ссылку на группу ВК</b>\n\n"
                    "Пример: <code>/analyze https://vk.com/public123</code>\n"
                    "Или: <code>/analyze vk.com/groupname</code>\n\n"
                    "Для быстрого анализа используйте: <code>/quick ссылка</code>"
                )
                return
            group_link = command.args.strip()
        
        user_id = message.from_user.id
        
        # Очищаем старые сессии
        await cleanup_old_sessions()
        
        # Проверяем, не выполняется ли уже анализ для этого пользователя
        if user_id in user_sessions and user_sessions[user_id].get('status') == 'analyzing':
            await message.answer(
                "⏳ <b>У вас уже выполняется анализ</b>\n\n"
                "Пожалуйста, дождитесь завершения текущего анализа."
            )
            return
        
        # Начинаем анализ
        user_sessions[user_id] = {
            'status': 'analyzing',
            'group_link': group_link,
            'current_step': 'получение_информации',
            'created_at': time.time()
        }
        
        await message.answer("⏳ <b>Начинаю полный анализ аудитории...</b>")
        logger.info(f"Пользователь {user_id} запросил полный анализ {group_link}")
        
        # Получаем информацию о группе
        await message.answer("🔍 <b>Шаг 1 из 5:</b> Получаю информацию о группе...")
        group_info = await vk_client.get_group_info(group_link)
        
        if not group_info:
            del user_sessions[user_id]
            await message.answer(
                "❌ <b>Не удалось получить информацию о группе</b>\n\n"
                "Возможные причины:\n"
                "• Группа не существует или удалена\n"
                "• Группа заблокирована (banned) в ВК\n"
                "• Группа приватная или закрытая\n"
                "• Неверный формат ссылки\n\n"
                "Попробуйте:\n"
                "1. Проверить правильность ссылки\n"
                "2. Убедиться, что группа открыта и активна\n"
                "3. Использовать другую группу для анализа"
            )
            return
        
        # Проверяем, что группа открыта
        if group_info.get('is_closed', 1) != 0:
            del user_sessions[user_id]
            await message.answer(
                f"⚠️ <b>Группа '{group_info['name']}' закрытая или приватная</b>\n\n"
                "Анализ участников недоступен для закрытых групп ВК."
            )
            return
        
        # Проверяем наличие участников
        if group_info.get('members_count', 0) == 0:
            del user_sessions[user_id]
            await message.answer(
                f"⚠️ <b>В группе '{group_info['name']}' нет участников</b>\n\n"
                "Либо группа пустая, либо данные скрыты."
            )
            return
        
        # Обновляем сессию
        user_sessions[user_id].update({
            'group_info': group_info,
            'current_step': 'сбор_участников'
        })
        
        # Информируем о начале сбора данных
        info_message = await message.answer(
            f"📊 <b>Группа:</b> {escape_html(group_info['name'])}\n"
            f"👥 <b>Участников:</b> {format_number(group_info['members_count'])}\n"
            f"🔍 <b>Статус:</b> {'Открытая' if group_info.get('is_closed') == 0 else 'Закрытая'}\n\n"
            "⏳ <b>Шаг 2 из 5:</b> Собираю данные об участниках..."
        )
        
        # Получаем участников группы
        members_limit = min(1000, group_info['members_count'])
        members = await vk_client.get_group_members(group_info['id'], limit=members_limit)
        
        if not members:
            del user_sessions[user_id]
            await message.answer(
                "❌ <b>Не удалось получить информацию об участниках</b>\n\n"
                "Возможно:\n"
                "• Группа стала приватной во время анализа\n"
                "• Превышены лимиты VK API\n"
                "• Проблемы с сетью\n\n"
                "Попробуйте позже или выберите другую группу."
            )
            return
        
        user_sessions[user_id].update({
            'members': members,
            'current_step': 'анализ_демографии'
        })
        
        await info_message.edit_text(
            f"📊 <b>Группа:</b> {escape_html(group_info['name'])}\n"
            f"👥 <b>Участников:</b> {format_number(group_info['members_count'])}\n"
            f"📈 <b>Проанализировано:</b> {format_number(len(members))} "
            f"({min(100, (len(members) * 100) // group_info['members_count'])}%)\n\n"
            "⏳ <b>Шаг 3 из 5:</b> Анализирую демографию и географию..."
        )
        
        # Анализируем аудиторию
        analysis = await analyzer.analyze_audience(members)
        
        user_sessions[user_id].update({
            'analysis': analysis,
            'current_step': 'генерация_отчета'
        })
        
        await info_message.edit_text(
            f"📊 <b>Группа:</b> {escape_html(group_info['name'])}\n"
            f"👥 <b>Участников:</b> {format_number(group_info['members_count'])}\n"
            f"📈 <b>Проанализировано:</b> {format_number(len(members))}\n\n"
            "⏳ <b>Шаг 4 из 5:</b> Формирую детальный отчет..."
        )
        
        # ФИКС: Преобразуем group_id в строку и сохраняем в базе
        saved = await db.save_analysis(
            user_id=user_id,
            group_id=str(group_info['id']),  # ВАЖНО: Преобразуем в строку
            group_name=group_info['name'],
            analysis=analysis
        )
        
        if saved:
            logger.info(f"Анализ группы {group_info['name']} сохранен в БД")
        else:
            logger.warning(f"Не удалось сохранить анализ группы {group_info['name']}")
        
        user_sessions[user_id].update({
            'current_step': 'отправка_результатов',
            'report_saved': saved
        })
        
        # Формируем и отправляем отчет
        await send_comprehensive_report(message, group_info, analysis, len(members))
        
        # Завершаем сессию
        user_sessions[user_id]['status'] = 'completed'
        
    except KeyError as e:
        logger.error(f"KeyError при анализе группы: {e}", exc_info=True)
        if message.from_user.id in user_sessions:
            del user_sessions[message.from_user.id]
        await message.answer(
            "❌ <b>Ошибка обработки данных от ВКонтакте</b>\n\n"
            "Техническая информация отправлена в лог.\n"
            "Попробуйте другую группу или повторите позже."
        )
    except Exception as e:
        logger.error(f"Непредвиденная ошибка в /analyze: {e}", exc_info=True)
        if message.from_user.id in user_sessions:
            del user_sessions[message.from_user.id]
        await message.answer(
            "❌ <b>Внутренняя ошибка при анализе</b>\n\n"
            "Пожалуйста, попробуйте позже.\n"
            "Если ошибка повторяется, сообщите администратору."
        )

async def send_comprehensive_report(message: Message, group_info: dict, analysis: dict, analyzed_count: int):
    """Отправляет комплексный отчет по анализу"""
    total_members = group_info['members_count']
    analyzed_percentage = min(100, (analyzed_count * 100) // total_members)
    
    # Клавиатура для навигации по отчету
    report_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📊 Демография", callback_data="report_demography"),
                InlineKeyboardButton(text="🎯 Интересы", callback_data="report_interests")
            ],
            [
                InlineKeyboardButton(text="📱 Активность", callback_data="report_activity"),
                InlineKeyboardButton(text="🏙️ География", callback_data="report_geography")
            ],
            [
                InlineKeyboardButton(text="⭐ Качество", callback_data="report_quality"),
                InlineKeyboardButton(text="💡 Рекомендации", callback_data="report_recommendations")
            ],
            [
                InlineKeyboardButton(text="💾 Сохранить отчет", callback_data="save_report"),
                InlineKeyboardButton(text="📤 Экспорт", callback_data="export_report")
            ]
        ]
    )
    
    # Основное сообщение с сводкой
    summary_report = f"""
📊 <b>ПОЛНЫЙ АНАЛИЗ АУДИТОРИИ: {escape_html(group_info['name'])}</b>

<b>📋 ОБЩАЯ ИНФОРМАЦИЯ:</b>
👥 Всего участников: <b>{format_number(total_members)}</b>
📈 Проанализировано: <b>{format_number(analyzed_count)}</b> ({analyzed_percentage}%)
🔗 Ссылка: vk.com/{escape_html(group_info.get('screen_name', ''))}

<b>⭐ ОЦЕНКА КАЧЕСТВА АУДИТОРИИ:</b>
{get_quality_stars(analysis.get('audience_quality_score', 0))} <b>{analysis.get('audience_quality_score', 0)}/100</b>
<i>{escape_html(analysis.get('quality_interpretation', ''))}</i>

<b>👫 ОСНОВНЫЕ МЕТРИКИ:</b>
"""
    
    # Добавляем основные метрики
    gender = analysis.get('gender', {})
    if gender:
        main_gender = "👨 Мужчины" if gender.get('male', 0) > gender.get('female', 0) else "👩 Женщины"
        main_percentage = max(gender.get('male', 0), gender.get('female', 0))
        summary_report += f"• {main_gender}: <b>{main_percentage}%</b>\n"
    
    age_groups = analysis.get('age_groups', {})
    if age_groups:
        main_age = max(age_groups.items(), key=lambda x: x[1])[0] if age_groups else 'не определено'
        summary_report += f"• Основная возрастная группа: <b>{escape_html(main_age)}</b>\n"
    
    if 'average_age' in age_groups:
        summary_report += f"• Средний возраст: <b>{age_groups.get('average_age', 0)} лет</b>\n"
    
    geography = analysis.get('geography', {})
    if geography:
        top_cities = geography.get('top_cities', {})
        if top_cities:
            first_city = list(top_cities.keys())[0] if top_cities else 'не определен'
            summary_report += f"• Основной город: <b>{escape_html(first_city)}</b>\n"
    
    social = analysis.get('social_activity', {})
    if social:
        active_percentage = social.get('active_users_percentage', 0)
        summary_report += f"• Активные пользователи: <b>{active_percentage}%</b>\n"
    
    summary_report += f"\n<b>💡 ИСПОЛЬЗУЙТЕ КНОПКИ НИЖЕ</b> для детального просмотра каждого раздела анализа."
    
    await message.answer(summary_report, reply_markup=report_keyboard)
    
    # Сохраняем данные для callback
    user_id = message.from_user.id
    if user_id in user_sessions:
        user_sessions[user_id]['report_data'] = {
            'group_info': group_info,
            'analysis': analysis,
            'analyzed_count': analyzed_count,
            'created_at': time.time()
        }

@dp.callback_query(F.data.startswith("report_"))
async def handle_report_callback(callback: CallbackQuery):
    """Обработка callback для детальных разделов отчета"""
    user_id = callback.from_user.id
    
    try:
        # Очищаем старые сессии
        await cleanup_old_sessions()
        
        if user_id not in user_sessions or 'report_data' not in user_sessions[user_id]:
            await callback.answer("Данные отчета устарели. Пожалуйста, выполните анализ заново.", show_alert=True)
            return
        
        report_data = user_sessions[user_id]['report_data']
        
        # Проверяем, не устарели ли данные (более 1 часа)
        if time.time() - report_data.get('created_at', 0) > 3600:
            del user_sessions[user_id]
            await callback.answer("Данные отчета устарели. Пожалуйста, выполните анализ заново.", show_alert=True)
            return
        
        analysis = report_data['analysis']
        
        report_type = callback.data.replace("report_", "")
        
        if report_type == "demography":
            await send_demography_report(callback.message, analysis)
        elif report_type == "interests":
            await send_interests_report(callback.message, analysis)
        elif report_type == "activity":
            await send_activity_report(callback.message, analysis)
        elif report_type == "geography":
            await send_geography_report(callback.message, analysis)
        elif report_type == "quality":
            await send_quality_report(callback.message, analysis)
        elif report_type == "recommendations":
            await send_recommendations_report(callback.message, analysis)
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка в колбэке {callback.data}: {e}")
        await callback.answer("Произошла ошибка. Попробуйте еще раз.", show_alert=True)

async def send_demography_report(message: Message, analysis: dict):
    """Отправляет отчет по демографии"""
    gender = analysis.get('gender', {})
    age_groups = analysis.get('age_groups', {})
    
    report = "<b>📊 ДЕТАЛЬНЫЙ АНАЛИЗ ДЕМОГРАФИИ</b>\n\n"
    
    report += "<b>👫 ГЕНДЕРНОЕ РАСПРЕДЕЛЕНИЕ:</b>\n"
    if gender:
        # Прогресс-бары для наглядности
        male_bars = "█" * max(1, int(gender.get('male', 0) / 3))
        female_bars = "█" * max(1, int(gender.get('female', 0) / 3))
        unknown_bars = "█" * max(1, int(gender.get('unknown', 0) / 3))
        
        report += f"👨 Мужчины: <b>{gender.get('male', 0)}%</b> {male_bars}\n"
        report += f"👩 Женщины: <b>{gender.get('female', 0)}%</b> {female_bars}\n"
        if gender.get('unknown', 0) > 0:
            report += f"❓ Не указано: <b>{gender.get('unknown', 0)}%</b> {unknown_bars}\n"
    else:
        report += "Нет данных о поле участников\n"
    
    report += "\n<b>📅 ВОЗРАСТНЫЕ ГРУППЫ:</b>\n"
    if age_groups:
        for age_group, percentage in sorted(age_groups.items()):
            if 'average' not in age_group and 'unknown' not in age_group and percentage > 0:
                bars = "█" * max(1, int(percentage / 5))
                report += f"• {escape_html(age_group)}: <b>{percentage}%</b> {bars}\n"
        
        if 'average_age' in age_groups:
            report += f"\n<b>Средний возраст:</b> {age_groups['average_age']} лет\n"
        
        if 'unknown_percentage' in age_groups and age_groups['unknown_percentage'] > 0:
            report += f"<i>Возраст не указали: {age_groups['unknown_percentage']}% участников</i>\n"
    else:
        report += "Нет данных о возрасте участников\n"
    
    # Анализ распределения
    report += "\n<b>📈 АНАЛИЗ РАСПРЕДЕЛЕНИЯ:</b>\n"
    if gender and age_groups:
        if gender.get('male', 0) > 70:
            report += "• Преобладает мужская аудитория\n"
        elif gender.get('female', 0) > 70:
            report += "• Преобладает женская аудитория\n"
        else:
            report += "• Сбалансированная аудитория по полу\n"
        
        # Определяем основную возрастную группу
        if age_groups:
            main_age_group = max(
                [(k, v) for k, v in age_groups.items() if 'average' not in k and 'unknown' not in k],
                key=lambda x: x[1],
                default=(None, 0)
            )
            if main_age_group[1] > 30:
                report += f"• Основная возрастная группа: {escape_html(main_age_group[0])}\n"
    
    await message.answer(report, reply_markup=create_back_button())

async def send_interests_report(message: Message, analysis: dict):
    """Отправляет отчет по интересам"""
    interests = analysis.get('interests', {})
    popular_categories = interests.get('popular_categories', {})
    
    report = "<b>🎯 АНАЛИЗ ИНТЕРЕСОВ И АКТИВНОСТИ</b>\n\n"
    
    if popular_categories:
        report += "<b>🔥 ПОПУЛЯРНЫЕ КАТЕГОРИИ ИНТЕРЕСОВ:</b>\n"
        for category, percentage in sorted(popular_categories.items(), key=lambda x: x[1], reverse=True)[:8]:
            emoji_map = {
                'технологии': '💻', 'образование': '🎓', 'спорт': '⚽', 
                'искусство': '🎨', 'бизнес': '💼', 'путешествия': '✈️',
                'мода': '👗', 'авто': '🚗', 'кулинария': '🍳',
                'здоровье': '🏥', 'гейминг': '🎮', 'книги': '📚',
                'сериалы': '🎬', 'музыка': '🎵', 'хобби': '🎨'
            }
            emoji = emoji_map.get(category, '•')
            bars = "█" * max(1, int(percentage / 5))
            report += f"{emoji} {escape_html(category.title())}: <b>{percentage}%</b> {bars}\n"
    else:
        report += "Не удалось определить популярные категории интересов\n"
    
    report += f"\n<b>📝 ЗАПОЛНЕННОСТЬ ПРОФИЛЕЙ:</b>\n"
    report += f"• Заполнено профилей: <b>{interests.get('profile_fill_rate', 0)}%</b>\n"
    report += f"• Категорий найдено: <b>{interests.get('total_categories_found', 0)}</b>\n"
    
    report += "\n<b>💡 ИНТЕРПРЕТАЦИЯ:</b>\n"
    if popular_categories:
        top_3 = list(popular_categories.keys())[:3]
        if top_3:
            report += f"Основные интересы аудитории: {', '.join([escape_html(c) for c in top_3])}\n"
        
        # Анализ по сочетаниям интересов
        if 'технологии' in popular_categories and 'образование' in popular_categories:
            report += "• Аудитория технически подкована и стремится к обучению\n"
        if 'спорт' in popular_categories and 'здоровье' in popular_categories:
            report += "• Аудитория заботится о здоровье и физической форме\n"
        if 'искусство' in popular_categories and 'музыка' in popular_categories:
            report += "• Аудитория творческая, интересуется искусством\n"
    
    await message.answer(report, reply_markup=create_back_button())

async def send_activity_report(message: Message, analysis: dict):
    """Отправляет отчет по активности"""
    social = analysis.get('social_activity', {})
    completeness = analysis.get('profile_completeness', {})
    last_seen = social.get('last_seen_distribution', {})
    
    report = "<b>📱 АНАЛИЗ АКТИВНОСТИ И ПОЛНОТЫ ПРОФИЛЕЙ</b>\n\n"
    
    report += "<b>⏰ ВРЕМЯ ПОСЛЕДНЕЙ АКТИВНОСТИ:</b>\n"
    if last_seen:
        # Сортируем по порядку
        order = ['менее_дня', '1-7_дней', '1-4_недели', '1-3_месяца', 'более_3_месяцев', 'никогда']
        for period in order:
            if period in last_seen and last_seen[period] > 0:
                period_name = {
                    'менее_дня': 'Сегодня',
                    '1-7_дней': 'За последнюю неделю',
                    '1-4_недели': '1-4 недели назад',
                    '1-3_месяца': '1-3 месяца назад',
                    'более_3_месяцев': 'Более 3 месяцев назад',
                    'никогда': 'Никогда не заходили'
                }.get(period, period)
                
                bars = "█" * max(1, int(last_seen[period] / 5))
                report += f"• {period_name}: <b>{last_seen[period]}%</b> {bars}\n"
    else:
        report += "Нет данных о времени активности\n"
    
    report += f"\n<b>📊 УРОВЕНЬ АКТИВНОСТИ:</b>\n"
    active_percentage = social.get('active_users_percentage', 0)
    if active_percentage >= 70:
        report += f"• <b>Высокая активность</b> ({active_percentage}% активных пользователей)\n"
        report += "  <i>Аудитория регулярно посещает ВК</i>\n"
    elif active_percentage >= 40:
        report += f"• <b>Средняя активность</b> ({active_percentage}% активных пользователей)\n"
        report += "  <i>Аудитория умеренно активна</i>\n"
    else:
        report += f"• <b>Низкая активность</b> ({active_percentage}% активных пользователей)\n"
        report += "  <i>Аудитория редко посещает ВК</i>\n"
    
    report += "\n<b>📋 ПОЛНОТА ЗАПОЛНЕНИЯ ПРОФИЛЕЙ:</b>\n"
    if completeness:
        avg_completeness = completeness.get('average_completeness', 0)
        high_percentage = completeness.get('high_completeness_percentage', 0)
        # ФИКС: Заменяем "<30%" на "&lt;30%" для корректного HTML
        low_percentage = completeness.get('low_completeness_percentage', 0)
        
        report += f"• Средняя заполненность: <b>{avg_completeness}%</b>\n"
        report += f"• Хорошо заполнены (&gt;70%): <b>{high_percentage}%</b>\n"
        report += f"• Плохо заполнены (&lt;30%): <b>{low_percentage}%</b>\n"
        
        if avg_completeness > 70:
            report += "  <i>Профили хорошо заполнены, можно использовать сложный таргетинг</i>\n"
        elif avg_completeness < 30:
            report += "  <i>Профили заполнены слабо, упрощайте таргетинг</i>\n"
    else:
        report += "Нет данных о полноте профилей\n"
    
    await message.answer(report, reply_markup=create_back_button())

async def send_geography_report(message: Message, analysis: dict):
    """Отправляет отчет по географии"""
    geography = analysis.get('geography', {})
    top_cities = geography.get('top_cities', {})
    countries = geography.get('countries', {})
    city_types = geography.get('city_types', {})
    
    report = "<b>🏙️ АНАЛИЗ ГЕОГРАФИЧЕСКОГО РАСПРЕДЕЛЕНИЯ</b>\n\n"
    
    if top_cities:
        report += "<b>🗺️ ТОП-10 ГОРОДОВ УЧАСТНИКОВ:</b>\n"
        for i, (city, percentage) in enumerate(list(top_cities.items())[:10], 1):
            flag = "🇷🇺" if city.lower() in ['москва', 'санкт-петербург'] else "🏙️"
            bars = "█" * max(1, int(percentage / 5))
            report += f"{i}. {flag} {escape_html(city)}: <b>{percentage}%</b> {bars}\n"
    else:
        report += "Нет данных о городах участников\n"
    
    if countries:
        report += "\n<b>🌍 РАСПРЕДЕЛЕНИЕ ПО СТРАНАМ:</b>\n"
        for country, percentage in sorted(countries.items(), key=lambda x: x[1], reverse=True)[:5]:
            flag = "🇷🇺" if "россия" in country.lower() else "🌐"
            report += f"{flag} {escape_html(country)}: <b>{percentage}%</b>\n"
    
    if city_types:
        report += "\n<b>📊 РАСПРЕДЕЛЕНИЕ ПО ТИПАМ ГОРОДОВ:</b>\n"
        
        # Переименовываем ключи для читаемости
        type_names = {
            'столицы': 'Столицы и крупнейшие города',
            'миллионники': 'Города-миллионники',
            'крупные_города': 'Крупные города (100к+)',
            'средние_города': 'Средние города (30-100к)',
            'малые_города': 'Малые города (до 30к)'
        }
        
        for city_type, percentage in city_types.items():
            if percentage > 0:
                readable_name = type_names.get(city_type, city_type.replace('_', ' ').title())
                bars = "█" * max(1, int(percentage / 5))
                report += f"• {readable_name}: <b>{percentage}%</b> {bars}\n"
        
        # Анализ распределения
        if city_types.get('столицы', 0) > 50:
            report += "\n<i>🎯 Аудитория преимущественно столичная</i>\n"
            report += "  • Подходят премиум-товары и услуги\n"
            report += "  • Высокая покупательная способность\n"
            report += "  • Быстрая реакция на тренды\n"
        elif city_types.get('малые_города', 0) > 50:
            report += "\n<i>🎯 Аудитория из малых городов</i>\n"
            report += "  • Важны доступные цены и доставка\n"
            report += "  • Меньшая конкуренция\n"
            report += "  • Лояльность к брендам\n"
    
    unknown_percentage = geography.get('unknown_location_percentage', 0)
    if unknown_percentage > 0:
        report += f"\n<i>📍 Географию не указали: {unknown_percentage}% участников</i>\n"
    
    await message.answer(report, reply_markup=create_back_button())

async def send_quality_report(message: Message, analysis: dict):
    """Отправляет отчет по качеству аудитории"""
    quality_score = analysis.get('audience_quality_score', 0)
    quality_interpretation = analysis.get('quality_interpretation', '')
    completeness = analysis.get('profile_completeness', {})
    social = analysis.get('social_activity', {})
    interests = analysis.get('interests', {})
    
    report = f"<b>⭐ ОЦЕНКА КАЧЕСТВА АУДИТОРИИ: {quality_score}/100</b>\n\n"
    
    # Звезды для наглядности
    stars = get_quality_stars(quality_score)
    report += f"{stars}\n\n"
    
    report += f"<i>{escape_html(quality_interpretation)}</i>\n\n"
    
    report += "<b>📊 ФАКТОРЫ, ВЛИЯЮЩИЕ НА ОЦЕНКУ:</b>\n\n"
    
    # Полнота профилей (макс 20 баллов)
    avg_completeness = completeness.get('average_completeness', 0)
    completeness_score = (avg_completeness / 100) * 20
    report += f"<b>📋 Полнота профилей:</b> {completeness_score:.1f}/20 баллов\n"
    report += f"   Средняя заполненность: {avg_completeness}%\n"
    if avg_completeness > 70:
        report += "   ✅ Высокий показатель\n"
    elif avg_completeness > 40:
        report += "   ⚠️ Средний показатель\n"
    else:
        report += "   ❌ Низкий показатель\n"
    
    report += "\n"
    
    # Активность пользователей (макс 20 баллов)
    active_percentage = social.get('active_users_percentage', 0)
    activity_score = (active_percentage / 100) * 20
    report += f"<b>📱 Активность пользователей:</b> {activity_score:.1f}/20 баллов\n"
    report += f"   Активных пользователей: {active_percentage}%\n"
    if active_percentage > 70:
        report += "   ✅ Высокая активность\n"
    elif active_percentage > 40:
        report += "   ⚠️ Средняя активность\n"
    else:
        report += "   ❌ Низкая активность\n"
    
    report += "\n"
    
    # Разнообразие интересов (макс 10 баллов)
    total_categories = interests.get('total_categories_found', 0)
    interests_score = min(10, total_categories * 2)
    report += f"<b>🎯 Разнообразие интересов:</b> {interests_score:.1f}/10 баллов\n"
    report += f"   Категорий интересов: {total_categories}\n"
    if total_categories > 5:
        report += "   ✅ Широкий спектр интересов\n"
    elif total_categories > 2:
        report += "   ⚠️ Умеренное разнообразие\n"
    else:
        report += "   ❌ Ограниченные интересы\n"
    
    report += "\n"
    
    # Сбалансированность по полу (макс 10 баллов)
    gender = analysis.get('gender', {})
    gender_diff = abs(gender.get('male', 0) - gender.get('female', 0))
    gender_score = max(0, 10 - (gender_diff / 10))
    report += f"<b>⚖️ Сбалансированность по полу:</b> {gender_score:.1f}/10 баллов\n"
    report += f"   Разница мужчин/женщин: {gender_diff}%\n"
    if gender_diff < 20:
        report += "   ✅ Сбалансированная аудитория\n"
    elif gender_diff < 40:
        report += "   ⚠️ Умеренный перекос\n"
    else:
        report += "   ❌ Сильный перекос\n"
    
    report += "\n<b>📈 РЕКОМЕНДАЦИИ ПО УЛУЧШЕНИЮ:</b>\n"
    
    if avg_completeness < 50:
        report += "• Работайте над полнотой профилей участников\n"
    if active_percentage < 50:
        report += "• Повышайте активность через контент и взаимодействие\n"
    if total_categories < 3:
        report += "• Расширяйте тематику контента для привлечения разнообразной аудитории\n"
    if gender_diff > 40:
        report += "• Попробуйте привлечь аудиторию противоположного пола\n"
    
    if quality_score >= 80:
        report += "\n✅ <b>Ваша аудитория уже высокого качества!</b> Фокусируйтесь на удержании и монетизации."
    elif quality_score >= 60:
        report += "\n⚠️ <b>Аудитория хорошего качества.</b> Работайте над улучшением слабых сторон."
    else:
        report += "\n❌ <b>Аудитория требует улучшений.</b> Сфокусируйтесь на рекомендациях выше."
    
    await message.answer(report, reply_markup=create_back_button())

async def send_recommendations_report(message: Message, analysis: dict):
    """Отправляет отчет с рекомендациями"""
    recommendations = analysis.get('recommendations', [])
    gender = analysis.get('gender', {})
    age_groups = analysis.get('age_groups', {})
    geography = analysis.get('geography', {})
    social = analysis.get('social_activity', {})
    
    report = "<b>💡 РЕКОМЕНДАЦИИ ДЛЯ ТАРГЕТИРОВАННОЙ РЕКЛАМЫ</b>\n\n"
    
    if recommendations:
        for i, rec in enumerate(recommendations[:12], 1):
            # Определяем эмодзи для типа рекомендации
            if "аудитория" in rec.lower() or "преобладает" in rec.lower():
                emoji = "👥"
            elif "возраст" in rec.lower():
                emoji = "📅"
            elif "город" in rec.lower() or "гео" in rec.lower():
                emoji = "🏙️"
            elif "активность" in rec.lower():
                emoji = "📱"
            elif "интересы" in rec.lower() or "тема" in rec.lower():
                emoji = "🎯"
            elif "качество" in rec.lower() or "профиль" in rec.lower():
                emoji = "📋"
            elif "таргетинг" in rec.lower() or "реклам" in rec.lower():
                emoji = "🎯"
            else:
                emoji = "💡"
            
            report += f"{emoji} <b>{i}.</b> {escape_html(rec)}\n"
    else:
        report += "Нет сгенерированных рекомендаций\n"
    
    report += "\n<b>🎯 КОНКРЕТНЫЕ СТРАТЕГИИ ТАРГЕТИНГА:</b>\n\n"
    
    # Гендерный таргетинг
    if gender.get('male', 0) > 60:
        report += "<b>👨 Для мужской аудитории:</b>\n"
        report += "• Технологии, гаджеты, авто\n"
        report += "• Спорт, фитнес, здоровье\n"
        report += "• Бизнес, финансы, карьера\n"
        report += "• Юмор, игры, развлечения\n\n"
    elif gender.get('female', 0) > 60:
        report += "<b>👩 Для женской аудитории:</b>\n"
        report += "• Мода, красота, стиль\n"
        report += "• Здоровье, диеты, уход\n"
        report += "• Семья, дети, отношения\n"
        report += "• Творчество, хобби, рукоделие\n\n"
    
    # Возрастной таргетинг
    main_age_group = max(
        [(k, v) for k, v in age_groups.items() if 'average' not in k and 'unknown' not in k],
        key=lambda x: x[1],
        default=(None, 0)
    )[0]
    
    if main_age_group:
        report += f"<b>📅 Для возрастной группы {escape_html(main_age_group)}:</b>\n"
        if main_age_group == 'до 18':
            report += "• Образование, курсы, учеба\n"
            report += "• Мода, музыка, сериалы\n"
            report += "• Игры, развлечения\n\n"
        elif main_age_group == '18-24':
            report += "• Образование, карьера, стартапы\n"
            report += "• Путешествия, активный отдых\n"
            report += "• Технологии, гаджеты\n\n"
        elif main_age_group == '25-34':
            report += "• Карьера, бизнес, инвестиции\n"
            report += "• Недвижимость, автомобили\n"
            report += "• Семья, дети, здоровье\n\n"
        elif main_age_group == '35-44':
            report += "• Карьера, бизнес, управление\n"
            report += "• Недвижимость, инвестиции\n"
            report += "• Здоровье, путешествия\n\n"
        elif main_age_group == '45+':
            report += "• Здоровье, медицина\n"
            report += "• Отдых, хобби, дача\n"
            report += "• Финансы, недвижимость\n\n"
    
    # Географический таргетинг
    city_types = geography.get('city_types', {})
    if city_types.get('столицы', 0) > 50:
        report += "<b>🏙️ Для столичной аудитории:</b>\n"
        report += "• Премиум-товары и услуги\n"
        report += "• Образование, курсы повышения квалификации\n"
        report += "• Рестораны, развлечения, события\n\n"
    elif city_types.get('малые_города', 0) > 50:
        report += "<b>🏡 Для аудитории из малых городов:</b>\n"
        report += "• Товары с доставкой по всей России\n"
        report += "• Образовательные курсы онлайн\n"
        report += "• Услуги для дома и семьи\n\n"
    
    # Рекомендации по времени публикаций
    active_percentage = social.get('active_users_percentage', 0)
    if active_percentage > 70:
        report += "<b>⏰ Рекомендуемое время публикаций:</b>\n"
        report += "• Утро (9-11): образовательный контент\n"
        report += "• Обед (13-15): развлекательный контент\n"
        report += "• Вечер (19-22): основные публикации\n"
        report += "• Можно публиковать чаще (3-5 раз в день)\n"
    else:
        report += "<b>⏰ Рекомендуемое время публикаций:</b>\n"
        report += "• Утро (10-11): основные публикации\n"
        report += "• Вечер (20-21): повтор важного контента\n"
        report += "• Публикуйте реже, но качественнее (1-2 раза в день)\n"
    
    report += "\n<b>🎯 КЛЮЧЕВОЙ СОВЕТ:</b>\n"
    report += "Тестируйте разные подходы, анализируйте результаты и оптимизируйте стратегию на основе данных.\n"
    
    await message.answer(report, reply_markup=create_back_button())

@dp.callback_query(F.data == "back_to_report")
async def back_to_report(callback: CallbackQuery):
    """Возвращает к основному отчету"""
    user_id = callback.from_user.id
    
    try:
        if user_id not in user_sessions or 'report_data' not in user_sessions[user_id]:
            await callback.answer("Данные отчета устарели", show_alert=True)
            return
        
        report_data = user_sessions[user_id]['report_data']
        group_info = report_data['group_info']
        analysis = report_data['analysis']
        analyzed_count = report_data['analyzed_count']
        
        await send_comprehensive_report(callback.message, group_info, analysis, analyzed_count)
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка в back_to_report: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)

# ==================== ДОПОЛНИТЕЛЬНЫЕ КОМАНДЫ ====================

@dp.message(Command("competitors"))
async def cmd_competitors(message: Message, command: CommandObject = None):
    """Анализ конкурентов группы"""
    try:
        # ФИКС: Безопасное получение аргументов
        if command is None:
            # Команда вызвана без использования CommandObject
            parts = message.text.split()
            if len(parts) < 2:
                await message.answer(
                    "🥊 <b>Анализ конкурентов</b>\n\n"
                    "Эта команда найдет и проанализирует похожие группы.\n\n"
                    "<b>Пример:</b>\n"
                    "<code>/competitors https://vk.com/public123</code>\n"
                    "<code>/competitors vk.com/groupname</code>\n\n"
                    "<i>Бот найдет до 10 похожих групп и проведет их анализ</i>"
                )
                return
            group_link = parts[1].strip()
        else:
            # Команда вызвана с CommandObject
            if not command.args:
                await message.answer(
                    "🥊 <b>Анализ конкурентов</b>\n\n"
                    "Эта команда найдет и проанализирует похожие группы.\n\n"
                    "<b>Пример:</b>\n"
                    "<code>/competitors https://vk.com/public123</code>\n"
                    "<code>/competitors vk.com/groupname</code>\n\n"
                    "<i>Бот найдет до 10 похожих групп и проведет их анализ</i>"
                )
                return
            group_link = command.args.strip()
        
        user_id = message.from_user.id
        
        await message.answer("🥊 <b>Начинаю анализ конкурентов...</b>")
        
        # Реализация анализа конкурентов
        await message.answer(
            f"Анализ конкурентов для группы: {escape_html(group_link)}\n\n"
            "Функционал в разработке..."
        )
        
    except Exception as e:
        logger.error(f"Ошибка в команде /competitors: {e}", exc_info=True)
        await message.answer(
            "❌ <b>Ошибка при анализе конкурентов</b>\n\n"
            "Попробуйте позже или выберите другую группу."
        )

@dp.message(Command("text_analysis"))
async def cmd_text_analysis(message: Message, command: CommandObject = None):
    """AI-анализ текстового контента группы"""
    try:
        # ФИКС: Безопасное получение аргументов
        if command is None:
            # Команда вызвана без использования CommandObject
            parts = message.text.split()
            if len(parts) < 2:
                await message.answer(
                    "🧠 <b>AI-анализ текстового контента</b>\n\n"
                    "Эта команда проанализирует текстовый контент группы:\n"
                    "• Тональность (позитивная/негативная/нейтральная)\n"
                    "• Основные темы и категории\n"
                    "• Ключевые слова и фразы\n"
                    "• Эмоциональная окраска\n\n"
                    "<b>Пример:</b>\n"
                    "<code>/text_analysis https://vk.com/public123</code>\n"
                    "<code>/text_analysis vk.com/groupname</code>"
                )
                return
            group_link = parts[1].strip()
        else:
            # Команда вызвана с CommandObject
            if not command.args:
                await message.answer(
                    "🧠 <b>AI-анализ текстового контента</b>\n\n"
                    "Эта команда проанализирует текстовый контент группы:\n"
                    "• Тональность (позитивная/негативная/нейтральная)\n"
                    "• Основные темы и категории\n"
                    "• Ключевые слова и фразы\n"
                    "• Эмоциональная окраска\n\n"
                    "<b>Пример:</b>\n"
                    "<code>/text_analysis https://vk.com/public123</code>\n"
                    "<code>/text_analysis vk.com/groupname</code>"
                )
                return
            group_link = command.args.strip()
        
        await message.answer("🧠 <b>Начинаю AI-анализ текста...</b>")
        
        # Реализация анализа текста
        await message.answer(
            f"AI-анализ текста для группы: {escape_html(group_link)}\n\n"
            "Функционал в разработке..."
        )
        
    except Exception as e:
        logger.error(f"Ошибка в команде /text_analysis: {e}", exc_info=True)
        await message.answer(
            "❌ <b>Ошибка при анализе текста</b>\n\n"
            "Попробуйте позже или выберите другую группу."
        )

@dp.message(Command("quick"))
async def cmd_quick(message: Message, command: CommandObject = None):
    """Быстрый анализ аудитории"""
    try:
        # ФИКС: Безопасное получение аргументов
        if command is None:
            # Команда вызвана без использования CommandObject
            parts = message.text.split()
            if len(parts) < 2:
                await message.answer(
                    "⚡ <b>Быстрый анализ аудитории</b>\n\n"
                    "Пример: <code>/quick https://vk.com/public123</code>\n"
                    "Или: <code>/quick vk.com/groupname</code>\n\n"
                    "<i>Быстрый анализ показывает основные метрики за 1-2 минуты</i>"
                )
                return
            group_link = parts[1].strip()
        else:
            # Команда вызвана с CommandObject
            if not command.args:
                await message.answer(
                    "⚡ <b>Быстрый анализ аудитории</b>\n\n"
                    "Пример: <code>/quick https://vk.com/public123</code>\n"
                    "Или: <code>/quick vk.com/groupname</code>\n\n"
                    "<i>Быстрый анализ показывает основные метрики за 1-2 минуты</i>"
                )
                return
            group_link = command.args.strip()
        
        await message.answer("⚡ <b>Запускаю быстрый анализ...</b>")
        
        # Простая реализация быстрого анализа
        await message.answer(
            f"Быстрый анализ для группы: {escape_html(group_link)}\n\n"
            "Функционал в разработке...\n"
            "Используйте <code>/analyze</code> для полного анализа."
        )
        
    except Exception as e:
        logger.error(f"Ошибка в команде /quick: {e}", exc_info=True)
        await message.answer("❌ <b>Ошибка быстрого анализа.</b> Попробуйте позже.")

@dp.message(Command("compare"))
async def cmd_compare(message: Message):
    """Сравнение аудиторий двух групп"""
    try:
        args = message.text.split()[1:]
        if len(args) < 2:
            await message.answer(
                "🔄 <b>Сравнение двух групп</b>\n\n"
                "Пример: <code>/compare https://vk.com/group1 https://vk.com/group2</code>\n\n"
                "<i>Сравнивает демографию, интересы и качество аудитории</i>"
            )
            return
        
        group1_link, group2_link = args[0].strip(), args[1].strip()
        
        await message.answer("🔄 <b>Начинаю сравнение аудиторий...</b>")
        
        # Простая реализация сравнения
        await message.answer(
            f"Сравнение групп:\n"
            f"1. {escape_html(group1_link)}\n"
            f"2. {escape_html(group2_link)}\n\n"
            "Функционал в разработке..."
        )
        
    except Exception as e:
        logger.error(f"Ошибка в команде /compare: {e}", exc_info=True)
        await message.answer(
            "❌ <b>Ошибка при сравнении групп</b>\n\n"
            "Попробуйте позже или проверьте правильность ссылок."
        )

@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    """Показать статистику пользователя"""
    try:
        stats = await db.get_user_stats(message.from_user.id)
        
        report = f"📈 <b>ВАША СТАТИСТИКА</b>\n\n"
        report += f"👤 <b>Ваш ID:</b> {message.from_user.id}\n"
        report += f"📊 <b>Проанализировано групп:</b> {stats.get('total_analyses', 0)}\n"
        report += f"💾 <b>Сохранено отчетов:</b> {stats.get('saved_reports', 0)}\n"
        
        if stats.get('last_analyses'):
            report += "\n<b>📅 ПОСЛЕДНИЕ АНАЛИЗЫ:</b>\n"
            for i, analysis in enumerate(stats['last_analyses'][:5], 1):
                report += f"{i}. {escape_html(analysis['group_name'])} — {analysis['created_at']}\n"
        else:
            report += "\n<i>У вас пока нет сохраненных анализов.</i>\n"
            report += "<i>Используйте команду /analyze для первого анализа!</i>"
        
        # Добавляем кнопки действий
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📊 Новый анализ", callback_data="start_analysis")],
                [InlineKeyboardButton(text="📤 Экспорт истории", callback_data="export_history")],
                [InlineKeyboardButton(text="🔙 В главное меню", callback_data="main_menu")]
            ]
        )
        
        await message.answer(report, reply_markup=keyboard)
        
    except Exception as e:
        logger.error(f"Ошибка в команде /stats: {e}", exc_info=True)
        await message.answer("❌ <b>Ошибка при получении статистики.</b> Попробуйте позже.")

# ==================== ОБРАБОТЧИКИ КНОПОК ====================

@dp.callback_query(F.data == "analyze_group")
async def analyze_group_callback(callback: CallbackQuery):
    """Обработчик кнопки анализа группы"""
    await callback.message.answer(
        "🔍 <b>Анализ группы ВКонтакте</b>\n\n"
        "Отправьте ссылку на группу:\n"
        "<code>https://vk.com/public123</code>\n"
        "Или: <code>vk.com/groupname</code>\n\n"
        "Для полного анализа: /analyze ссылка\n"
        "Для быстрого анализа: /quick ссылка"
    )
    await callback.answer()

@dp.callback_query(F.data == "competitors_help")
async def competitors_help_callback(callback: CallbackQuery):
    """Обработчик кнопки помощи по конкурентам"""
    await callback.message.answer(
        "🥊 <b>Анализ конкурентов</b>\n\n"
        "Эта функция найдет и проанализирует похожие группы.\n\n"
        "<b>Пример команды:</b>\n"
        "<code>/competitors https://vk.com/public123</code>\n\n"
        "<b>Что делает бот:</b>\n"
        "1. Находит похожие группы по тематике\n"
        "2. Анализирует их аудиторию\n"
        "3. Сравнивает с вашей группой\n"
        "4. Дает рекомендации по улучшению\n\n"
        "<i>Анализ может занять 3-5 минут</i>"
    )
    await callback.answer()

@dp.callback_query(F.data == "text_analysis_help")
async def text_analysis_help_callback(callback: CallbackQuery):
    """Обработчик кнопки помощи по AI-анализу текста"""
    await callback.message.answer(
        "🧠 <b>AI-анализ текста</b>\n\n"
        "Эта функция анализирует текстовый контент группы.\n\n"
        "<b>Пример команды:</b>\n"
        "<code>/text_analysis https://vk.com/public123</code>\n\n"
        "<b>Что анализирует бот:</b>\n"
        "• Тональность (позитивная/негативная/нейтральная)\n"
        "• Основные темы и категории\n"
        "• Ключевые слова и фразы\n"
        "• Эмоциональную окраску\n"
        "• Читаемость текста\n\n"
        "<i>Анализ использует NLP-алгоритмы</i>"
    )
    await callback.answer()

@dp.callback_query(F.data == "full_help")
async def full_help_callback(callback: CallbackQuery):
    """Обработчик кнопки полной помощи"""
    await cmd_help(callback.message)
    await callback.answer()

@dp.callback_query(F.data == "start_analysis")
async def start_analysis_callback(callback: CallbackQuery):
    """Обработчик кнопки начала анализа"""
    await callback.message.answer(
        "🎯 <b>Начать анализ группы</b>\n\n"
        "Отправьте ссылку на группу ВК:\n"
        "<code>https://vk.com/public123</code>\n"
        "Или: <code>vk.com/groupname</code>\n\n"
        "Для полного анализа: /analyze ссылка\n"
        "Для быстрого анализа: /quick ссылка"
    )
    await callback.answer()

@dp.callback_query(F.data == "user_stats")
async def user_stats_callback(callback: CallbackQuery):
    """Обработчик кнопки статистики"""
    await cmd_stats(callback.message)
    await callback.answer()

@dp.callback_query(F.data == "main_menu")
async def main_menu_callback(callback: CallbackQuery):
    """Обработчик кнопки главного меню"""
    await cmd_start(callback.message)
    await callback.answer()

@dp.callback_query(F.data == "back_to_start")
async def back_to_start_callback(callback: CallbackQuery):
    """Обработчик кнопки возврата в начало"""
    await cmd_start(callback.message)
    await callback.answer()

# ==================== ОСНОВНАЯ ФУНКЦИЯ ====================

async def main():
    """Основная функция запуска бота"""
    logger.info("=" * 60)
    logger.info("🚀 ЗАПУСК ТЕЛЕГРАМ БОТА С AI-АНАЛИЗОМ И АНАЛИЗОМ КОНКУРЕНТОВ")
    logger.info("=" * 60)
    
    try:
        # Инициализация базы данных
        logger.info("Инициализация базы данных...")
        db_success = await db.init_db()
        
        if db_success:
            logger.info("✅ База данных подключена успешно")
        else:
            logger.warning("⚠️  Бот запущен с временной SQLite базой")
        
        # Получение информации о боте
        bot_info = await bot.get_me()
        logger.info(f"🤖 Бот: @{bot_info.username} (ID: {bot_info.id})")
        logger.info(f"👥 Администраторы: {config.ADMIN_IDS}")
        logger.info(f"🌐 VK API Версия: {config.VK_API_VERSION}")
        
        # Сбрасываем вебхук
        try:
            await bot.delete_webhook(drop_pending_updates=True)
            logger.info("✅ Вебхук сброшен, старые обновления удалены")
        except Exception as e:
            logger.warning(f"При сбросе вебхука: {e}")
        
        # Ждем 2 секунды для очистки состояния
        await asyncio.sleep(2)
        
        logger.info("✅ Бот готов к работе! Ожидание команд...")
        logger.info("-" * 60)
        
        # Запуск бота
        await dp.start_polling(bot, skip_updates=True)
        
    except KeyboardInterrupt:
        logger.info("Получен сигнал прерывания (Ctrl+C)")
    except Exception as e:
        logger.critical(f"КРИТИЧЕСКАЯ ОШИБКА ПРИ ЗАПУСКЕ БОТА: {e}", exc_info=True)
        raise
    finally:
        # Корректное завершение работы
        logger.info("Завершение работы бота...")
        
        try:
            await db.close()
            logger.info("✅ Соединения с базой данных закрыты")
        except Exception as e:
            logger.error(f"Ошибка при закрытии БД: {e}")
        
        try:
            await vk_client.close()
            logger.info("✅ Сессия VK API закрыта")
        except Exception as e:
            logger.error(f"Ошибка при закрытии VK клиента: {e}")
        
        logger.info("Бот остановлен")
        logger.info("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
