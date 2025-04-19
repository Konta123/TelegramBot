from telegram.ext import Application, MessageHandler, CommandHandler, filters
import logging
import asyncio
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Вставьте ваш токен от BotFather
TOKEN = '7119450062:AAGbrry2lh86F1qajgvOm4Cbaevhq0eHkd8'
# Вставьте ваш Telegram ID
CREATOR_ID = 1321220840
# Вставьте ID группы
GROUP_CHAT_ID = -1002250348882

# Простой HTTP-сервер для Render
class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot is running")

def run_dummy_server():
    server = HTTPServer(("", 8080), DummyHandler)
    logger.info("Запущен HTTP-сервер на порту 8080")
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

async def shutdown(application):
    logger.info("Останавливаем бота...")
    try:
        if application.job_queue:
            application.job_queue.stop()
            logger.info("JobQueue остановлен")
        await application.stop()
        logger.info("Application остановлен")
        await application.bot.close()
        logger.info("Bot закрыт")
    except Exception as e:
        logger.error(f"Ошибка при остановке бота: {e}")

async def main():
    # Запускаем HTTP-сервер в отдельном потоке
    threading.Thread(target=run_dummy_server, daemon=True).start()

    # Создаём Application
    application = Application.builder().token(TOKEN).build()
    
    # Добавляем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler((filters.TEXT | filters.PHOTO) & filters.ChatType.PRIVATE, forward_message))
    application.add_error_handler(error_handler)

    # Проверяем, доступен ли JobQueue
    if application.job_queue is None:
        logger.error("JobQueue не доступен! Установите python-telegram-bot[job-queue]")
    else:
        application.job_queue.run_once(on_startup, 0)

    logger.info("Бот запущен, жду сообщений...")
    try:
        await application.run_polling(allowed_updates=["message"], stop_signals=[])
    except Exception as e:
        logger.error(f"Ошибка в run_polling: {e}")
        raise
    finally:
        await shutdown(application)

if __name__ == '__main__':
    while True:
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(main())
        except Exception as e:
            logger.error(f"Бот упал с ошибкой: {e}. Перезапускаю...")
            import time
            time.sleep(10)
        finally:
            loop.close()
