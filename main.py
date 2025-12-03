from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, ContextTypes, MessageHandler, CommandHandler, CallbackQueryHandler, filters
from datetime import datetime, timedelta
import re

TOKEN   = "8454655203:AAGxMR1lN1Xs03e5BxtzpW35EuZvn8imRT0"
CHANNEL_ID = -1002496916338   # твой ID канала
GROUP   = -1003380922656
ADMIN   = 6895755261

auctions = {}

async def notify(text):
    try:
        await app.bot.send_message(ADMIN, f"АУКЦИОН\n\n{text}")
    except: pass

def get_price(t):
    m = re.search(r'(\d+[.,]?\d*)', t.lower().replace(',','.'))
    if not m: return 1000
    num = float(m.group(1))
    if re.search(r'[кkK]', t.lower()): num *= 1000
    return int(num)

def fmt(s): return f"{s//60:02d}:{s%60:02d}"

async def tick(c):
    mid = c.job.data
    if mid not in auctions: return
    lot = auctions[mid]
    left = max(0, int((lot["end"] - datetime.now()).total_seconds()))

    if left == 0:
        w = lot.get("lead", "никто")
        await notify(f"ЗАВЕРШЁН\n{lot['name']}\n@{w} — {lot['price']:,} ₽")
        try:
            await c.bot.edit_message_caption(GROUP, mid, caption=f"АУКЦИОН ЗАВЕРШЁН\n{lot['name']}\n@{w} — {lot['price']:,} ₽")
        except: pass
        auctions.pop(mid, None)
        return

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"СТАВКА: {lot['price']:,} ₽".replace(",", " "), callback_data="0")],
        [InlineKeyboardButton(t, callback_data=f"{v}_{mid}") for t, v in [("+50₽", 50), ("+100₽", 100), ("+150₽", 150)]]
    ])
    cap = f"Название: {lot['name']}\nСостояние: {lot['cond']}\nСтарт: {lot['start']:,} ₽\nЛокация: {lot['loc']}\n\nЛидер: @{lot.get('lead','—')}\nОсталось: {fmt(left)}"
    try: await c.bot.edit_message_caption(GROUP, mid, caption=cap, reply_markup=kb)
    except: pass

async def new_lot(u: Update, c: ContextTypes.DEFAULT_TYPE):
    m = u.channel_post
    if not m or m.chat.id != CHANNEL_ID: return
    txt = (m.caption or m.text or "")
    if "#аукцион" not in txt.lower(): return

    p = get_price(txt)
    name = cond = loc = "—"
    for l in txt.splitlines():
        low = l.lower()
        if low.startswith("название:"): name = l.split(":",1)[1].strip()
        if low.startswith("состояние:"): cond = l.split(":",1)[1].strip()
        if low.startswith("локация:"): loc = l.split(":",1)[1].strip()

    photo = m.photo[-1].file_id if m.photo else None
    sent = await c.bot.send_photo(GROUP, photo or "https://via.placeholder.com/600",
        caption=f"Название: {name}\nСостояние: {cond}\nСтарт: {p:,} ₽\nЛокация: {loc}\n\nЛидер: —\nОсталось: 60:00")

    mid = sent.message_id
    auctions[mid] = {"price":p,"start":p,"name":name,"cond":cond,"loc":loc,"end":datetime.now()+timedelta(hours=1)}

    await c.bot.send_message(GROUP, " ", reply_to_message_id=mid, reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton(f"СТАВКА: {p:,} ₽".replace(",", " "), callback_data="0")],
        [InlineKeyboardButton(t, callback_data=f"{v}_{mid}") for t,v in [("+50₽",50),("+100₽",100),("+150₽",150)]]
    ]))

    await notify(f"НОВЫЙ ЛОТ\n{name}\nСтарт: {p:,} ₽")
    c.job_queue.run_repeating(tick, 3, data=mid)

async def bid(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer()
    try: amt, mid = map(int, q.data.split("_"))
    except: return
    if mid not in auctions: return

    lot = auctions[mid]; lot["price"] += amt
    user = q.from_user.username or q.from_user.first_name or "аноним"
    lot["lead"] = user

    if (lot["end"] - datetime.now()).total_seconds() < 180:
        lot["end"] += timedelta(minutes=5)

    await notify(f"НОВАЯ СТАВКА\n@{user} +{amt}₽\n{lot['name']}\nТекущая: {lot['price']:,} ₽")
    await q.answer(f"+{amt}₽ — ты лидер!", show_alert=True)

# /sell
async def sell(u: Update, _): await u.message.reply_text("Кидай лот в @pdrop_us с #аукцион — я выставлю сам!")

# ЗАПУСК
app = Application.builder().token(TOKEN).build()

app.add_handler(MessageHandler(filters.Chat(CHANNEL_ID) & filters.Regex(r"(?i)#аукцион"), new_lot))
app.add_handler(CallbackQueryHandler(bid, pattern=r"^\d+_\d+$"))
app.add_handler(CommandHandler("sell", sell))

print("АУКЦИОН 2025 — 100% ЖИВОЙ, ПРОВЕРЕНО НА RENDER")
app.run_polling(drop_pending_updates=True)
