import logging
from telegram import Update, ForceReply, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import psycopg2
import requests

#логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

#подключение к бд
def connect_db():
    return psycopg2.connect(
        dbname="work",
        user="postgres",
        password="89168117733",
        host="host.docker.internal"
    )

#наличия вакансии в бд
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

#парсинг с hh.ru
def parse_hh_vacancies(query, salary_from=None, salary_to=None, employment=None):
    url = 'https://api.hh.ru/vacancies'
    params = {
        'text': query,
        'area': 1,
        'per_page': 10
    }
    if salary_from:
        params['salary_from'] = salary_from
    if salary_to:
        params['salary_to'] = salary_to
    if employment:
        params['employment'] = employment

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
        'Доступные команды:\n/start - Начать диалог\n/help - Помощь\n/search - Поиск вакансий\n/info - Информация о боте')
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
        '/info - Получить информацию о боте'
    )
    logger.info("Команда /info обработана")

#обработка текста
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_text = update.message.text
    if user_text.startswith('/'):
        return

    salary_from = None
    salary_to = None
    employment = None

    if 'salary_from:' in user_text:
        salary_from = int(user_text.split('salary_from:')[1].split()[0])
    if 'salary_to:' in user_text:
        salary_to = int(user_text.split('salary_to:')[1].split()[0])
    if 'employment:' in user_text:
        employment = user_text.split('employment:')[1].split()[0]

    query = user_text.split('salary_from:')[0].split('salary_to:')[0].split('employment:')[0].strip()

    await update.message.reply_text(
        f'Ищу вакансии по запросу: {query}, Зарплата от: {salary_from}, Зарплата до: {salary_to}, Занятость: {employment}')



    #парсинг
    parse_hh_vacancies(query, salary_from, salary_to, employment)

    #поиск в бд и отправка результатов пользователю
    vacancies = search_vacancies(query, salary_from, salary_to, employment)
    total_vacancies = len(vacancies)
    await update.message.reply_text(f'Найдено {total_vacancies} вакансий по запросу: {query}')

    if vacancies:
        for vacancy in vacancies:
            await update.message.reply_text(format_vacancy(vacancy))
    else:
        await update.message.reply_text('Вакансий не найдено.')
    logger.info(f"Сообщение '{user_text}' обработано")

#поиск вакансий в бд
def search_vacancies(job_title, salary_from=None, salary_to=None, employment=None):
    conn = connect_db()
    cursor = conn.cursor()

    query = """
        SELECT title, skills, work_format, salary, location, experience_level
        FROM vacancies
        WHERE title ILIKE %s
    """
    params = [f'%{job_title}%']

    if salary_from is not None:
        query += " AND salary >= %s"
        params.append(salary_from)
    if salary_to is not None:
        query += " AND salary <= %s"
        params.append(salary_to)
    if employment is not None:
        query += " AND work_format = %s"
        params.append(employment)

    cursor.execute(query, tuple(params))
    results = cursor.fetchall()
    cursor.close()
    conn.close()
    return results

#инф. о  вакансии
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
        BotCommand("info", "Информация о боте")
    ]
    await application.bot.set_my_commands(commands)
    logger.info("Команды установлены")

def main():
    #аpplication и диспетчера
    application = Application.builder().token("6833575364:AAFxAHB7D2q1lrTNpguGcN8LbNKNv3H9Fs8").build()

    #установка команд в меню
    application.add_handler(CommandHandler('set_commands', set_commands))

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("search", search_command))
    application.add_handler(CommandHandler("info", info_command))

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    application.job_queue.run_once(set_commands, when=0)

    application.run_polling()
    logger.info("Бот запущен")

if __name__ == '__main__':
    main()
