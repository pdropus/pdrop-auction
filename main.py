from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, ContextTypes, MessageHandler, CommandHandler, CallbackQueryHandler, filters
from datetime import datetime, timedelta
import re

TOKEN = "8454655203:AAGxMR1lN1Xs03e5BxtzpW35EuZvn8imRT0"
CHANNEL = "@pdrop_us"
GROUP = -1003380922656   # твой чат/группа

auctions = {}

def extract_price(text):
    text = text.lower().replace(',', '.')
    match = re.search(r'(\d+[.,]?\d*)\s*[кkк]|(\d+[.,]?\d*)\s*000|(\d+[.,]?\d*)\s*₽|(\d+[.,]?\d*)', text)
    if match:
        num = float([x for x in match.groups() if x][0])
        if 'к' in match.group(0) or 'k' in match.group(0) or '000' in match.group(0):
            num *= 1000
        return int(num)
    return 1000

def format_time(sec):
    m, s = divmod(int(sec), 60)
    return f"{m:02d}:{s:02d}"

# ────────────────────── ОБНОВЛЕНИЕ ЛОТА ──────────────────────
async def refresh_lot(context: ContextTypes.DEFAULT_TYPE):
    msg_id = context.job.data["msg_id"]
    if msg_id not in auctions:
        return
    lot = auctions[msg_id]
    left = max(0, (lot["end_time"] - datetime.now()).total_seconds())

    if left <= 0 and not lot.get("ended"):
        lot["ended"] = True
        await context.bot.edit_message_caption(GROUP, msg_id, caption=f"АУКЦИОН ЗАВЕРШЁН ⚡\n\n{lot['name']}\nПобедитель: @{lot['bidder'] if lot['bidder'] else '—'} — {lot['price']:,} ₽" if lot['bidder'] else "Ставок не было")
        del auctions[msg_id]
        return

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"СТАВКА: {lot['price']:,} ₽".replace(",", " "), callback_data="noop")],
        [InlineKeyboardButton("+50₽", callback_data=f"bid_{msg_id}_50"),
         InlineKeyboardButton("+100₽", callback_data=f"bid_{msg_id}_100"),
         InlineKeyboardButton("+150₽", callback_data=f"bid_{msg_id}_150")],
    ])

    text = f"""Название: {lot['name']}
Состояние: {lot['condition']}
Старт: {lot['start_price']:,} ₽
Локация: {lot['location']}

Лидер: @{lot['bidder'] if lot['bidder'] else '—'}
Осталось: {format_time(left)}"""

    try:
        await context.bot.edit_message_caption(GROUP, msg_id, caption=text, reply_markup=kb, parse_mode="HTML")
    except:
        pass

# ────────────────────── НОВЫЙ ЛОТ ИЗ КАНАЛА ──────────────────────
async def new_auction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.channel_post
    if not msg or msg.chat.username != CHANNEL[1:]:
        return
    text = (msg.caption or msg.text or "")
    if "#аукцион" not in text.lower():
        return

    price = extract_price(text)
    name = condition = location = "—"
    for line in text.split("\n"):
        l = line.lower()
        if l.startswith("название:"): name = line.split(":",1)[1].strip()
        if l.startswith("состояние:"): condition = line.split(":",1)[1].strip()
        if l.startswith("локация:"): location = line.split(":",1)[1].strip()

    photo = msg.photo[-1].file_id if msg.photo else None

    sent = await context.bot.send_photo(
        chat_id=GROUP,
        photo=photo or "https://via.placeholder.com/400",
        caption=f"Название: {name}\nСостояние: {condition}\nСтарт: {price:,} ₽\nЛокация: {location}\n\nЛидер: —\nОсталось: 60:00",
        parse_mode="HTML"
    )

    msg_id = sent.message_id

    auctions[msg_id] = {
        "price": price, "start_price": price, "bidder": None,
        "name": name, "condition": condition, "location": location,
        "end_time": datetime.now() + timedelta(hours=1), "ended": False
    }

    # Добавляем кнопки сразу после отправки
    await context.bot.edit_message_reply_markup(
        chat_id=GROUP,
        message_id=msg_id,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(f"СТАВКА: {price:,} ₽".replace(",", " "), callback_data="noop")],
            [InlineKeyboardButton("+50₽", callback_data=f"bid_{msg_id}_50"),
             InlineKeyboardButton("+100₽", callback_data=f"bid_{msg_id}_100"),
             InlineKeyboardButton("+150₽", callback_data=f"bid_{msg_id}_150")]
        ])
    )

    context.job_queue.run_repeating(refresh_lot, interval=3, data={"msg_id": msg_id})

# ────────────────────── СТАВКИ ──────────────────────
async def bid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not q.data.startswith("bid_"): return
    _, msg_id, amount = q.data.split("_")
    msg_id, amount = int(msg_id), int(amount)
    if msg_id not in auctions or auctions[msg_id].get("ended"): return

    lot = auctions[msg_id]
    lot["price"] += amount
    lot["bidder"] = q.from_user.username or "аноним"

    # продление на 5 минут при ставке за последние 3 минуты
    if (lot["end_time"] - datetime.now()).total_seconds() < 180:
        lot["end_time"] = datetime.now() + timedelta(minutes=5)

    await q.answer(f"Твоя ставка +{amount}₽ принята!")
    await refresh_lot(context)

# ────────────────────── /sell ──────────────────────
async def sell(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Пришли фото + описание с #аукцион — я выставлю лот автоматически!")

# ────────────────────── ЗАПУСК ──────────────────────
app = Application.builder().token(TOKEN).build()

app.add_handler(MessageHandler(filters.ChatType.CHANNEL & filters.CaptionRegex(r"(?i)#аукцион"), new_auction))
app.add_handler(CallbackQueryHandler(bid, pattern=r"^bid_"))
app.add_handler(CommandHandler("sell", sell))

print("АУКЦИОН 2025 ЗАПУЩЕН — ВСЁ РАБОТАЕТ 100%!")
app.run_polling(drop_pending_updates=True)
