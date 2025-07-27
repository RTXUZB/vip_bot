import os
import sqlite3
import logging
import asyncio
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)

# CONFIG
BOT_TOKEN = os.getenv("8172385229:AAGXNu7mmkr-Y6FWJbHOsuffXYCaFX6Hk_s") or "YOUR_BOT_TOKEN"
VIP_CHANNEL_ID = -2577241187  # Kanal ID (manfiy son)
ADMIN_IDS = [7050717288]  # Admin Telegram ID ro'yxati
PRICE = {1: 10000, 3: 50000, 6: 70000, 12: 100000}
PAY_INFO = "💳 To‘lov kartasi: 5614681001095854 MAXMUDOVA MAXBUBA +9989177353\n📸 To‘lov chekining rasmini yuboring."

# LOGGING
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# DB INIT
def init_db():
    conn = sqlite3.connect("vip.db")
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        telegram_id INTEGER UNIQUE,
        months INTEGER,
        expire TEXT,
        confirmed INTEGER DEFAULT 0
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER,
        file_id TEXT,
        approved INTEGER DEFAULT 0
    )""")
    conn.commit()
    conn.close()

# DB UTILS
def add_user(tid, months):
    expire = datetime.now() + timedelta(days=30 * months)
    conn = sqlite3.connect("vip.db")
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO users (telegram_id, months, expire, confirmed) VALUES (?, ?, ?, 0)",
              (tid, months, expire.isoformat()))
    c.execute("INSERT INTO payments (telegram_id, file_id) VALUES (?, '')", (tid,))
    conn.commit(); conn.close()

def save_payment_file(tid, file_id):
    conn = sqlite3.connect("vip.db")
    c = conn.cursor()
    c.execute("UPDATE payments SET file_id = ? WHERE telegram_id = ? AND approved = 0", (file_id, tid))
    conn.commit(); conn.close()

def approve_user(tid):
    conn = sqlite3.connect("vip.db")
    c = conn.cursor()
    c.execute("UPDATE payments SET approved = 1 WHERE telegram_id = ?", (tid,))
    c.execute("UPDATE users SET confirmed = 1 WHERE telegram_id = ?", (tid,))
    conn.commit(); conn.close()

def get_confirmed_users():
    conn = sqlite3.connect("vip.db")
    c = conn.cursor()
    c.execute("SELECT telegram_id, expire FROM users WHERE confirmed = 1")
    rows = c.fetchall()
    conn.close()
    return rows

def remove_user(tid):
    conn = sqlite3.connect("vip.db")
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE telegram_id = ?", (tid,))
    conn.commit(); conn.close()

# COMMANDS
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton(f"{m} oy - {PRICE[m]} so‘m", callback_data=f"sub_{m}")] for m in PRICE]
    await update.message.reply_text("📅 Obuna turini tanlang:", reply_markup=InlineKeyboardMarkup(kb))

async def handle_sub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    months = int(query.data.split('_')[1])
    add_user(query.from_user.id, months)
    await query.message.reply_text(f"🧾 Obuna: {months} oy\n{PAY_INFO}")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file_id = update.message.photo[-1].file_id
    save_payment_file(update.effective_user.id, file_id)
    for admin in ADMIN_IDS:
        await context.bot.send_photo(chat_id=admin, photo=file_id,
            caption=f"🧾 Yangi to‘lov: {update.effective_user.id}\nTasdiqlash: /tasdiqla {update.effective_user.id}")
    await update.message.reply_text("✅ To‘lov qabul qilindi. Admin tekshiradi.")

async def tasdiqla(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Siz admin emassiz.")
        return
    if not context.args:
        await update.message.reply_text("Foydalanuvchi ID kiriting: /tasdiqla 123456789")
        return
    uid = int(context.args[0])
    approve_user(uid)
    try:
        link = await context.bot.create_chat_invite_link(chat_id=VIP_CHANNEL_ID, member_limit=1)
        await context.bot.send_message(chat_id=uid, text=f"🎉 To‘lov tasdiqlandi!\nVIP kanal: {link.invite_link}")
        await update.message.reply_text(f"✅ {uid} ga link yuborildi.")
    except Exception as e:
        await update.message.reply_text(f"❌ Link yuborishda xatolik: {e}")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    rows = get_confirmed_users()
    txt = f"📊 Obunachilar: {len(rows)}\n\n"
    for tid, exp in rows:
        exp_date = exp.split("T")[0]
        txt += f"👤 {tid} - Tugash: {exp_date}\n"
    await update.message.reply_text(txt)

# SCHEDULED TASK
async def check_expired(app):
    now = datetime.now()
    for tid, exp_str in get_confirmed_users():
        exp_date = datetime.fromisoformat(exp_str)
        if now > exp_date:
            try:
                await app.bot.ban_chat_member(chat_id=VIP_CHANNEL_ID, user_id=tid)
                await app.bot.unban_chat_member(chat_id=VIP_CHANNEL_ID, user_id=tid)
                remove_user(tid)
                logger.info(f"{tid} chiqarildi.")
            except Exception as e:
                logger.error(f"{tid} chiqarib bo‘lmadi: {e}")

async def periodic_task(app):
    while True:
        await check_expired(app)
        await asyncio.sleep(3600)  # 1 soatda bir marta tekshirish

# MAIN
async def main():
    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_sub))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CommandHandler("tasdiqla", tasdiqla))
    app.add_handler(CommandHandler("stats", stats))

    asyncio.create_task(periodic_task(app))
    print("Bot ishga tushdi...")
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())