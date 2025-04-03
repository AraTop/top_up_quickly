from telegram import Update, WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackContext,
    filters  # Важно!
)
import logging
import requests
import json

# Настройка логгирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация
API_KEY = "e1f2ef350da0032b567b66a7c36e509e"
BOT_TOKEN = "7382197547:AAFTXmXfoSCQCBF937nzXffGBMXAbRLyGc4"
WEBAPP_URL = "https://ваш-хостинг.com/webapp/index.html"  # HTTPS обязательно!

async def start(update: Update, context: CallbackContext):
    try:
        await update.message.reply_text(
            text="🎮 <b>Steam Balance Top-Up</b>\n\n"
                 "Нажмите кнопку ниже чтобы пополнить баланс:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    text="✨ Открыть приложение",
                    web_app=WebAppInfo(url=WEBAPP_URL))
            ]])
        )
    except Exception as e:
        logger.error(f"Error in start command: {e}")

async def handle_webapp_data(update: Update, context: CallbackContext):
    try:
        data = json.loads(update.web_app_data.data)
        response = requests.post(
            "https://balancesteam.ru/api/v2/partner/create",
            data={
                'apikey': API_KEY,
                'login_or_email': data['login'],
                'service_id': 5955,
                'amount': data['amount']
            }
        )
        await update.message.reply_text(f"✅ Заказ создан! ID: {response.json().get('id')}")
    except Exception as e:
        logging.error(f"WebApp error: {e}")
        await update.message.reply_text("❌ Ошибка при создании заказа")

def main():
    application = Application.builder().token(BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(
        filters.StatusUpdate.WEB_APP_DATA,
        handle_webapp_data
    ))
    
    logging.info("Бот запущен!")
    application.run_polling()

if __name__ == '__main__':
    main()