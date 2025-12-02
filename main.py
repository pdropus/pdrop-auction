from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, MessageEntity
from telegram.ext import Application, ContextTypes, MessageHandler, CommandHandler, CallbackQueryHandler, filters
from datetime import datetime, timedelta
import reurfl

TOKEN   = "8454655203:AAGxMR1lN1Xs03e5BxtzpW35EuZvn8imRT0"
CHANNEL = "pdrop_us"           # без @
GROUP   = -1003380922656
ADMIN   = 6895755261           # твой Telegram ID

auctions = {}

# Уведомления в группу + тебе в ЛС
async def notify(text: str):
    try:
        await app.bot.send_message(GROUP, text, disable_notification=True)
        await app.bot.send_message(ADMIN, f"АУКЦИОН\n\n{text}")
    except: pass

# Парсим цену из текста
def extract_price(text: str) -> int:
    match = re.search(r'(\d+[.,]?\d*)\s*[кkK]?', text.lower().replace(',', '.'))
    if not match: return 1000
    num = float(match.group(1))
    if any(x in match.group(0) for x in 'кkK'): num *= 1000
    return int(num)

def fmt(seconds: int) -> str:
    m, s = divmod(seconds, 60)
    return f"{m:02d}:{s:02d}"

# Обновление лота каждые 3 сек
async def tick(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    mid = job.data
    if mid not in auctions: return

    lot = auctions[mid]
    left = max(0, int((lot["end"] - datetime.now()).total_seconds()))

    if left == 0:
        winner = lot.get("lead", "никто")
        await notify(f"АУКЦИОН ЗАВЕРШЁН\n{lot['name']}\nПобедитель: @{winner}\nЦена: {lot['price']:,} ₽")
        try:
            await context.bot.edit_message_caption(
                chat_id=GROUP, message_id=mid,
                caption=f"АУКЦИОН ЗАВЕРШЁН\n{lot['name']}\nПобедитель: @{winner}\nЦена: {lot['price']:,} ₽"
            )
        except: pass
        auctions.pop(mid, None)
        return

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"СТАВКА: {lot['price']:,} ₽".replace(",", " "), callback_data="ignore")],
        [InlineKeyboardButton(b, callback_data=f"{v}_{mid}") for b, v in [("+50₽", 50), ("+100₽", 100), ("+150₽", 150)]]
    ])

    caption = (f"Название: {lot['name']}\n"
               f"Состояние: {lot['cond']}\n"
               f"Старт: {lot['start']:,} ₽\n"
               f"Локация: {lot['loc']}\n\n"
               f"Лидер: @{lot.get('lead', '—')}\n"
               f"Осталось: {fmt(left)}")

    try:
        await context.bot.edit_message_caption(chat_id=GROUP, message_id=mid, caption=caption, reply_markup=kb)
    except: pass

# Новый лот из канала
async def new_lot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.channel_post
    if not msg or msg.chat.username != CHANNEL: return
    text = (msg.caption or msg.text or "")
    if "#аукцион" not in text.lower(): return

    price = extract_price(text)
    name = cond = loc = "—"
    for line in text.splitlines():
        low = line.lower()
        if low.startswith("название:"): name = line.split(":", 1)[1].strip()
        if low.startswith("состояние:"): cond = line.split(":", 1)[1].strip()
        if low.startswith("локация:"): loc = line.split(":", 1)[1].strip()

    photo = msg.photo[-1].file_id if msg.photo else None
    sent = await context.bot.send_photo(
        chat_id=GROUP,
        photo=photo or "https://via.placeholder.com/600",
        caption=f"Название: {name}\nСостояние: {cond}\nСтарт: {price:,} ₽\nЛокация: {loc}\n\nЛидер: —\nОсталось: 60:00"
    )

    mid = sent.message_id
    auctions[mid] = {
        "price": price, "start": price, "name": name, "cond": cond, "loc": loc,
        "end": datetime.now() + timedelta(hours=1)
    }

    # Кнопки
    await context.bot.send_message(
        chat_id=GROUP, text=" ", reply_to_message_id=mid,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(f"СТАВКА: {price:,} ₽".replace(",", " "), callback_data="ignore")],
            [InlineKeyboardButton(b, callback_data=f"{v}_{mid}") for b, v in [("+50₽", 50), ("+100₽", 100), ("+150₽", 150)]]
        ])
    )

    await notify(f"НОВЫЙ ЛОТ\n{name}\nСтартовая цена: {price:,} ₽")
    context.job_queue.run_repeating(tick, interval=3, data=mid)

# Ставки
async def bid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    try:
        amount, mid = map(int, q.data.split("_"))
    except: return
    if mid not in auctions: return

    lot = auctions[mid]
    lot["price"] += amount
    lot["lead"] = q.from_user.username or q.from_user.first_name or "аноним"

    if (lot["end"] - datetime.now()).total_seconds() < 180:
        lot["end"] += timedelta(minutes=5)

    await notify(f"НОВАЯ СТАВКА\n@{lot['lead']} +{amount}₽\n{lot['name']}\nТекущая: {lot['price']:,} ₽")
    await q.answer(f"+{amount}₽ — ты лидер!", show_alert=True)

# Команда /sell
async def sell(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Кидай фото + описание + #аукцион в @pdrop_us — я выставлю лот автоматически!")

# ЗАПУСК
app = Application.builder().token(TOKEN).build()

app.add_handler(MessageHandler(filters.ChatType.CHANNEL & filters.Entity(MessageEntity.HASHTAG), new_lot))
app.add_handler(CallbackQueryHandler(bid, pattern=r"^\d+_\d+$"))
app.add_handler(CommandHandler("sell", sell))

print("АУКЦИОН 2025 — ЗАПУЩЕН И РАБОТАЕТ НА 100%")
app.run_polling(drop_pending_updates=True)
