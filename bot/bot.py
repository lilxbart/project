import logging
from telegram import Update, ForceReply, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
import psycopg2
import requests

#логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levellevel)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

#подключение к БД
def connect_db():
    return psycopg2.connect(
        dbname="work",
        user="postgres",
        password="89168117733",
        host="host.docker.internal"
    )

#проверка наличия вакансии в БД
def vacancy_exists(cursor, vacancy_id):
    cursor.execute("SELECT 1 FROM vacancies WHERE id = %s", (vacancy_id,))
    return cursor.fetchone() is not None

#вставка данных в таблицу
def insert_vacancy(cursor, vacancy):
    if not vacancy_exists(cursor, vacancy['id']):
        cursor.execute("""
            INSERT INTO vacancies (id, title, skills, work_format, salary, location, experience_level)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            vacancy['id'],
            vacancy['name'],
            ', '.join([skill['name'] for skill in vacancy['key_skills']]),
            vacancy['employment']['name'],
            vacancy['salary']['from'] if vacancy['salary'] else None,
            vacancy['area']['name'],
            vacancy['experience']['name']
        ))
    else:
        logger.info(f"Vacancy {vacancy['id']} already exists in the database.")

#парсинг
def parse_hh_vacancies(query, area):
    url = 'https://api.hh.ru/vacancies'
    params = {
        'text': query,
        'area': area,  #ID города
        'per_page': 10
    }

    response = requests.get(url, params=params)
    data = response.json()

    conn = connect_db()
    cursor = conn.cursor()

    for item in data['items']:
        vacancy_details = requests.get(item['url']).json()
        insert_vacancy(cursor, vacancy_details)

    conn.commit()
    cursor.close()
    conn.close()
    logger.info(f"Parsed and inserted vacancies for query '{query}' in area '{area}'")

#/start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await update.message.reply_markdown_v2(
        fr'Привет, {user.mention_markdown_v2()}\! Используйте команду /help для получения списка доступных команд.',
        reply_markup=ForceReply(selective=True),
    )
    logger.info("Команда /start обработана")

#/help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        'Доступные команды:\n/start - Начать диалог\n/help - Помощь\n/search - Поиск вакансий\n/info - Информация о боте\n/filters - Установить фильтры\n/reset_filters - Сбросить фильтры\n/set_city - Установить город поиска')
    logger.info("Команда /help обработана")

#/search
async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text('Введите название должности для поиска вакансий:')
    logger.info("Команда /search обработана")

#/info
async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        'Этот бот предназначен для поиска вакансий. Используйте следующие команды для взаимодействия с ботом:\n'
        '/start - Начать диалог\n'
        '/help - Получить список команд\n'
        '/search - Начать поиск вакансий\n'
        '/info - Получить информацию о боте\n'
        '/filters - Установить фильтры\n'
        '/reset_filters - Сбросить фильтры\n'
        '/set_city - Установить город поиска'
    )
    logger.info("Команда /info обработана")

#/filters
async def filters_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("Установить фильтры", callback_data='set_filters')],
        [InlineKeyboardButton("Сбросить фильтры", callback_data='reset_filters')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('Нажмите кнопку ниже, чтобы установить или сбросить фильтры:', reply_markup=reply_markup)
    logger.info("Команда /filters обработана")

#/set_city
async def set_city_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("Москва", callback_data='set_city_1')],
        [InlineKeyboardButton("Санкт-Петербург", callback_data='set_city_2')],
        [InlineKeyboardButton("Екатеринбург", callback_data='set_city_3')],
        [InlineKeyboardButton("Сбросить город", callback_data='reset_city')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('Нажмите кнопку ниже, чтобы выбрать город для поиска:', reply_markup=reply_markup)
    logger.info("Команда /set_city обработана")

#обработка нажатия кнопок для фильтров и города
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    if query.data == 'set_filters':
        await query.edit_message_text(text="Введите минимальную зарплату и тип занятости (Полная занятость/Частичная занятость/Стажировка):")
        context.user_data['setting_filters'] = True
    elif query.data == 'reset_filters':
        context.user_data.pop('min_salary', None)
        context.user_data.pop('employment_type', None)
        await query.edit_message_text(text="Фильтры сброшены.")
        logger.info("Фильтры сброшены пользователем")
    elif query.data.startswith('set_city'):
        city_id = int(query.data.split('_')[-1])
        context.user_data['city'] = city_id  # Устанавливаем новый город
        await query.edit_message_text(text=f"Город поиска установлен: {context.user_data['city']}")
        logger.info(f"Город поиска установлен: {context.user_data['city']}")
    elif query.data == 'reset_city':
        context.user_data.pop('city', None)
        await query.edit_message_text(text="Город поиска сброшен.")
        logger.info("Город поиска сброшен пользователем")

#обработка текста
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_text = update.message.text

    if context.user_data.get('setting_filters'):
        try:
            min_salary, employment_type = user_text.split(maxsplit=1)
            context.user_data['min_salary'] = int(min_salary)
            context.user_data['employment_type'] = employment_type
            context.user_data['setting_filters'] = False
            await update.message.reply_text(f'Фильтры установлены: минимальная зарплата - {min_salary}, тип занятости - {employment_type}')
            logger.info("Фильтры установлены пользователем")
        except ValueError:
            await update.message.reply_text('Ошибка: пожалуйста, введите минимальную зарплату и тип занятости в формате "100000 Полная занятость".')
            return
    else:
        if user_text.startswith('/'):
            return
        await update.message.reply_text(f'Ищу вакансии по запросу: {user_text}')

        #арсинг
        city = context.user_data.get('city', 1)  # По умолчанию Москва (ID = 1)
        parse_hh_vacancies(user_text, city)

        #поиск в БД и отправка результатов пользователю с фильтром
        min_salary = context.user_data.get('min_salary')
        employment_type = context.user_data.get('employment_type')
        vacancies = search_vacancies(user_text, min_salary, employment_type, city)
        total_vacancies = len(vacancies)

        await update.message.reply_text(f'Найдено {total_vacancies} вакансий по запросу: {user_text}')

        if vacancies:
            for vacancy in vacancies:
                await update.message.reply_text(format_vacancy(vacancy))
        else:
            await update.message.reply_text('Вакансий не найдено.')
        logger.info(f"Сообщение '{user_text}' обработано")

#поиск вакансий в БД с учётом фильтров
def search_vacancies(job_title, min_salary=None, employment_type=None, city=None):
    conn = connect_db()
    cursor = conn.cursor()
    query = """
        SELECT title, skills, work_format, salary, location, experience_level
        FROM vacancies
        WHERE title ILIKE %s
    """
    params = [f'%{job_title}%']

    if min_salary is not None:
        query += " AND CAST(salary AS INTEGER) >= %s"
        params.append(min_salary)
    if employment_type is not None:
        query += " AND work_format ILIKE %s"
        params.append(f'%{employment_type}%')
    if city is not None:
        query += " AND location ILIKE %s"
        city_name = {
            1: 'Москва',
            2: 'Санкт-Петербург',
            3: 'Екатеринбург'
        }.get(city, 'Москва')
        params.append(f'%{city_name}%')

    cursor.execute(query, params)
    results = cursor.fetchall()
    cursor.close()
    conn.close()
    logger.info(f"Search query executed: found {len(results)} vacancies for query '{job_title}' with filters salary >= {min_salary}, employment = {employment_type}, city = {city_name}")
    return results

#форматирование информации о вакансии
def format_vacancy(vacancy):
    title, skills, work_format, salary, location, experience_level = vacancy
    return (f"Название: {title}\n"
            f"Навыки: {skills}\n"
            f"Формат работы: {work_format}\n"
            f"Зарплата: {salary}\n"
            f"Локация: {location}\n"
            f"Уровень опыта: {experience_level}\n")

async def set_commands(application):
    commands = [
        BotCommand("start", "Начать диалог"),
        BotCommand("help", "Помощь"),
        BotCommand("search", "Поиск вакансий"),
        BotCommand("info", "Информация о боте"),
        BotCommand("filters", "Установить фильтры"),
        BotCommand("reset_filters", "Сбросить фильтры"),
        BotCommand("set_city", "Установить город поиска")
    ]
    await application.bot.set_my_commands(commands)
    logger.info("Команды установлены")

def main():
    #Application и диспетчера
    application = Application.builder().token("6833575364:AAFxAHB7D2q1lrTNpguGcN8LbNKNv3H9Fs8").build()

    #установка команд в меню
    application.add_handler(CommandHandler('set_commands', set_commands))

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("search", search_command))
    application.add_handler(CommandHandler("info", info_command))
    application.add_handler(CommandHandler("filters", filters_command))
    application.add_handler(CommandHandler("reset_filters", filters_command))
    application.add_handler(CommandHandler("set_city", set_city_command))

    application.add_handler(CallbackQueryHandler(button))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    application.job_queue.run_once(set_commands, when=0)

    application.run_polling()
    logger.info("Бот запущен")

if __name__ == '__main__':
    main()
