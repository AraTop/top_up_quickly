import requests
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackContext,
    CallbackQueryHandler,
    ConversationHandler,
    filters
)

# Настройки
API_KEY = "e1f2ef350da0032b567b66a7c36e509e"
BOT_TOKEN = "7382197547:AAFTXmXfoSCQCBF937nzXffGBMXAbRLyGc4"

# Состояния диалога
GET_LOGIN, GET_AMOUNT, CONFIRMATION = range(3)

# Настройка логгирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Функции для работы с API
def check_balance(apikey):
    url = "https://balancesteam.ru/api/v2/partner/balance"
    payload = {'apikey': apikey}
    response = requests.post(url, data=payload)
    return response.json()

def check_steam_login(apikey, steam_login):
    url = "https://balancesteam.ru/api/v2/partner/check"
    payload = {
        'apikey': apikey,
        'login_or_email': steam_login,
        'service_id': 5955
    }
    response = requests.post(url, data=payload)
    return response.json()

def create_order(apikey, steam_login, amount):
    url = "https://balancesteam.ru/api/v2/partner/create"
    payload = {
        'apikey': apikey,
        'login_or_email': steam_login,
        'service_id': 5955,
        'amount': amount
    }
    response = requests.post(url, data=payload)
    return response.json()

# Обработчики команд
async def start(update: Update, context: CallbackContext):
    await update.message.reply_text(
        "Привет! Я бот для пополнения баланса Steam. "
        "Отправь команду /topup чтобы начать."
    )

async def topup(update: Update, context: CallbackContext):
    await update.message.reply_text("Введите ваш Steam логин:")
    return GET_LOGIN

async def get_login(update: Update, context: CallbackContext):
    context.user_data['steam_login'] = update.message.text
    await update.message.reply_text("Введите сумму пополнения (например: 100, 500, 1000):")
    return GET_AMOUNT

async def get_amount(update: Update, context: CallbackContext):
    try:
        amount = float(update.message.text)
        if amount <= 0:
            raise ValueError
        context.user_data['amount'] = amount
    except ValueError:
        await update.message.reply_text("Пожалуйста, введите корректную сумму (число больше 0).")
        return GET_AMOUNT
    
    login_check = check_steam_login(API_KEY, context.user_data['steam_login'])
    if login_check.get('error') or not login_check.get('status'):
        await update.message.reply_text("Ошибка: неверный логин или региональные ограничения.")
        return ConversationHandler.END
    
    balance = check_balance(API_KEY)
    if balance.get('error') or balance.get('balance', 0) < amount:
        await update.message.reply_text("Ошибка: недостаточно средств на балансе.")
        return ConversationHandler.END
    
    keyboard = [
        [InlineKeyboardButton("✅ Подтвердить", callback_data='confirm')],
        [InlineKeyboardButton("❌ Отменить", callback_data='cancel')]
    ]
    await update.message.reply_text(
        f"Подтвердите заказ:\nЛогин: {context.user_data['steam_login']}\nСумма: {amount}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CONFIRMATION

async def confirmation(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'confirm':
        order = create_order(
            API_KEY,
            context.user_data['steam_login'],
            context.user_data['amount']
        )
        if order.get('error'):
            await query.edit_message_text("Ошибка при создании заказа!")
        else:
            await query.edit_message_text(f"✅ Заказ #{order.get('id')} создан!")
    else:
        await query.edit_message_text("❌ Заказ отменен.")
    
    return ConversationHandler.END

async def cancel(update: Update, context: CallbackContext):
    await update.message.reply_text("Операция отменена.")
    return ConversationHandler.END

async def error_handler(update: object, context: CallbackContext):
    logger.error("Ошибка: %s", context.error)

def main():
    # Создаем приложение с явным отключением JobQueue
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .job_queue(None)  # Полностью отключаем JobQueue
        .build()
    )
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('topup', topup)],
        states={
            GET_LOGIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_login)],
            GET_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_amount)],
            CONFIRMATION: [CallbackQueryHandler(confirmation)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)
    app.add_error_handler(error_handler)
    
    app.run_polling()

if __name__ == '__main__':
    main()