from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ForceReply
from telegram.ext import Application, ContextTypes, MessageHandler, CommandHandler, CallbackQueryHandler, filters, ConversationHandler
from datetime import datetime, timedelta
import re

TOKEN      = "8454655203:AAGxMR1lN1Xs03e5BxtzpW35EuZvn8imRT0"
GROUP      = -1003380922656
ADMIN      = 6895755261  # ты — сюда уведомления

# Состояния диалога
PHOTO, NAME, CONDITION, LOCATION, PRICE = range(5)

auctions = {}

async def notify(text):
    try: await app.bot.send_message(ADMIN, f"АУКЦИОН\n\n{text}")
    except: pass

def get_price(text):
    match = re.search(r'(\d+[.,]?\d*)', text.lower().replace(',', '.'))
    if not match: return 1000
    num = float(match.group(1))
    if re.search(r'[кkK]', text.lower()): num *= 1000
    return int(num)

def fmt(seconds): return f"{seconds//60:02d}:{seconds%60:02d}"

async def tick(context):
    mid = context.job.data
    if mid not in auctions: return
    lot = auctions[mid]
    left = max(0, int((lot["end"] - datetime.now()).total_seconds()))

    if left == 0:
        winner = lot.get("lead", "никто")
        await notify(f"АУКЦИОН ЗАВЕРШЁН\n{lot['name']}\nПобедитель: @{winner}\nЦена: {lot['price']:,} ₽")
        try:
            await context.bot.edit_message_caption(GROUP, mid,
                caption=f"АУКЦИОН ЗАВЕРШЁН\n{lot['name']}\nПобедитель: @{winner}\nЦена: {lot['price']:,} ₽")
        except: pass
        auctions.pop(mid, None)
        return

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"СТАВКА: {lot['price']:,} ₽".replace(",", " "), callback_data="0")],
        [InlineKeyboardButton(t, callback_data=f"{v}_{mid}") for t, v in [("+50₽", 50), ("+100₽", 100), ("+150₽", 150)]]
    ])
    caption = f"Название: {lot['name']}\nСостояние: {lot['cond']}\nСтарт: {lot['start']:,} ₽\nЛокация: {lot['loc']}\n\nЛидер: @{lot.get('lead','—')}\nОсталось: {fmt(left)}"
    try: await context.bot.edit_message_caption(GROUP, mid, caption=caption, reply_markup=kb)
    except: pass

# ====== ДИАЛОГ ДЛЯ ПРОДАВЦА ======
async def start_sell(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Ты хочешь выставить лот на аукцион?\n\n"
        "1/5 Отправь фото лота (или пропиши 'нет' если без фото)")
    return PHOTO

async def get_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.photo:
        context.user_data['photo'] = update.message.photo[-1].file_id
    else:
        context.user_data['photo'] = None
        if update.message.text.lower() != "нет":
            await update.message.reply_text("Я не увидел фото, продолжим без него.")
    
    await update.message.reply_text("2/5 Напиши название лота")
    return NAME

async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['name'] = update.message.text.strip() or "Без названия"
    await update.message.reply_text("3/5 Состояние лота (новый, б/у, отличное и т.д.)")
    return CONDITION

async def get_condition(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['cond'] = update.message.text.strip() or "—"
    await update.message.reply_text("4/5 Локация (город, самовывоз, доставка и т.д.)")
    return LOCATION

async def get_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['loc'] = update.message.text.strip() or "—"
    await update.message.reply_text("5/5 Стартовая цена (например: 1500 или 15к)")
    return PRICE

async def get_price_and_publish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    price = get_price(update.message.text)
    context.user_data['price'] = price

    photo = context.user_data.get('photo')
    name = context.user_data.get('name', 'Без названия')
    cond = context.user_data.get('cond', '—')
    loc = context.user_data.get('loc', '—')

    sent = await context.bot.send_photo(
        GROUP,
        photo or "https://via.placeholder.com/600",
        caption=f"Название: {name}\nСостояние: {cond}\nСтарт: {price:,} ₽\nЛокация: {loc}\n\nЛидер: —\nОсталось: 60:00"
    )

    mid = sent.message_id
    auctions[mid] = {
        "price": price, "start": price, "name": name,
        "cond": cond, "loc": loc,
        "end": datetime.now() + timedelta(hours=1)
    }

    await context.bot.send_message(
        GROUP, " ", reply_to_message_id=mid,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(f"СТАВКА: {price:,} ₽".replace(",", " "), callback_data="0")],
            [InlineKeyboardButton(t, callback_data=f"{v}_{mid}") for t, v in [("+50₽", 50), ("+100₽", 100), ("+150₽", 150)]]
        ])
    )

    seller = update.effective_user.username or update.effective_user.first_name
    await notify(f"НОВЫЙ ЛОТ от @{seller}\n{name}\nСтарт: {price:,} ₽")
    await update.message.reply_text("Готово! Твой лот выставлен в группе. Удачных торгов! 🚀")

    context.job_queue.run_repeating(tick, interval=3, data=mid)
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Выставление лота отменено.")
    return ConversationHandler.END

# ====== СТАВКИ ======
async def bid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    try: amt, mid = map(int, q.data.split("_"))
    except: return
    if mid not in auctions: return

    lot = auctions[mid]
    lot["price"] += amt
    user = q.from_user.username or q.from_user.first_name or "аноним"
    lot["lead"] = user

    if (lot["end"] - datetime.now()).total_seconds() < 180:
        lot["end"] += timedelta(minutes=5)

    await notify(f"НОВАЯ СТАВКА +{amt}₽\n@{user}\n{lot['name']}\nТекущая: {lot['price']:,} ₽")
    await q.answer(f"+{amt}₽ — ты лидер!", show_alert=True)

# ====== ЗАПУСК ======
app = Application.builder().token(TOKEN).build()

conv_handler = ConversationHandler(
    entry_points=[CommandHandler("sell", start_sell), MessageHandler(filters.TEXT & ~filters.COMMAND, start_sell)],
    states={
        PHOTO: [MessageHandler(filters.PHOTO | filters.TEXT, get_photo)],
        NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
        CONDITION: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_condition)],
        LOCATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_location)],
        PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_price_and_publish)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)

app.add_handler(conv_handler)
app.add_handler(CallbackQueryHandler(bid, pattern=r"^\d+_\d+$"))

print("АУКЦИОН С ДИАЛОГОМ — ЗАПУЩЕН И РАБОТАЕТ!")
app.run_polling(drop_pending_updates=True)
