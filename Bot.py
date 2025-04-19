from telegram.ext import Application, MessageHandler, CommandHandler, filters
import logging
import json
import threading
import asyncio
from http.server import HTTPServer, BaseHTTPRequestHandler

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Вставьте ваш токен от BotFather
TOKEN = '7119450062:AAGuCqIJLfpUQjeabJEwmKV1mObGhCW1BQw'
# Вставьте ваш Telegram ID
CREATOR_ID = 1321220840
# Вставьте ID группы
GROUP_CHAT_ID = -180025934882

# Порт для HTTP-сервера
PORT = 8080

# Глобальные переменные для HTTP-сервера
httpd = None
httpd_thread = None

# Класс для обработки HTTP-запросов от Telegram
class TelegramWebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            update = json.loads(post_data.decode('utf-8'))
            logger.info(f"Получено обновление: {update}")
            
            # Обрабатываем обновление
            asyncio.run_coroutine_threadsafe(
                application.process_update(update),
                loop=asyncio.get_event_loop()
            )
            
            self.send_response(200)
            self.end_headers()
        except Exception as e:
            logger.error(f"Ошибка при обработке вебхука: {e}")
            self.send_response(500)
            self.end_headers()

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot is running")

# Функция для запуска HTTP-сервера
def run_webhook_server():
    global httpd
    httpd = HTTPServer(("", PORT), TelegramWebhookHandler)
    logger.info(f"Запущен HTTP-сервер для вебхуков на порту {PORT}")
    httpd.serve_forever()

# Функция для остановки HTTP-сервера
def stop_webhook_server():
    global httpd, httpd_thread
    if httpd:
        logger.info("Останавливаем HTTP-сервер...")
        httpd.shutdown()
        httpd.server_close()
        logger.info("HTTP-сервер остановлен")
    if httpd_thread:
        httpd_thread.join()
        logger.info("Поток HTTP-сервера завершён")

# Функция для отправки периодического сообщения
async def send_periodic_message(context):
    application = context.application
    if not application.running:
        logger.warning("Application не запущен, пропускаю отправку сообщения")
        return
    try:
        await context.bot.send_message(
            chat_id=GROUP_CHAT_ID,
            text="Если ты хочешь написать создателю чата или отправить фото для опубликования в группе, напиши этому боту."
        )
        logger.info(f"Отправлено периодическое сообщение в группу {GROUP_CHAT_ID}")
    except Exception as e:
        logger.error(f"Ошибка при отправке периодического сообщения: {e}")
        raise  # Поднимаем исключение для перезапуска

# Callback для настройки периодических задач после запуска
async def on_startup(context):
    if context.job_queue is None:
        logger.error("JobQueue не инициализирован! Установите python-telegram-bot[job-queue]")
        return
    context.job_queue.run_repeating(send_periodic_message, interval=6*60*60, first=10)
    logger.info("Периодические задачи настроены")

async def start(update, context):
    bot_username = context.bot.username
    bot_link = f"https://t.me/{bot_username}"
    await update.message.reply_text(
        f"Я могу пересылать текст или фото создателю чата.\n"
        f"Напиши мне в личный чат! [Перейти в личный чат]({bot_link})",
        parse_mode="Markdown"
    )

async def forward_message(update, context):
    message = update.message
    logger.info(f"Получено сообщение: {message.chat.type}, текст: {message.text}, фото: {message.photo}")

    if message.chat.type == 'private':
        sender_id = message.from_user.id
        sender_name = message.from_user.first_name or "Неизвестный"
        logger.info(f"Сообщение от {sender_name} (ID: {sender_id})")
        
        if message.text:
            logger.info("Получен текст в личном чате, пересылаю")
            await context.bot.send_message(
                chat_id=CREATOR_ID,
                text=f"Сообщение от {sender_name} (ID: {sender_id}):\n{message.text}"
            )
            await message.reply_text("Сообщение отправлено!")
        elif message.photo:
            logger.info("Получено фото в личном чате, пересылаю")
            photo = message.photo[-1]
            await context.bot.send_photo(
                chat_id=CREATOR_ID,
                photo=photo.file_id,
                caption=f"Фото от {sender_name} (ID: {sender_id})"
            )
            await message.reply_text("Фото отправлено!")
        else:
            logger.info("Сообщение не текст и не фото, пропускаю")
            await message.reply_text("Пожалуйста, отправьте текст или фото.")
    else:
        logger.info("Сообщение из группы, игнорирую (кроме команд)")
        return

async def error_handler(update, context):
    logger.error(f"Произошла ошибка: {context.error}")
    if update:
        await context.bot.send_message(
            chat_id=CREATOR_ID,
            text=f"Произошла ошибка: {context.error}"
        )
    raise  # Поднимаем исключение для перезапуска

async def shutdown(application):
    logger.info("Останавливаем бота...")
    try:
        if application.job_queue:
            application.job_queue.stop()
            logger.info("JobQueue остановлен")
        if application.running:
            await application.stop()
            logger.info("Application остановлен")
        bot_session = getattr(application.bot, '_session', None)
        if bot_session and not bot_session.closed:
            await application.bot.close()
            logger.info("Bot закрыт")
        await application.bot.delete_webhook()
        logger.info("Вебхук удалён")
    except Exception as e:
        logger.error(f"Ошибка при остановке бота: {e}")

async def main():
    # Создаём Application
    application = Application.builder().token(TOKEN).build()
    
    # Добавляем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler((filters.TEXT | filters.PHOTO) & filters.ChatType.PRIVATE, forward_message))
    application.add_error_handler(error_handler)

    # Инициализируем приложение
    await application.initialize()
    await application.start()

    # Проверяем, доступен ли JobQueue
    if application.job_queue is None:
        logger.error("JobQueue не доступен! Установите python-telegram-bot[job-queue]")
    else:
        application.job_queue.run_once(on_startup, 0)

    # Устанавливаем вебхук
    webhook_url = "https://mytelegrambot.onrender.com/webhook"
    await application.bot.set_webhook(webhook_url)
    logger.info(f"Установлен вебхук: {webhook_url}")

    # Запускаем HTTP-сервер в отдельном потоке
    global httpd_thread
    httpd_thread = threading.Thread(target=run_webhook_server, daemon=True)
    httpd_thread.start()

    logger.info("Бот запущен, жду обновлений через вебхуки...")
    
    # Держим приложение запущенным
    try:
        while True:
            await asyncio.sleep(3600)  # Спим 1 час
    except asyncio.CancelledError:
        pass
    finally:
        await shutdown(application)

if __name__ == '__main__':
    while True:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(main())
        except Exception as e:
            logger.error(f"Бот упал с ошибкой: {e}. Перезапускаю...")
            import time
            time.sleep(10)
        finally:
            stop_webhook_server()
            pending = asyncio.all_tasks(loop=loop)
            for task in pending:
                task.cancel()
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
            except Exception as e:
                logger.error(f"Ошибка при завершении асинхронных генераторов: {e}")
            try:
                loop.close()
                logger.info("Цикл событий закрыт")
            except Exception as e:
                logger.error(f"Ошибка при закрытии цикла событий: {e}")
