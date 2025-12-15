import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.enums import ParseMode

from config import config
from vk_api_client import vk_client
from analytics import AudienceAnalyzer
from database import Database

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

# ==================== КОМАНДЫ БОТА ====================

@dp.message(Command("start"))
async def cmd_start(message: Message):
    """Приветственное сообщение и список команд"""
    await message.answer(
        "👋 <b>Привет! Я бот для анализа аудитории ВКонтакте.</b>\n\n"
        "📊 <b>Доступные команды:</b>\n"
        "• /analyze [ссылка] — проанализировать аудиторию группы\n"
        "• /compare [ссылка1] [ссылка2] — сравнить две аудитории\n"
        "• /stats — посмотреть вашу статистику\n"
        "• /test_vk — тест подключения к VK API (только для админов)\n"
        "• /help — подробная справка\n\n"
        "⚠️ <i>Для анализа доступны только открытые группы ВК.</i>"
    )

@dp.message(Command("help"))
async def cmd_help(message: Message):
    """Подробная справка по использованию бота"""
    help_text = """
<b>📚 Справка по использованию бота</b>

<b>Основные команды:</b>
<code>/analyze ссылка_на_группу</code> — анализ аудитории группы ВК
<code>/compare ссылка1 ссылка2</code> — сравнение двух групп
<code>/stats</code> — ваша статистика анализов
<code>/test_vk</code> — тест подключения к VK API (только админы)

<b>Поддерживаемые форматы ссылок:</b>
• Полная ссылка: <code>https://vk.com/public123456</code>
• Сокращенная: <code>vk.com/club123456</code>
• Короткое имя: <code>https://vk.com/durov</code>
• Упоминание: <code>@durov</code>

<b>Примеры использования:</b>
<code>/analyze https://vk.com/durov</code>
<code>/compare vk.com/group1 vk.com/group2</code>

<b>Что анализирует бот:</b>
✅ Демография (пол, возраст)
✅ География (города)
✅ Интересы и активность
✅ Рекомендации для таргетированной рекламы

<b>Важные ограничения:</b>
⚠️ Только открытые группы ВК
⚠️ До 1000 участников за один анализ
⚠️ Лимиты VK API (~3 запроса в секунду)
"""
    await message.answer(help_text)

@dp.message(Command("analyze"))
async def cmd_analyze(message: Message):
    """Анализ аудитории группы ВК"""
    try:
        # Извлекаем ссылку из команды
        args = message.text.split()[1:]
        if not args:
            await message.answer(
                "❌ <b>Укажите ссылку на группу ВК</b>\n\n"
                "Пример: <code>/analyze https://vk.com/public123</code>\n"
                "Или: <code>/analyze vk.com/groupname</code>"
            )
            return
        
        group_link = args[0].strip()
        
        # Отправляем подтверждение
        await message.answer("⏳ <b>Начинаю анализ аудитории...</b>")
        logger.info(f"Пользователь {message.from_user.id} запросил анализ {group_link}")
        
        # Получаем информацию о группе
        group_info = await vk_client.get_group_info(group_link)
        if not group_info:
            await message.answer(
                "❌ <b>Не удалось получить информацию о группе</b>\n\n"
                "Возможные причины:\n"
                "• Группа не существует или удалена\n"
                "• Группа заблокирована (banned) в ВК\n"
                "• Группа приватная или закрытая\n"
                "• Неверный формат ссылки\n"
                "• Проблемы с доступом к VK API\n\n"
                "Попробуйте:\n"
                "1. Проверить правильность ссылки\n"
                "2. Убедиться, что группа открыта и активна\n"
                "3. Использовать другую группу для анализа"
            )
            return
        
        # Проверяем, что группа открыта и имеет участников
        if group_info.get('is_closed', 1) != 0:
            await message.answer(
                f"⚠️ <b>Группа '{group_info['name']}' закрытая или приватная</b>\n\n"
                "Анализ участников недоступен для закрытых групп ВК."
            )
            return
        
        if group_info.get('members_count', 0) == 0:
            await message.answer(
                f"⚠️ <b>В группе '{group_info['name']}' нет участников</b>\n\n"
                "Либо группа пустая, либо данные скрыты."
            )
            return
        
        # Уведомляем о начале сбора данных
        await message.answer(
            f"📊 <b>Группа:</b> {group_info['name']}\n"
            f"👥 <b>Участников:</b> {group_info['members_count']:,}\n"
            f"🔍 <b>Статус:</b> {'Открытая' if group_info.get('is_closed') == 0 else 'Закрытая'}\n\n"
            "⌛️ <i>Собираю данные об участниках... Это может занять некоторое время.</i>"
        )
        
        # Получаем участников группы (ограничиваем для производительности)
        members_limit = min(1000, group_info['members_count'])
        members = await vk_client.get_group_members(group_info['id'], limit=members_limit)
        
        if not members:
            await message.answer(
                "❌ <b>Не удалось получить информацию об участниках</b>\n\n"
                "Возможно:\n"
                "• Группа стала приватной во время анализа\n"
                "• Превышены лимиты VK API\n"
                "• Проблемы с сетью\n\n"
                "Попробуйте позже или выберите другую группу."
            )
            return
        
        # Анализируем аудиторию
        analysis = await analyzer.analyze_audience(members)
        
        # Сохраняем результаты в базу данных
        saved = await db.save_analysis(
            user_id=message.from_user.id,
            group_id=group_info['id'],
            group_name=group_info['name'],
            analysis=analysis
        )
        
        if saved:
            logger.info(f"Анализ группы {group_info['name']} сохранен в БД")
        
        # Формируем отчет
        report = f"📊 <b>АНАЛИЗ АУДИТОРИИ: {group_info['name']}</b>\n\n"
        report += f"👥 <b>Всего участников:</b> {group_info['members_count']:,}\n"
        report += f"📈 <b>Проанализировано:</b> {len(members):,} "
        
        # Процент проанализированных участников
        if group_info['members_count'] > 0:
            percentage = min(100, (len(members) * 100) // group_info['members_count'])
            report += f"({percentage}%)\n\n"
        else:
            report += "\n\n"
        
        # Гендерное распределение
        if 'gender' in analysis:
            male = analysis['gender'].get('male', 0)
            female = analysis['gender'].get('female', 0)
            unknown = analysis['gender'].get('unknown', 0)
            
            report += "<b>👫 ГЕНДЕРНОЕ РАСПРЕДЕЛЕНИЕ:</b>\n"
            report += f"👨 Мужчины: <b>{male}%</b>\n"
            report += f"👩 Женщины: <b>{female}%</b>\n"
            if unknown > 0:
                report += f"❓ Не указано: <b>{unknown}%</b>\n"
            report += "\n"
        
        # Возрастные группы
        if 'age_groups' in analysis:
            report += "<b>📅 ВОЗРАСТНЫЕ ГРУППЫ:</b>\n"
            for age, perc in analysis['age_groups'].items():
                if perc > 0:
                    # Добавляем индикатор прогресса
                    bars = "█" * max(1, int(perc / 5))
                    report += f"• {age}: <b>{perc}%</b> {bars}\n"
            report += "\n"
        
        # Топ городов
        if 'cities' in analysis and analysis['cities']:
            report += "<b>🗺️ ТОП ГОРОДОВ:</b>\n"
            for i, (city, count) in enumerate(list(analysis['cities'].items())[:5], 1):
                report += f"{i}. {city}: <b>{count}%</b>\n"
            report += "\n"
        
        await message.answer(report)
        
        # Рекомендации для таргета (отдельным сообщением)
        if analysis.get('recommendations'):
            rec_text = "<b>🎯 РЕКОМЕНДАЦИИ ДЛЯ ТАРГЕТИРОВАННОЙ РЕКЛАМЫ:</b>\n\n"
            for i, rec in enumerate(analysis['recommendations'][:3], 1):
                rec_text += f"{i}. {rec}\n"
            
            rec_text += "\n<i>💡 Совет: Используйте эти данные для настройки рекламных кампаний в ВК и Telegram</i>"
            await message.answer(rec_text)
        
        # Финальное сообщение
        await message.answer(
            "✅ <b>Анализ завершен успешно!</b>\n\n"
            "Чтобы посмотреть статистику ваших анализов, используйте команду /stats\n"
            "Для сравнения с другой группой: /compare ссылка1 ссылка2"
        )
        
    except KeyError as e:
        logger.error(f"KeyError при анализе группы: {e}", exc_info=True)
        await message.answer(
            "❌ <b>Ошибка обработки данных от ВКонтакте</b>\n\n"
            "Техническая информация отправлена в лог.\n"
            "Попробуйте другую группу или повторите позже."
        )
    except Exception as e:
        logger.error(f"Непредвиденная ошибка в /analyze: {e}", exc_info=True)
        await message.answer(
            "❌ <b>Внутренняя ошибка при анализе</b>\n\n"
            "Пожалуйста, попробуйте позже.\n"
            "Если ошибка повторяется, сообщите администратору."
        )

@dp.message(Command("compare"))
async def cmd_compare(message: Message):
    """Сравнение аудиторий двух групп"""
    try:
        args = message.text.split()[1:]
        if len(args) < 2:
            await message.answer(
                "❌ <b>Укажите две ссылки на группы для сравнения</b>\n\n"
                "Пример: <code>/compare https://vk.com/group1 https://vk.com/group2</code>\n"
                "Или: <code>/compare vk.com/group1 @group2</code>"
            )
            return
        
        group1_link, group2_link = args[0].strip(), args[1].strip()
        
        await message.answer("⏳ <b>Начинаю сравнение аудиторий...</b>")
        logger.info(f"Пользователь {message.from_user.id} сравнивает {group1_link} и {group2_link}")
        
        groups_data = []
        successful_groups = []
        
        # Собираем данные по обеим группам
        for i, link in enumerate([group1_link, group2_link], 1):
            await message.answer(f"🔍 <b>Анализирую группу {i}...</b>")
            
            group_info = await vk_client.get_group_info(link)
            if not group_info:
                await message.answer(f"❌ <b>Не удалось получить группу {i}:</b> {link}")
                continue
            
            if group_info.get('is_closed', 1) != 0:
                await message.answer(f"⚠️ <b>Группа {i} закрытая:</b> {group_info['name']}")
                continue
            
            members = await vk_client.get_group_members(group_info['id'], limit=500)
            if not members:
                await message.answer(f"⚠️ <b>Нет данных об участниках:</b> {group_info['name']}")
                continue
            
            analysis = await analyzer.analyze_audience(members)
            groups_data.append({
                'info': group_info,
                'analysis': analysis
            })
            successful_groups.append(group_info['name'])
            
            await message.answer(f"✅ <b>Группа {i} готова:</b> {group_info['name']} ({len(members)} участников)")
        
        # Проверяем, что получили данные обеих групп
        if len(groups_data) < 2:
            await message.answer(
                "❌ <b>Не удалось получить данные для сравнения</b>\n\n"
                f"Успешно проанализировано: {len(groups_data)} из 2 групп\n"
                f"Группы: {', '.join(successful_groups) if successful_groups else 'нет'}"
            )
            return
        
        # Сравниваем аудитории
        comparison = await analyzer.compare_audiences(
            groups_data[0]['analysis'],
            groups_data[1]['analysis']
        )
        
        # Формируем отчет сравнения
        report = f"📊 <b>СРАВНЕНИЕ АУДИТОРИЙ</b>\n\n"
        report += f"1️⃣ <b>{groups_data[0]['info']['name']}</b>\n"
        report += f"2️⃣ <b>{groups_data[1]['info']['name']}</b>\n\n"
        
        # Индикатор сходства
        similarity = comparison['similarity_score']
        if similarity >= 80:
            similarity_emoji = "🔴"
            similarity_text = "ОЧЕНЬ ВЫСОКОЕ"
        elif similarity >= 60:
            similarity_emoji = "🟠"
            similarity_text = "ВЫСОКОЕ"
        elif similarity >= 40:
            similarity_emoji = "🟡"
            similarity_text = "СРЕДНЕЕ"
        elif similarity >= 20:
            similarity_emoji = "🟢"
            similarity_text = "НИЗКОЕ"
        else:
            similarity_emoji = "🔵"
            similarity_text = "ОЧЕНЬ НИЗКОЕ"
        
        report += f"📈 <b>СХОДСТВО АУДИТОРИЙ: {similarity}%</b> {similarity_emoji}\n"
        report += f"<i>({similarity_text} сходство)</i>\n\n"
        
        # Общие характеристики
        if comparison['common_characteristics']:
            report += "<b>🔗 ОБЩИЕ ХАРАКТЕРИСТИКИ:</b>\n"
            for char in comparison['common_characteristics']:
                report += f"• {char}\n"
        else:
            report += "<i>⚠️ Значительных общих характеристик не обнаружено</i>\n"
        
        await message.answer(report)
        
        # Дополнительная аналитика
        additional = "<b>📋 СВОДКА ПО ГРУППАМ:</b>\n\n"
        
        for i, group in enumerate(groups_data, 1):
            analysis = group['analysis']
            additional += f"<b>Группа {i} — {group['info']['name']}:</b>\n"
            
            if 'gender' in analysis:
                main_gender = "М" if analysis['gender'].get('male', 0) > analysis['gender'].get('female', 0) else "Ж"
                additional += f"• Преобладающий пол: {main_gender}\n"
            
            if 'age_groups' in analysis:
                main_age = max(analysis['age_groups'].items(), key=lambda x: x[1])[0]
                additional += f"• Основная возрастная группа: {main_age}\n"
            
            additional += "\n"
        
        await message.answer(additional)
        
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
                report += f"{i}. {analysis['group_name']} — {analysis['created_at']}\n"
        else:
            report += "\n<i>У вас пока нет сохраненных анализов.</i>\n"
            report += "<i>Используйте команду /analyze для первого анализа!</i>"
        
        await message.answer(report)
        
    except Exception as e:
        logger.error(f"Ошибка в команде /stats: {e}", exc_info=True)
        await message.answer("❌ <b>Ошибка при получении статистики.</b> Попробуйте позже.")

@dp.message(Command("test_vk"))
async def cmd_test_vk(message: Message):
    """Тестирование подключения к VK API (только для администраторов)"""
    # Проверка прав администратора
    if message.from_user.id not in config.ADMIN_IDS:
        await message.answer(
            "❌ <b>Эта команда доступна только администраторам</b>\n\n"
            f"Ваш ID: {message.from_user.id}\n"
            f"Администраторы: {', '.join(map(str, config.ADMIN_IDS))}"
        )
        return
    
    await message.answer("🔍 <b>Запускаю тестирование подключения к VK API...</b>")
    
    try:
        result = await vk_client.test_connection()
        
        if result['success']:
            report = "✅ <b>ТЕСТИРОВАНИЕ ПРОЙДЕНО УСПЕШНО</b>\n\n"
            report += f"{result['message']}\n\n"
            
            if 'details' in result:
                report += "<b>Детали тестов:</b>\n"
                for detail in result['details']:
                    status = "✅" if detail['success'] else "❌"
                    # Убираем лишние переносы строк для читаемости в Telegram
                    message_text = detail['message'].replace('\n', ' ')
                    report += f"{status} <b>{detail['test']}:</b> {message_text}\n"
            
            report += f"\n<b>Конфигурация VK API:</b>\n"
            report += f"• Версия API: {config.VK_API_VERSION}\n"
            report += f"• Задержка между запросами: {config.REQUEST_DELAY:.2f}с\n"
            report += f"• Токен: {'✅ Установлен' if config.VK_SERVICE_TOKEN else '❌ Отсутствует'}\n"
            report += f"• Таймаут запросов: {config.VK_API_TIMEOUT}с\n"
            
            await message.answer(report)
            
            # Предложение протестировать на реальной группе
            await message.answer(
                "💡 <b>Проверьте работу на реальной группе:</b>\n"
                "<code>/analyze https://vk.com/public1</code>\n"
                "Или: <code>/analyze https://vk.com/club1</code>"
            )
            
        else:
            report = "❌ <b>ПРОБЛЕМЫ С ПОДКЛЮЧЕНИЕМ К VK API</b>\n\n"
            report += f"{result['message']}\n\n"
            
            if 'details' in result:
                report += "<b>Результаты тестов:</b>\n"
                for detail in result['details']:
                    status = "✅" if detail['success'] else "❌"
                    message_text = detail['message'].replace('\n', ' ')
                    report += f"{status} <b>{detail['test']}:</b> {message_text}\n"
            
            report += "\n<b>Возможные причины:</b>\n"
            report += "1. Неверный или просроченный VK_SERVICE_TOKEN\n"
            report += "2. Группа заблокирована (banned) в ВК\n"
            report += "3. Ограничения приложения VK\n"
            report += "4. Проблемы с сетью или блокировки\n"
            report += "5. Превышение лимитов API\n\n"
            report += "<b>Рекомендации:</b>\n"
            report += "1. Проверьте токен в настройках Railway\n"
            report += "2. Убедитесь, что приложение VK активно\n"
            report += "3. Проверьте права доступа приложения\n"
            report += "4. Попробуйте создать новый сервисный ключ\n"
            report += "5. Попробуйте проанализировать другую группу\n"
            
            await message.answer(report)
            
    except Exception as e:
        logger.error(f"Ошибка тестирования VK: {e}", exc_info=True)
        await message.answer(
            f"❌ <b>Критическая ошибка тестирования:</b>\n\n"
            f"{str(e)[:200]}\n\n"
            "<i>Проверьте логи бота для подробной информации.</i>"
        )

# ==================== ОСНОВНАЯ ФУНКЦИЯ ====================

async def main():
    """Основная функция запуска бота"""
    logger.info("=" * 60)
    logger.info("ЗАПУСК ТЕЛЕГРАМ БОТА ДЛЯ АНАЛИЗА АУДИТОРИИ ВК")
    logger.info("=" * 60)
    
    try:
        # Инициализация базы данных
        logger.info("Инициализация базы данных...")
        db_success = await db.init_db()
        
        if db_success:
            logger.info("✅ База данных подключена успешно")
        else:
            logger.warning("⚠️  Бот запущен с временной SQLite базой. Данные могут быть не сохранены!")
        
        # Получение информации о боте
        bot_info = await bot.get_me()
        logger.info(f"🤖 Бот: @{bot_info.username} (ID: {bot_info.id})")
        logger.info(f"👥 Администраторы: {config.ADMIN_IDS}")
        logger.info(f"🌐 VK API Версия: {config.VK_API_VERSION}")
        
        # === ВАЖНО: Сбрасываем вебхук на случай остаточных состояний ===
        try:
            await bot.delete_webhook(drop_pending_updates=True)
            logger.info("✅ Вебхук сброшен, старые обновления удалены")
        except Exception as e:
            logger.warning(f"При сбросе вебхука: {e}")
        
        # Ждем 2 секунды для очистки состояния
        await asyncio.sleep(2)
        
        logger.info("✅ Бот готов к работе! Ожидание команд...")
        logger.info("-" * 60)
        
        # Запуск бота с пропуском старых обновлений
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
