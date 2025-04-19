from telegram.ext import Application, MessageHandler, CommandHandler, filters
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import threading

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Вставьте ваш токен от BotFather
TOKEN = '719458062:AAGbrrY21H86FiagYOm4CaevbYqeHdk8'
# Вставьте ваш Telegram ID
CREATOR_ID = 1321220840
# Вставьте ID группы
GROUP_CHAT_ID = -180025934882

# Создаём Application
application = Application.builder().token(TOKEN).build()

# Порт для HTTP-сервера
PORT = 8080

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
                application.update_queue.put(update),
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
    server = HTTPServer(("", PORT), TelegramWebhookHandler)
    logger.info(f"Запущен HTTP-сервер для вебхуков на порту {PORT}")
    server.serve_forever()

# Функция для отправки периодического сообщения
async def send_periodic_message(context):
    if not context.application.running:
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

async def main():
    # Добавляем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler((filters.TEXT | filters.PHOTO) & filters.ChatType.PRIVATE, forward_message))
    application.add_error_handler(error_handler)

    # Проверяем, доступен ли JobQueue
    if application.job_queue is None:
        logger.error("JobQueue не доступен! Установите python-telegram-bot[job-queue]")
    else:
        application.job_queue.run_once(on_startup, 0)

    # Запускаем бота
    await application.initialize()
    await application.start()

    # Получаем URL от Render
    # Замените YOUR_SERVICE_NAME на имя вашего сервиса (например, mytelegrambot)
    webhook_url = "https://mytelegrambot.onrender.com/webhook"
    await application.bot.set_webhook(webhook_url)
    logger.info(f"Установлен вебхук: {webhook_url}")

    # Запускаем HTTP-сервер в отдельном потоке
    threading.Thread(target=run_webhook_server, daemon=True).start()

    logger.info("Бот запущен, жду обновлений через вебхуки...")

    # Держим приложение запущенным
    while True:
        await asyncio.sleep(3600)  # Спим 1 час, чтобы не завершать приложение

if __name__ == '__main__':
    # Создаём цикл событий
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        logger.info("Останавливаем бота...")
        loop.run_until_complete(application.stop())
        loop.run_until_complete(application.bot.delete_webhook())
        logger.info("Вебхук удалён")
    finally:
        loop.close()
        logger.info("Цикл событий закрыт")
