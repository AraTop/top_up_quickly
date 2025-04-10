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
from dotenv import load_dotenv
import os
import asyncpg

load_dotenv()

# Настройки
API_KEY = os.getenv("API_KEY")
BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
YKASSA_SHOP_ID = os.getenv("YKASSA_SHOP_ID")
YKASSA_SECRET_KEY = os.getenv("YKASSA_SECRET_KEY")

ADMINS = [5706003073,2125819462]
BALANCE_API_URL = 'https://balancesteam.ru/api/v2/partner/balance'
CHECK_API_URL = 'https://balancesteam.ru/api/v2/partner/check'
CREATE_ORDER_URL = 'https://balancesteam.ru/api/v2/partner/create'
COMMISSION_RUB = 0.137

async def connect_db():
    return await asyncpg.create_pool(DATABASE_URL)

async def log_steam_topup(telegram_id, username, steam_login, amount, commission):
    pool = await connect_db()

    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO steam_topups (telegram_id, username, steam_login, amount, commission)
            VALUES ($1, $2, $3, $4, $5)
            """,
            telegram_id, username, steam_login, amount, commission
        )
    
    # Закрываем подключение
    await pool.close()

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
def check_steam_login(apikey, steam_login, currency):
    if currency == 'RUB':
        service_id = 5955

    response = requests.post(CHECK_API_URL, data={'apikey': apikey, 'login_or_email': steam_login, 'service_id': service_id})
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
def create_payment_ykassa(amount, steam_login, currency):
    commission = calculate_commission(amount, currency)
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
def calculate_commission(amount, currency):
    if currency == 'RUB':    
        return round(amount * COMMISSION_RUB, 2)  # 13.7% комиссия

# /start
async def start(update: Update, context: CallbackContext):
    context.user_data.clear()

    user_id = update.effective_user.id
    user_name = update.effective_user.first_name
    text = f"👋 Привет, {user_name}!\n\nДобро пожаловать в наш сервис для быстрого пополнения аккаунтов Steam и не только! 🚀\n\nВыберите опцию ниже, чтобы начать."

    keyboard = [
        [InlineKeyboardButton("💰 Пополнить Steam", callback_data='topup')],
        [InlineKeyboardButton("📦 Мои заказы", callback_data='my_orders')],
    ]

    if user_id in ADMINS:
        keyboard.append([InlineKeyboardButton("⚙️ Админ-панель", callback_data='admin_panel')])

    if update.callback_query:
        await update.callback_query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def back_to_menu(update: Update, context: CallbackContext):
    context.user_data.clear()
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    user_name = update.effective_user.first_name
    text = f"👋 Привет, {user_name}!\n\nДобро пожаловать в наш сервис для быстрого пополнения аккаунтов Steam и не только! 🚀\n\nВыберите опцию ниже, чтобы начать."

    keyboard = [
        [InlineKeyboardButton("💰 Пополнить Steam", callback_data='topup')],
        [InlineKeyboardButton("📦 Мои заказы", callback_data='my_orders')],
    ]

    if user_id in ADMINS:
        keyboard.append([InlineKeyboardButton("⚙️ Админ-панель", callback_data='admin_panel')])

    await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard))

async def view_my_orders(update: Update, context: CallbackContext):
    user_id = update.effective_user.id

    try:
        conn = await asyncpg.connect(DATABASE_URL)
        rows = await conn.fetch("""
            SELECT steam_login, amount, commission, created_at
            FROM steam_topups
            WHERE telegram_id = $1
            ORDER BY created_at DESC
            LIMIT $2
        """, user_id, 15)
        await conn.close()

        if not rows:
            text = "❌ У вас пока нет заказов."
        else:
            header = "📦 Ваши последние заказы:\n\n"
            text = header
            for row in rows:
                block = (
                    f"👤 Логин: <code>{row['steam_login']}</code>\n"
                    f"💸 Сумма: {row['amount']:.2f}₽\n"
                    f"💰 Комиссия: {row['commission']:.2f}₽\n"
                    f"🕒 Время: {row['created_at'].strftime('%Y-%m-%d %H:%M')}\n\n"
                )
                # Проверяем, не превысим ли лимит в 4096 символов
                if len(text) + len(block) > 4096:
                    break
                text += block

        keyboard = [[InlineKeyboardButton("⬅️ Назад в меню", callback_data='back_to_menu')]]

        await update.callback_query.message.edit_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    except Exception as e:
        print(f"Ошибка при получении заказов: {e}")
        await update.callback_query.message.edit_text("⚠️ Произошла ошибка при получении заказов.")

async def admin_panel(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    keyboard = [
        [InlineKeyboardButton("🧾 Комиссия", callback_data='choose_fee_type')],
        [InlineKeyboardButton("📊 Проверка баланса", callback_data='check_balance')],
        [InlineKeyboardButton("📊 Статистика", callback_data='stats')],
        [InlineKeyboardButton("⬅️ Назад в меню", callback_data='back_to_menu')],
    ]

    await query.edit_message_text(
        "⚙️ Админ-панель:\n\nВыберите действие:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_check_balance(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    try:
        # Запрос баланса
        response = requests.post(BALANCE_API_URL, data={'apikey': API_KEY})
        data = response.json()

        # Обработка ответа
        if "balance" in data:
            balance = float(data["balance"])
            text = f"💼 Баланс партнёрского счёта:\n\n{balance:.2f} ₽"
        else:
            text = "❌ Не удалось получить баланс.\nПроверь API."

        # Добавляем кнопку назад
        keyboard = [
            [InlineKeyboardButton("⬅️ Назад", callback_data='admin_panel')],
        ]
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    except Exception as e:
        await query.edit_message_text(f"⚠️ Ошибка при запросе баланса:\n{e}")

async def choose_fee_type(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    keyboard = [
        [InlineKeyboardButton("💸 Посмотреть комиссию Steam (RUB)", callback_data='show_fee_rub')],
        [InlineKeyboardButton("🇷🇺 Изменить комиссию Steam (RUB)", callback_data='edit_fee_rub')],
        [InlineKeyboardButton("⬅️ Назад", callback_data='admin_panel')],
    ]

    await query.edit_message_text(
        "Выберите, для чего вы хотите изменить комиссию:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

#  Изменить комиссию
async def show_fee_rub(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    keyboard = [
        [InlineKeyboardButton("⬅️ Назад", callback_data='choose_fee_type')],
    ]
    await query.edit_message_text(
         f"💼 комиссия на Steam (RUB):\n\n{round(COMMISSION_RUB * 100, 2)}%",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

#  Изменить комиссию
async def edit_fee_rub(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    keyboard = [
        [InlineKeyboardButton("⬅️ Назад", callback_data='choose_fee_type')],
    ]
    context.user_data["awaiting_fee"] = "COMMISSION_RUB"
    await query.edit_message_text(
        "✏️ Введите новую комиссию для Steam (RUB):\n"
        "• 1.0 = 100%\n"
        "• 0.01 = 1%\n\n",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_text(update: Update, context: CallbackContext):
    fee_type = context.user_data.get("awaiting_fee")
    login = context.user_data.get('awaiting_login')
    sum_on_steam = context.user_data.get('awaiting_sum_on_steam')
    print(fee_type)
    if fee_type in ("COMMISSION_RUB", ''):
        try:
            percent = float(update.message.text)
            if percent <= 0:
                raise ValueError("Меньше или равно нулю")

            global COMMISSION_RUB
            COMMISSION_RUB =  percent
            print(COMMISSION_RUB)
            context.user_data["awaiting_fee"] = None
            keyboard = [
                [InlineKeyboardButton("⬅️ Назад", callback_data='choose_fee_type')],
            ]
            await update.message.reply_text(
                f"✅ Комиссия обновлена для {fee_type.upper()}:\n"
                f"• Введено: {percent}\n"
                f"• Сохранено как: {percent * 100}%",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except ValueError:
            await update.message.reply_text("❌ Введите корректное число больше 0.")

    elif login:
        steam_login = update.message.text
        currency = context.user_data.get('currency')
        result = check_steam_login(API_KEY, steam_login, currency)

        if not result.get("status"):
            await update.message.reply_text("🚫 Логин недействителен. Попробуйте снова.")
            return

        context.user_data['steam_login'] = steam_login
        if currency == 'RUB':

            context.user_data['awaiting_login'] = False
            context.user_data['awaiting_sum_on_steam'] = True
            await update.message.reply_text(
                "💵 Пожалуйста, введите сумму пополнения:\n\n"
                "✅ Сумма не может быть ниже 100₽.\n"
                "📝 Например: 100₽, 200₽.",
                parse_mode='Markdown'
            )

    elif sum_on_steam:
        try:
            amount = int(update.message.text)
            if amount < 100:
                raise ValueError("Слишком маленькая сумма")

            context.user_data['amount'] = amount
            context.user_data['awaiting_sum_on_steam'] = False
            currency = context.user_data.get('currency')

            commission = calculate_commission(amount, currency)
            total = round(amount + commission, 2)
            context.user_data['commission'] = commission
            steam_login = context.user_data.get('steam_login')

            keyboard = [
                [InlineKeyboardButton("✅ Подтвердить", callback_data='confirm_payment')],
                [InlineKeyboardButton("❌ Отменить", callback_data='cancel_payment')],
            ]
            await update.message.reply_text(
                f"🧾 Проверьте данные перед оплатой:\n\n"
                f"👤 Логин: {steam_login}\n"
                f"💰 Сумма на Steam: {amount}₽\n"
                f"🧾 Комиссия: {commission}₽\n"
                f"💳 Итого к оплате: {total}₽\n"
                f"✅ Подтвердите платёж:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

        except ValueError:
            await update.message.reply_text("❌ Введите корректную сумму (от 100₽).")

    else:
        await update.message.reply_text("Пожалуйста, используйте /start или кнопки.")

# Нажата кнопка Пополнить Steam
async def topup_handler(update: Update, context: CallbackContext):
    await update.callback_query.answer()
    keyboard = [
        [InlineKeyboardButton("🇷🇺 RUB", callback_data='currency_rub')],
        [InlineKeyboardButton("🇺🇸 USD (временно недоступно)", callback_data='currency_usd')],
        [InlineKeyboardButton("⬅️ Назад в меню", callback_data='back_to_menu')],
    ]
    await update.callback_query.edit_message_text("🌍 Выберите валюту:", reply_markup=InlineKeyboardMarkup(keyboard))

# Обработка валюты
async def currency_chosen(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    keyboard = [
        [InlineKeyboardButton("⬅️ Назад", callback_data='topup_handler')],
    ]
    # Получаем валюту из callback_data
    currency = query.data.split('_')[1].upper()
    context.user_data['currency'] = currency

    if currency == 'RUB':
        # Переход в следующую общую функцию — ввод логина
        context.user_data['awaiting_login'] = True
        await query.edit_message_text("🧾 Введите логин от вашего Steam аккаунта:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif currency == 'USD':
        keyboard = [
            [InlineKeyboardButton("⬅️ Назад", callback_data='topup_handler')],
        ]
        await query.edit_message_text("🇺🇸 USD (временно недоступно):", reply_markup=InlineKeyboardMarkup(keyboard))

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
async def check_payment_status(payment_id, amount, query, recipient, commission):
    print("Начинаем проверку статуса платежа...")
    
    previous_message = None  # Переменная для хранения предыдущего сообщения
    
    while True:
        try:
            updated_payment = Payment.find_one(payment_id)
            print(f"Платеж с ID {payment_id} получен. Статус: {updated_payment.status}")

            # Проверка на успешный статус
            if updated_payment.status == "succeeded":
                print("Оплата успешна.")
                
                # Это Steam логин — переводим средства
                result = transfer_to_steam(amount, recipient)

                # Записываем в базу данных

                username = query.from_user.username
                user_id = query.from_user.id

                await log_steam_topup(user_id, username, recipient, amount, commission)
                if result:
                    message = "💸 Деньги поступили! 🎉 Ожидайте, пожалуйста, поступление на ваш баланс Steam. ⏳"
                    break
                else:
                    message = (
                        "⚠️ Упс! Что-то пошло не так при пополнении баланса Steam.\n"
                        "💬 свяжитесь с администратором для помощи. 🙏"
                    )
                if previous_message != message:
                    await query.edit_message_text(message)
                    previous_message = message
                break

            elif updated_payment.status == "canceled":
                print("Оплата была отменена.")
                message = "❌ Оплата была отменена. Попробуйте снова! 💡"
                if previous_message != message:
                    await query.edit_message_text(message)
                    previous_message = message
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

    if update.callback_query.data == 'confirm_payment':
        amount = context.user_data['amount']
        login = context.user_data['steam_login']
        currency = context.user_data.get('currency')
        commission = context.user_data.get('commission')

        # Создаем платеж и получаем ссылку на оплату
        payment_url, payment_id = create_payment_ykassa(amount, login, currency)

        # Сохраняем ID платежа в user_data для дальнейшей проверки
        context.user_data['payment_id'] = payment_id

        # Отправляем ссылку на оплату
        await update.callback_query.edit_message_text(f"🔗 Перейдите по ссылке для оплаты:\n{payment_url}")

        # Запускаем асинхронную задачу для проверки статуса платежа
        asyncio.create_task(check_payment_status(payment_id, amount, update.callback_query, login, commission))

    else:
        await update.callback_query.edit_message_text("🚫 Операция отменена. Возврат в главное меню.")
        await start(update, context)

    return ConversationHandler.END

# Отмена
async def cancel(update: Update, context: CallbackContext):
    await update.callback_query.edit_message_text("🚫 Операция отменена. Возврат в главное меню.")
    await start(update, context)
    return ConversationHandler.END

# Основной запуск
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(admin_panel, pattern="^admin_panel$"))
    app.add_handler(CallbackQueryHandler(choose_fee_type, pattern="^choose_fee_type$"))
    app.add_handler(CallbackQueryHandler(back_to_menu, pattern="^back_to_menu$"))
    app.add_handler(CallbackQueryHandler(edit_fee_rub, pattern="^edit_fee_rub$"))
    app.add_handler(CallbackQueryHandler(show_fee_rub, pattern="^show_fee_rub$"))
    app.add_handler(CallbackQueryHandler(handle_check_balance, pattern="^check_balance$"))
    app.add_handler(CallbackQueryHandler(topup_handler, pattern="^topup$"))
    app.add_handler(CallbackQueryHandler(topup_handler, pattern="^topup_handler$"))
    app.add_handler(CallbackQueryHandler(currency_chosen, pattern="^currency_rub$"))
    app.add_handler(CallbackQueryHandler(confirmation_handler, pattern="^confirm_payment$"))
    app.add_handler(CallbackQueryHandler(currency_chosen, pattern="^currency_usd$"))
    app.add_handler(CallbackQueryHandler(cancel, pattern="^cancel_payment$"))
    app.add_handler(CallbackQueryHandler(view_my_orders, pattern="^my_orders$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.run_polling()

if __name__ == "__main__":
    main()
