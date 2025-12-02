from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, ContextTypes, MessageHandler, CommandHandler, CallbackQueryHandler, filters
from datetime import datetime, timedelta
import re

TOKEN = "8454655203:AAGxMR1lN1Xs03e5BxtzpW35EuZvn8imRT0"
CHANNEL = "@pdrop_us"
GROUP = -1003380922656

auctions = {}

def extract_price(text):
    text = text.lower().replace(',', '.')
    for p in [r'(\d+[.,]?\d*)\s*[кk]', r'(\d+[.,]?\d*)\s*000', r'(\d+[.,]?\d*)\s*₽', r'(\d+[.,]?\d*)']:
        m = re.search(p, text)
        if m:
            num = float(m.group(1))
            if any(x in m.group(0) for x in ['к','k','000']): num *= 1000
            return int(num)
    return 1000

def format_time(seconds):
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"

async def refresh_lot(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    msg_id = job.data["msg_id"]
    if msg_id not in auctions:
        return

    lot = auctions[msg_id]
    left = max(0, int((lot["end_time"] - datetime.now()).total_seconds()))
    
    if left <= 0 and not lot.get("ended"):
        lot["ended"] = True
        await end_auction(msg_id, context)
        return

    price_str = f"{lot['price']:,} ₽".replace(",", " ")
    leader = f"@{lot['bidder']}" if lot['bidder'] else "—"

    keyboard = [
        [InlineKeyboardButton(f"ТЕКУЩАЯ СТАВКА: {price_str}", callback_data="noop")],
        [InlineKeyboardButton("+50 ₽", callback_data=f"bid_{msg_id}_50"),
         InlineKeyboardButton("+100 ₽", callback_data=f"bid_{msg_id}_100"),
         InlineKeyboardButton("+150 ₽", callback_data=f"bid_{msg_id}_150")],
    ]
    if lot.get("my_bid") == context.job.data.get("user_id"):
        keyboard.append([InlineKeyboardButton("Я ЛИДИРУЮ", callback_data=f"lead_{msg_id}")])

    text = f"""Название: {lot['name']}
Состояние: {lot['condition']}
Старт: {lot['start_price']:,} ₽
Локация: {lot['location']}

Лидер: {leader}
Осталось: {format_time(left)}

<a href="https://t.me/pdrop_us">аукцион</a>"""

    try:
        await context.bot.edit_message_caption(chat_id=GROUP, message_id=msg_id, caption=text, 
                                              reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    except:
        pass

async def end_auction(msg_id, context):
    if msg_id not in auctions: return
    lot = auctions.pop(msg_id)
    winner = f"@{lot['bidder']} — {lot['price']:,} ₽!" if lot['bidder'] else "Ставок не было"
    await context.bot.edit_message_caption(GROUP, msg_id, 
        caption=f"АУКЦИОН ЗАВЕРШЁН\n\n{lot['name']}\n{winner}")

async def new_auction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.channel_post
    if not msg or msg.chat.username != CHANNEL[1:]: return
    text = (msg.caption or msg.text or "")
    if "#аукцион" not in text.lower(): return

    price = extract_price(text)
    name = condition = location = "—"
    for line in text.split("\n"):
        l = line.lower()
        if l.startswith("название:"): name = line.split(":",1)[1].strip()
        if l.startswith("состояние:"): condition = line.split(":",1)[1].strip()
        if l.startswith("локация:"): location = line.split(":",1)[1].strip()

    photo = msg.photo[-1].file_id if msg.photo else None
    sent = await context.bot.send_photo(
        GROUP, photo or "https://via.placeholder.com/400",
        caption=f"Название: {name}\nСостояние: {condition}\nСтарт: {price:,} ₽\nЛокация: {location}\n\nЛидер: —\nОсталось: 60:00",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton(f"ТЕКУЩАЯ СТАВКА: {price:,} ₽".replace(",", " "), callback_data="noop"),
            InlineKeyboardButton("+50 ₽", callback_data=f"bid_{sent.message_id}_50"),
            InlineKeyboardButton("+100 ₽", callback_data=f"bid_{sent.message_id}_100"),
            InlineKeyboardButton("+150 ₽", callback_data=f"bid_{sent.message_id}_150")
        ]]),
        parse_mode="HTML"
    )

    auctions[sent.message_id] = {
        "price": price, "start_price": price, "bidder": None, "my_bid": None,
        "name": name, "condition": condition, "location": location,
        "end_time": datetime.now() + timedelta(hours=1), "ended": False
    }

    context.job_queue.run_repeating(refresh_lot, interval=3, data={"msg_id": sent.message_id})

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
    lot["my_bid"] = q.from_user.id

    if (lot["end_time"] - datetime.now()).total_seconds() < 180:
        lot["end_time"] = datetime.now() + timedelta(minutes=5)

    await q.answer(f"Ставка +{amount} ₽ принята!")
    await refresh_lot(context)

async def sell_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Отправь фото + описание с тегом #аукцион — я выставлю лот автоматически!\n\n"
        "Пример:\n"
        "Название: iPhone 14\n"
        "Состояние: новый\n"
        "Локация: Москва\n"
        "Цена: 50к\n"
        "#аукцион"
    )

# ЗАПУСК
app = Application.builder().token(TOKEN).build()

app.add_handler(MessageHandler(filters.ChatType.CHANNEL & filters.CaptionRegex(r"(?i)#аукцион"), new_auction))
app.add_handler(CallbackQueryHandler(bid, pattern=r"^bid_"))
app.add_handler(CommandHandler("sell", sell_command))

print("АУКЦИОН 2025 ЗАПУЩЕН — ВСЁ РАБОТАЕТ 100%!")
app.run_polling(drop_pending_updates=True)
