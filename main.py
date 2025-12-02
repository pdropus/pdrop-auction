from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, ContextTypes, MessageHandler, CommandHandler, CallbackQueryHandler, filters
from datetime import datetime, timedelta
import re, traceback

TOKEN   = "8454655203:AAGxMR1lN1Xs03e5BxtzpW35EuZvn8imRT0"
CHANNEL = "pdrop_us"
GROUP   = -1003380922656
ADMIN   = 6895755261   # твой ID — сюда приходят все уведомления

auctions = {}

# Уведомления тебе в ЛС + в группу
async def notify(text):
    try:
        await app.bot.send_message(GROUP, text, disable_notification=True)
        await app.bot.send_message(ADMIN, f"АУКЦИОН\n\n{text}")
    except: pass

# Парсим цену
price = lambda t: int(float(re.search(r'(\d+[.,]?\d*)', t.lower().replace(',','.'))[1].replace('.','')) * (1000 if any(x in t.lower() for x in "кk000") else 1)) if re.search(r'(\d+[.,]?\d*)', t.lower()) else 1000

def fmt(s): return f"{s//60:02d}:{s%60:02d}"

# Таймер
async def tick(c: ContextTypes.DEFAULT_TYPE):
    mid = c.job.data
    if mid not in auctions: return
    lot = auctions[mid]
    left = max(0, int((lot["end"] - datetime.now()).total_seconds()))

    if left == 0:
        win = lot.get("lead")
        await notify(f"АУКЦИОН ЗАВЕРШЁН\n{lot['name']}\nПобедитель: @{win or 'никто'} — {lot['price']:,} ₽")
        try:
            await c.bot.edit_message_caption(GROUP, mid, caption=f"АУКЦИОН ЗАВЕРШЁН\n{lot['name']}\nПобедитель: @{win or '—'}\nЦена: {lot['price']:,} ₽")
        except: pass
        auctions.pop(mid, None)
        return

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"СТАВКА: {lot['price']:,} ₽".replace(',',' '), callback_data="x")],
        [InlineKeyboardButton(b, callback_data=f"{v}_{mid}") for b,v in [("+50₽",50),("+100₽",100),("+150₽",150)]]
    ])
    text = f"Название: {lot['name']}\nСостояние: {lot['cond']}\nСтарт: {lot['start']:,} ₽\nЛокация: {lot['loc']}\n\nЛидер: @{lot.get('lead','—')}\nОсталось: {fmt(left)}"
    try: await c.bot.edit_message_caption(GROUP, mid, caption=text, reply_markup=kb)
    except: pass

# Новый лот из канала
async def new_lot(u: Update, c: ContextTypes.DEFAULT_TYPE):
    m = u.channel_post
    if not m or m.chat.username != CHANNEL: return
    txt = (m.caption or m.text or "")
    if "#аукцион" not in txt.lower(): return

    p = price(txt)
    name = cond = loc = "—"
    for line in txt.splitlines():
        low = line.lower()
        if low.startswith("название:"): name = line.split(":",1)[1].strip()
        if low.startswith("состояние:"): cond = line.split(":",1)[1].strip()
        if low.startswith("локация:"): loc = line.split(":",1)[1].strip()

    sent = await c.bot.send_photo(GROUP, m.photo[-1].file_id if m.photo else "https://via.placeholder.com/600",
        caption=f"Название: {name}\nСостояние: {cond}\nСтарт: {p:,} ₽\nЛокация: {loc}\n\nЛидер: —\nОсталось: 60:00")

    mid = sent.message_id
    auctions[mid] = {"price":p, "start":p, "name":name, "cond":cond, "loc":loc,
                     "end": datetime.now() + timedelta(hours=1)}

    await c.bot.send_message(GROUP, " ", reply_to_message_id=mid, reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton(f"СТАВКА: {p:,} ₽".replace(',',' '), callback_data="x")],
        [InlineKeyboardButton(b, callback_data=f"{v}_{mid}") for b,v in [("+50₽",50),("+100₽",100),("+150₽",150)]]
    ]))

    await notify(f"НОВЫЙ ЛОТ\n{name}\nСтарт: {p:,} ₽")
    c.job_queue.run_repeating(tick, 3, data=mid)

# Ставки
async def bid(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer()
    try: amt, mid = map(int, q.data.split("_"))
    except: return
    if mid not in auctions: return

    lot = auctions[mid]
    lot["price"] += amt
    user = q.from_user.username or q.from_user.first_name or "аноним"
    lot["lead"] = user

    if (lot["end"] - datetime.now()).total_seconds() < 180:
        lot["end"] += timedelta(minutes=5)

    await notify(f"НОВАЯ СТАВКА\n@{user} +{amt}₽\n{lot['name']}\nТекущая: {lot['price']:,} ₽")
    await q.answer(f"+{amt}₽ — ты лидер!", show_alert=True)

# Команда /sell
async def sell(u: Update, _):
    await u.message.reply_text("Просто кинь фото + описание + #аукцион в @pdrop_us — я выставлю сам!")

# Запуск
app = Application.builder().token(TOKEN).build()
app.add_handler(MessageHandler(filters.ChatType.CHANNEL & filters.HASHTAG, new_lot))
app.add_handler(CallbackQueryHandler(bid, pattern=r"^\d+_\d+$"))
app.add_handler(CommandHandler("sell", sell))

print("АУКЦИОН 2025 — ПРОСТО РАБОТАЕТ. ЛЮБОЙ МОЖЕТ УЧАСТВОВАТЬ")
app.run_polling(drop_pending_updates=True)
