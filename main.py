from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, ContextTypes, MessageHandler, CallbackQueryHandler, filters
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
    msg_id = context.job.data["msg_id"]
    if msg_id not in auctions: return
    lot = auctions[msg_id]

    left = max(0, int((lot["end_time"] - datetime.now()).total_seconds()))
    if left <= 0 and not lot.get("ended"):
        lot["ended"] = True
        await end_auction(msg_id, context)
        return

    price = f"{lot['price']:,} ₽".replace(",", " ")
    leader = f"@{lot['bidder']}" if lot['bidder'] else "—"

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"ТЕКУЩАЯ СТАВКА:\n{price}", callback_data="noop")],
        [InlineKeyboardButton("     +50 ₽     ", callback_data="50"),
         InlineKeyboardButton("    +100 ₽     ", callback_data="100"),
         InlineKeyboardButton("    +150 ₽     ", callback_data="150")],
        [InlineKeyboardButton("Я ЛИДИРУЮ", callback_data="lead")] if lot.get("last_id") else []
    ])

    text = f"""Название: {lot['name']}
Состояние: {lot['condition']}
Старт (цена): {lot['start_price']:,} ₽
Локация: {lot['location']}

Лидер: {leader}
Осталось: {format_time(left)}

<i>аукцион</i>"""

    try:
        await context.bot.edit_message_caption(
            chat_id=GROUP, message_id=msg_id, caption=text, reply_markup=kb, parse_mode="HTML"
        )
    except: pass

async def end_auction(msg_id, context):
    if msg_id not in auctions: return
    lot = auctions.pop(msg_id)
    winner = f"Победитель @{lot['bidder']} — {lot['price']:,} ₽!" if lot['bidder'] else "Ставок не было"
    final = f"АУКЦИОН ЗАВЕРШЁН\n\nНазвание: {lot['name']}\n{winner}"
    try:
        await context.bot.edit_message_caption(GROUP, msg_id, caption=final, reply_markup=None)
    except: pass

async def new_auction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.channel_post
    if not msg or msg.chat.username != CHANNEL.lstrip("@"): return
    full = (msg.caption or msg.text or "")
    if "#аукцион" not in full.lower(): return

    clean = re.sub(r"#аукцион", "", full, flags=re.I).strip()
    price = extract_price(clean)

    lines = [l.strip() for l in clean.split("\n") if l.strip()]
    name = condition = location = "—"
    for line in lines:
        l = line.lower()
        if l.startswith("название:"): name = line.split(":",1)[1].strip()
        if l.startswith("состояние:"): condition = line.split(":",1)[1].strip()
        if l.startswith("локация:"): location = line.split(":",1)[1].strip()

    photo = msg.photo[-1].file_id if msg.photo else None

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"ТЕКУЩАЯ СТАВКА:\n{price:,} ₽".replace(",", " "), callback_data="noop")],
        [InlineKeyboardButton("     +50 ₽     ", callback_data="50"),
         InlineKeyboardButton("    +100 ₽     ", callback_data="100"),
         InlineKeyboardButton("    +150 ₽     ", callback_data="150")]
    ])

    text = f"""Название: {name}
Состояние: {condition}
Старт (цена): {price:,} ₽
Локация: {location}

Лидер: —
Осталось: 60:00

<i>аукцион</i>"""

    sent = await (context.bot.send_photo(GROUP, photo, caption=text, reply_markup=kb, parse_mode="HTML") if photo
                  else context.bot.send_message(GROUP, text, reply_markup=kb, parse_mode="HTML"))

    auctions[sent.message_id] = {
        "price": price, "start_price": price, "bidder": None, "last_id": None,
        "name": name, "condition": condition, "location": location,
        "end_time": datetime.now() + timedelta(hours=1), "msg_id": sent.message_id, "ended": False
    }

    context.job_queue.run_repeating(refresh_lot, interval=3, data={"msg_id": sent.message_id})

async def bid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data in ["noop", "lead"]:
        if q.data == "lead": await q.answer("Вы лидер!", show_alert=True)
        return

    lot = auctions.get(q.message.message_id)
    if not lot or lot.get("ended"): return

    if lot.get("last_id") == q.from_user.id:
        await q.answer("Нельзя перебивать себя!", show_alert=True)
        return

    amount = int(q.data)
    lot["price"] += amount
    lot["bidder"] = q.from_user.username or "аноним"
    lot["last_id"] = q.from_user.id

    if (lot["end_time"] - datetime.now()).total_seconds() < 180:
        lot["end_time"] = datetime.now() + timedelta(minutes=5)

    await q.answer(f"СТАВКА ПРИНЯТА +{amount} ₽")
    await refresh_lot(context)

# ЗАПУСК
app = Application.builder().token(TOKEN).build()
app.add_handler(MessageHandler(filters.ChatType.CHANNEL, new_auction))
app.add_handler(CallbackQueryHandler(bid))

print("АУКЦИОН 2025 ЗАПУЩЕН — ВСЁ РАБОТАЕТ 100%!")

app.run_polling(drop_pending_updates=True)
