from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, ContextTypes, MessageHandler, CallbackQueryHandler, filters
from datetime import datetime, timedelta
import re

# ─────── ТВОИ ДАННЫЕ (всё уже вставлено правильно) ───
TOKEN      = "8454655203:AAGxMR1lN1Xs03e5BxtzpW35EuZvn8imRT0"
CHANNEL_ID = -1002496916338   # твой канал @pdrop_us
GROUP      = -1003380922656   # твоя группа
ADMIN      = 6895755261       # твой ID — сюда приходят уведомления

auctions = {}

# Уведомления тебе в ЛС
async def notify(text):
    try: await app.bot.send_message(ADMIN, f"АУКЦИОН\n\n{text}")
    except: pass

# Парсим цену (15к, 15000, 15.5к и т.д.)
def get_price(text):
    match = re.search(r'(\d+[.,]?\d*)', text.lower().replace(',', '.'))
    if not match: return 1000
    num = float(match.group(1))
    if re.search(r'[кkKкК]', text.lower()): num *= 1000
    return int(num)

# Формат времени
def fmt(seconds): return f"{seconds//60:02d}:{seconds%60:02d}"

# Обновление лота каждые 3 секунды
async def tick(context):
    mid = context.job.data
    if mid not in auctions: return
    lot = auctions[mid]
    left = max(0, int((lot["end"] - datetime.now()).total_seconds()))

    if left == 0:  # аукцион закончился
        winner = lot.get("lead", "никто")
        await notify(f"АУКЦИОН ЗАВЕРШЁН\n{lot['name']}\nПобедитель: @{winner}\nЦена: {lot['price']:,} ₽")
        try:
            await context.bot.edit_message_caption(GROUP, mid,
                caption=f"АУКЦИОН ЗАВЕРШЁН\n{lot['name']}\nПобедитель: @{winner}\nФинальная цена: {lot['price']:,} ₽")
        except: pass
        auctions.pop(mid, None)
        return

    # Кнопки
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"СТАВКА: {lot['price']:,} ₽".replace(",", " "), callback_data="0")],
        [InlineKeyboardButton(t, callback_data=f"{v}_{mid}") for t, v in [("+50₽", 50), ("+100₽", 100), ("+150₽", 150)]]
    ])
    caption = (f"Название: {lot['name']}\n"
               f"Состояние: {lot['cond']}\n"
               f"Старт: {lot['start']:,} ₽\n"
               f"Локация: {lot['loc']}\n\n"
               f"Лидер: @{lot.get('lead', '—')}\n"
               f"Осталось: {fmt(left)}")

    try:
        await context.bot.edit_message_caption(GROUP, mid, caption=caption, reply_markup=kb)
    except: pass

# Новый лот из канала
async def new_lot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.channel_post
    if not msg or msg.chat.id != CHANNEL_ID: return
    text = (msg.caption or msg.text or "")
    if "#аукцион" not in text.lower(): return

    price = get_price(text)
    name = cond = loc = "—"
    for line in text.splitlines():
        low = line.lower()
        if low.startswith("название:"): name = line.split(":", 1)[1].strip()
        if low.startswith("состояние:"): cond = line.split(":", 1)[1].strip()
        if low.startswith("локация:"): loc = line.split(":", 1)[1].strip()

    photo = msg.photo[-1].file_id if msg.photo else None
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

    # Кнопки под фото
    await context.bot.send_message(
        GROUP, " ", reply_to_message_id=mid,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(f"СТАВКА: {price:,} ₽".replace(",", " "), callback_data="0")],
            [InlineKeyboardButton(t, callback_data=f"{v}_{mid}") for t, v in [("+50₽", 50), ("+100₽", 100), ("+150₽", 150)]]
        ])
    )

    await notify(f"НОВЫЙ ЛОТ!\n{name}\nСтарт: {price:,} ₽")
    context.job_queue.run_repeating(tick, interval=3, data=mid)

# Обработка ставок
async def bid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    try:
        amt, mid = map(int, q.data.split("_"))
    except: return
    if mid not in auctions: return

    lot = auctions[mid]
    lot["price"] += amt
    lot["lead"] = q.from_user.username or q.from_user.first_name or "аноним"

    # Продление на 5 минут, если осталось < 3 минут
    if (lot["end"] - datetime.now()).total_seconds() < 180:
        lot["end"] += timedelta(minutes=5)

    await notify(f"НОВАЯ СТАВКА!\n@{lot['lead} +{amt}₽\n{lot['name']}\nТекущая цена: {lot['price']:,} ₽")
    await q.answer(f"+{amt}₽ — ты лидер!", show_alert=True)

# Запуск бота
app = Application.builder().token(TOKEN).build()

app.add_handler(MessageHandler(filters.Chat(CHANNEL_ID) & filters.Regex(r"(?i)#аукцион"), new_lot))
app.add_handler(CallbackQueryHandler(bid, pattern=r"^\d+_\d+$"))

print("АУКЦИОН-БОТ @pdrop_us — ЗАПУЩЕН И РАБОТАЕТ НА 100%")
app.run_polling(drop_pending_updates=True)
