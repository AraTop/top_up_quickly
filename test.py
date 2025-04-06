import requests
import logging
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackContext,
    CallbackQueryHandler,
    ConversationHandler,
    filters
)
from yookassa import Configuration, Payment
import asyncio
from datetime import datetime

# Настройки
API_KEY = "e1f2ef350da0032b567b66a7c36e509e"
BOT_TOKEN = "8197845963:AAGS9dWU2QNr4NIo_TfqWvmmkHXUuXT2QsE"
YKASSA_SHOP_ID = 1066265
YKASSA_SECRET_KEY = "test_ha5ciX5g5F5ECL6qqgEM9cd5PFvD8mPuXU-9ov3BwSc"
BALANCE_API_URL = 'https://balancesteam.ru/api/v2/partner/balance'
CHECK_API_URL = 'https://balancesteam.ru/api/v2/partner/check'
CREATE_ORDER_URL = 'https://balancesteam.ru/api/v2/partner/create'

# Инициализация YooKassa
Configuration.account_id = YKASSA_SHOP_ID
Configuration.secret_key = YKASSA_SECRET_KEY

# Этапы
CHOOSE_CURRENCY, GET_LOGIN, GET_AMOUNT, CONFIRMATION = range(4)

# Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Проверка баланса
def check_balance(apikey):
    response = requests.post(BALANCE_API_URL, data={'apikey': apikey})
    return response.json()

# Проверка Steam логина
def check_steam_login(apikey, steam_login):
    response = requests.post(CHECK_API_URL, data={'apikey': apikey, 'login_or_email': steam_login, 'service_id': 5955})
    return response.json()

# Создание заказа через API balancesteam.ru
def create_order(apikey, steam_login, amount):
    response = requests.post(CREATE_ORDER_URL, data={
        'apikey': apikey,
        'login_or_email': steam_login,
        'service_id': 5955,
        'amount': amount
    })
    return response.json()

# Создание ссылки на оплату через YooKassa
def create_payment_ykassa(amount, steam_login):
    commission = calculate_commission(amount)
    total = round(amount + commission, 2)

    payment_data = {
        'amount': {
            'value': total,
            'currency': 'RUB'
        },
        'capture_mode': 'AUTOMATIC',
        'payment_method': 'BANK_CARD',
        'description': f"Пополнение Steam для {steam_login}",
        'confirmation': {
            'type': 'redirect',
            'return_url': 'https://t.me/testolki_bot'  # Укажите URL для возврата после оплаты
        }
    }

    # Создаем платеж через API YooKassa
    payment = Payment.create(payment_data)

    # Возвращаем URL для перенаправления на страницу оплаты
    return payment.confirmation.confirmation_url, payment.id

# Комиссия
def calculate_commission(amount):
    return round(amount * 0.08, 2)  # 8% комиссия

# /start
async def start(update: Update, context: CallbackContext):
    # Сброс всех пользовательских данных
    context.user_data.clear()

    if update.callback_query:
        user_name = update.callback_query.from_user.first_name
        text = f"👋 Привет, {user_name}!\n\nВыберите, опцию:"
        keyboard = [
            [InlineKeyboardButton("💰 Пополнить Steam", callback_data='topup')],
        ]
        await update.callback_query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        user_name = update.effective_user.first_name
        text = f"👋 Привет, {user_name}!\n\nВыберите, опцию:"
        keyboard = [
            [InlineKeyboardButton("💰 Пополнить Steam", callback_data='topup')],
        ]
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

# Нажата кнопка Пополнить Steam
async def topup_handler(update: Update, context: CallbackContext):
    await update.callback_query.answer()
    keyboard = [
        [InlineKeyboardButton("🇷🇺 RUB", callback_data='currency_rub')],
        [InlineKeyboardButton("🇺🇸 USD (временно недоступно)", callback_data='currency_usd_disabled')],
    ]
    await update.callback_query.edit_message_text("🌍 Выберите валюту:", reply_markup=InlineKeyboardMarkup(keyboard))
    return CHOOSE_CURRENCY

# Обработка валюты
async def currency_chosen(update: Update, context: CallbackContext):
    await update.callback_query.answer()
    if update.callback_query.data == 'currency_rub':
        context.user_data['currency'] = 'RUB'
        await update.callback_query.edit_message_text("🧾 Введите ваш Steam логин:")
        return GET_LOGIN
    else:
        await update.callback_query.edit_message_text("❌ USD пока не поддерживается.")
        return ConversationHandler.END

# Обработка логина
async def get_login(update: Update, context: CallbackContext):
    steam_login = update.message.text
    result = check_steam_login(API_KEY, steam_login)

    if not result.get("status"):
        await update.message.reply_text("🚫 Логин недействителен. Попробуйте снова.")
        return GET_LOGIN

    context.user_data['steam_login'] = steam_login

    keyboard = [
        [
            InlineKeyboardButton("100", callback_data='amount_100'),
            InlineKeyboardButton("200", callback_data='amount_200'),
            InlineKeyboardButton("500", callback_data='amount_500'),
        ],
        [
            InlineKeyboardButton("1000", callback_data='amount_1000'),
            InlineKeyboardButton("2000", callback_data='amount_2000'),
            InlineKeyboardButton("5000", callback_data='amount_5000'),
        ]
    ]
    await update.message.reply_text("💵 Выберите сумму пополнения или введите свою (не меньше 100₽):", reply_markup=InlineKeyboardMarkup(keyboard))
    return GET_AMOUNT

# Ввод суммы через кнопку
async def amount_button_handler(update: Update, context: CallbackContext):
    await update.callback_query.answer()
    amount = int(update.callback_query.data.replace("amount_", ""))
    context.user_data['amount'] = amount
    return await show_confirmation(update.callback_query.message, context)

# Ввод суммы вручную
async def amount_text_handler(update: Update, context: CallbackContext):
    try:
        amount = float(update.message.text)
        if amount < 100:
            raise ValueError
    except ValueError:
        await update.message.reply_text("🚫 Введите корректную сумму от 100₽.")
        return GET_AMOUNT

    context.user_data['amount'] = amount
    return await show_confirmation(update.message, context)

# Подтверждение перед оплатой
async def show_confirmation(target, context):
    amount = context.user_data['amount']
    login = context.user_data['steam_login']
    commission = calculate_commission(amount)
    total = round(amount + commission, 2)

    text = (
        f"🧾 Проверьте данные перед оплатой:\n\n"
        f"👤 Логин: {login}\n"
        f"💰 Сумма на Steam: {amount}₽\n"
        f"🧾 Комиссия: {commission}₽\n"
        f"💳 Итого к оплате: {total}₽"
    )
    keyboard = [
        [InlineKeyboardButton("✅ Подтвердить", callback_data='confirm')],
        [InlineKeyboardButton("❌ Отменить", callback_data='cancel')],
    ]
    await target.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    return CONFIRMATION

def transfer_to_steam(amount, login):
    response = requests.post(
        "https://balancesteam.ru/api/v2/partner/create",
        data={
            "apikey": API_KEY,
            "login_or_email": login,
            "service_id": 5955,
            "amount": amount
        }
    )
    data = response.json()
    if not data.get("error"):
        print(f"🟢 Заказ успешно создан! ID заказа: {data.get('id')}")
        return True
    else:
        print(f"🔴 Ошибка при создании заказа: {data.get('message')}")
        return False

# Асинхронная проверка статуса платежа
async def check_payment_status(payment_id, amount, query, login):
    print("Начинаем проверку статуса платежа...")
    while True:
        try:
            updated_payment = Payment.find_one(payment_id)
            print(f"Платеж с ID {payment_id} получен. Статус: {updated_payment.status}")
            
            if updated_payment.status == "succeeded":
                print("Оплата успешна.")
                # Оплата успешна, переводим деньги на Steam
                result = transfer_to_steam(amount, login)  # Это ваш код для перевода средств на Steam
                print(result)
                if result:
                    await query.edit_message_text(
                        f"💸 Деньги поступили! 🎉 Ожидайте, пожалуйста, поступление на ваш баланс Steam. ⏳",
                    )
                else:
                    await query.edit_message_text(
                    "⚠️ Упс! Что-то пошло не так при пополнении баланса Steam.\n"
                    "🔄 Попробуйте снова чуть позже.\n\n"
                    "💬 Если проблема повторяется — свяжитесь с администратором для помощи. 🙏"
                )
                break

            elif updated_payment.status == "canceled":
                print("Оплата была отменена.")
                # Оплата была отменена
                await query.edit_message_text(
                    f"❌ Оплата была отменена. Попробуйте снова! 💡",
                )
                break
            else:
                # Если статус еще не определен, ждем некоторое время перед следующей проверкой
                print("Оплата еще не завершена, повторная проверка через 10 секунд.")
                await asyncio.sleep(10)
        except Exception as e:
            print(f"Ошибка при проверке статуса платежа: {e}")
            await asyncio.sleep(10)  # Если ошибка, попробуем снова через 10 секунд

# Подтверждение / отмена
# Обработчик подтверждения от пользователя
async def confirmation_handler(update: Update, context: CallbackContext):
    await update.callback_query.answer()

    if update.callback_query.data == 'confirm':
        amount = context.user_data['amount']
        login = context.user_data['steam_login']
        
        # Создаем платеж и получаем ссылку на оплату
        payment_url, payment_id = create_payment_ykassa(amount, login)

        # Сохраняем ID платежа в user_data для дальнейшей проверки
        context.user_data['payment_id'] = payment_id

        # Отправляем ссылку на оплату
        await update.callback_query.edit_message_text(f"🔗 Перейдите по ссылке для оплаты:\n{payment_url}")
        
        # Запускаем асинхронную задачу для проверки статуса платежа
        asyncio.create_task(check_payment_status(payment_id, amount, update.callback_query, login))

    else:
        await update.callback_query.edit_message_text("🚫 Операция отменена. Возврат в главное меню.")
        await start(update, context)

    return ConversationHandler.END

# Отмена
async def cancel(update: Update, context: CallbackContext):
    await update.message.reply_text("❌ Операция отменена. Возврат в меню.")
    await start(update, context)
    return ConversationHandler.END

# Основной запуск
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(topup_handler, pattern='^topup$')],
        states={
            CHOOSE_CURRENCY: [CallbackQueryHandler(currency_chosen)],
            GET_LOGIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_login)],
            GET_AMOUNT: [
                CallbackQueryHandler(amount_button_handler, pattern='^amount_'),
                MessageHandler(filters.TEXT & ~filters.COMMAND, amount_text_handler),
            ],
            CONFIRMATION: [CallbackQueryHandler(confirmation_handler, pattern='^(confirm|cancel)$')],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv)
    app.run_polling()

if __name__ == "__main__":
    main()
