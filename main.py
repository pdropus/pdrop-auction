from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application, ContextTypes, MessageHandler, CommandHandler, CallbackQueryHandler,
    filters, ConversationHandler
)
from datetime import datetime, timedelta
import re
import logging

logging.basicConfig(level=logging.INFO)

TOKEN       = "8454655203:AAGxMR1lN1Xs03e5BxtzpW35EuZvn8imRT0"
CHANNEL_ID  = -1002496916338   # @pdrop_us
GROUP       = -1003380922656
ADMIN       = 6895755261

# 6 шагов с комментарием
PHOTO, NAME, COND, LOC, PRICE, COMMENT = range(6)

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

def fmt(sec): return f"{sec//60:02d}:{sec%60:02d}"

async def tick(context):
    mid = context.job.data
    if mid not in auctions: return
    lot = auctions[mid]
    left = max(0, int((lot["end"] - datetime.now()).total_seconds()))

    if left == 0:
        w = lot.get("lead", "никто")
        await notify(f"ЗАВЕРШЁН\n{lot['name']}\nПобедитель: @{w}\nЦена: {lot['price']:,} ₽")
        caption = f"АУКЦИОН ЗАВЕРШЁН\nНазвание: {lot['name']}\nПобедитель: @{w}\nФинальная цена: {lot['price']:,} ₽"
        if lot.get("comment"): caption += f"\n\n{lot['comment']}"
        try: await context.bot.edit_message_caption(GROUP, mid, caption=caption, reply_markup=None)
        except: pass
        auctions.pop(mid, None)
        return

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"ТЕКУЩАЯ СТАВКА: {lot['price']:,} ₽".replace(",", " "), callback_data="0")],
        [InlineKeyboardButton("+50 ₽", callback_data=f"50_{mid}"),
         InlineKeyboardButton("+100 ₽", callback_data=f"100_{mid}"),
         InlineKeyboardButton("+150 ₽", callback_data=f"150_{mid}")]
    ])

    caption = f"Название: {lot['name']}\nСостояние: {lot['cond']}\nСтарт: {lot['start']:,} ₽\nЛокация: {lot['loc']}\n\nЛидер: @{lot.get('lead','—')}\nОсталось: {fmt(left)}"
    if lot.get("comment"):
        caption += f"\n\n{lot['comment']}"

    # Только edit_caption + reply_markup — без edit_media, чтобы не падало
    try:
        await context.bot.edit_message_caption(
            chat_id=GROUP,
            message_id=mid,
            caption=caption,
            reply_markup=kb
        )
    except Exception as e:
        print("Ошибка обновления лота:", e)

# Создание лота — теперь кнопки сразу с правильным mid!
async def create_lot(context, photo_file_id, name, cond, loc, price, comment="", seller="канал"):
    initial_caption = f"Название: {name}\nСостояние: {cond}\nСтарт: {price:,} ₽\nЛокация: {loc}\n\nЛидер: —\nОсталось: 60:00"
    if comment: initial_caption += f"\n\n{comment}"

    # Сначала отправляем с заглушкой (кнопки без mid)
    sent = await context.bot.send_photo(
        GROUP,
        photo_file_id or "https://via.placeholder.com/600",
        caption=initial_caption,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("ЗАГРУЗКА...", callback_data="0")]
        ])
    )

    mid = sent.message_id

    # Сразу правильные кнопки с реальным mid
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"ТЕКУЩАЯ СТАВКА: {price:,} ₽".replace(",", " "), callback_data="0")],
        [InlineKeyboardButton("+50 ₽", callback_data=f"50_{mid}"),
         InlineKeyboardButton("+100 ₽", callback_data=f"100_{mid}"),
         InlineKeyboardButton("+150 ₽", callback_data=f"150_{mid}")]
    ])

    # Обновляем подпись и кнопки
    await context.bot.edit_message_caption(
        chat_id=GROUP,
        message_id=mid,
        caption=initial_caption,
        reply_markup=kb
    )

    auctions[mid] = {
        "price": price, "start": price, "name": name, "cond": cond, "loc": loc,
        "comment": comment, "lead": None,
        "end": datetime.now() + timedelta(hours=1)
    }

    await notify(f"НОВЫЙ ЛОТ от @{seller}\n{name}\nСтарт: {price:,} ₽")
    context.job_queue.run_repeating(tick, interval=3, data=mid)

# ====== ДИАЛОГ ======
async def start_sell(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Давай выставим лот! 🚀 Фото (или 'нет')")
    return PHOTO

async def get_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['photo'] = update.message.photo[-1].file_id if update.message.photo else None
    await update.message.reply_text("Название")
    return NAME

async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['name'] = update.message.text.strip() or "Без названия"
    await update.message.reply_text("Состояние")
    return COND

async def get_cond(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['cond'] = update.message.text.strip() or "—"
    await update.message.reply_text("Локация")
    return LOC

async def get_loc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['loc'] = update.message.text.strip() or "—"
    await update.message.reply_text("Стартовая цена")
    return PRICE

async def get_price_dialog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['price'] = get_price(update.message.text)
    await update.message.reply_text("Комментарий/описание (можно 'нет')")
    return COMMENT

async def get_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    comment = update.message.text.strip()
    if comment.lower() in ["нет", "пропустить", ""]: comment = ""
    seller = update.effective_user.username or update.effective_user.first_name or "пользователь"

    await create_lot(
        context,
        context.user_data.get('photo'),
        context.user_data['name'],
        context.user_data['cond'],
        context.user_data['loc'],
        context.user_data['price'],
        comment,
        seller
    )
    await update.message.reply_text("Готово! Лот в группе 🔥")
    return ConversationHandler.END

async def cancel(update: Update, _):
    await update.message.reply_text("Отменено.")
    return ConversationHandler.END

# ====== КАНАЛ ======
async def channel_lot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.channel_post
    if not msg or msg.chat.id != CHANNEL_ID: return
    text = (msg.caption or msg.text or "")
    if "#аукцион" not in text.lower(): return

    price = get_price(text)
    name = cond = loc = comment = ""
    lines = text.splitlines()
    for line in lines:
        low = line.lower()
        if low.startswith("название:"): name = line.split(":",1)[1].strip()
        if low.startswith("состояние:"): cond = line.split(":",1)[1].strip()
        if low.startswith("локация:"): loc = line.split(":",1)[1].strip()
        if low.startswith("старт"): price = get_price(line)

    # Всё после основных полей — комментарий
    comment_lines = []
    started = False
    for line in lines:
        if line.lower().lstrip().startswith(("название:", "состояние:", "локация:", "старт", "#аукцион")):
            started = False
            continue
        if "#аукцион" in line.lower():
            started = True
            continue
        if started or line.strip():
            comment_lines.append(line.strip())
    comment = "\n".join([l for l in comment_lines if l])

    photo = msg.photo[-1].file_id if msg.photo else None
    await create_lot(context, photo, name or "Лот", cond or "—", loc or "—", price, comment, "канал")

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

    await notify(f"СТАВКА +{amt}₽\n@{user}\n{lot['name']}\nТекущая: {lot['price']:,} ₽")
    await q.answer(f"+{amt}₽ — ты лидер!", show_alert=True)

# ====== ЗАПУСК ======
app = Application.builder().token(TOKEN).build()

conv = ConversationHandler(
    entry_points=[CommandHandler("sell", start_sell)],
    states={
        PHOTO: [MessageHandler(filters.PHOTO | filters.TEXT, get_photo)],
        NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
        COND: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_cond)],
        LOC: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_loc)],
        PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_price_dialog)],
        COMMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_comment)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)

app.add_handler(conv)
app.add_handler(MessageHandler(filters.ChatType.CHANNEL & filters.Regex(r"(?i)#аукцион"), channel_lot))
app.add_handler(CallbackQueryHandler(bid, pattern=r"^\d+_\d+$"))

print("БОТ ЗАПУЩЕН — КНОПКИ АКТИВНЫ СРАЗУ, ТАЙМЕР ТИКАЕТ!")
if __name__ == '__main__':
    print("АУКЦИОН-БОТ ЗАПУЩЕН НА RAILWAY 24/7 🔥")
    app.run_polling(
        drop_pending_updates=True,
        allowed_updates=Update.ALL_TYPES
    )
