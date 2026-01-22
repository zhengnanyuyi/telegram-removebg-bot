# ================================
# Echo AI 抠图 Bot（稳定版 · rembg）
# ================================

import os
import json
import tempfile
from PIL import Image
import asyncio
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)
# ✅ 正确：在 handle_photo 里
from rembg import remove

# ================================
# 环境变量
# ================================
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_LINK = os.getenv("CHANNEL_LINK", "https://t.me/EchoAICut")

if not BOT_TOKEN:
    raise RuntimeError("❌ 缺少 BOT_TOKEN")

# ================================
# 配置
# ================================
MAX_FREE_TIMES = 3
USAGE_FILE = "/tmp/user_usage.json"

# ================================
# 用户数据
# ================================
def load_usage():
    if os.path.exists(USAGE_FILE):
        with open(USAGE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_usage(data):
    with open(USAGE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)

user_usage = load_usage()

# ================================
# 键盘
# ================================
MAIN_KEYBOARD = [
    ["✂️ 抠图"],
    ["📊 今日剩余次数"]
]

# ================================
# /start
# ================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 欢迎使用 Echo AI 抠图 Bot\n\n"
        "📸 直接发送图片即可自动抠图\n"
        "🎁 每天免费 3 次\n"
        "⚡ 稳定 / 快速 / 干净",
        reply_markup=ReplyKeyboardMarkup(MAIN_KEYBOARD, resize_keyboard=True)
    )

# ================================
# 文本
# ================================
async def reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)

    if user_id not in user_usage:
        user_usage[user_id] = {"count": 0}
        save_usage(user_usage)

    if update.message.text == "📊 今日剩余次数":
        used = user_usage[user_id]["count"]
        remaining = max(0, MAX_FREE_TIMES - used)
        await update.message.reply_text(
            f"📊 今日已使用 {used} 次\n剩余 {remaining} 次"
        )
        return

    await update.message.reply_text("📸 请直接发送图片")

# ================================
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)

    if user_id not in user_usage:
        user_usage[user_id] = {"count": 0}

    if user_usage[user_id]["count"] >= MAX_FREE_TIMES:
        await update.message.reply_text(
            f"🚫 今日免费次数已用完\n\n👉 关注频道获取更多机会：\n{CHANNEL_LINK}"
        )
        return

    user_usage[user_id]["count"] += 1
    save_usage(user_usage)

    await update.message.reply_text("⏳ 正在抠图，请稍等...")

    photo = update.message.photo[-1]
    file = await photo.get_file()

    with tempfile.TemporaryDirectory() as tmp:
        input_path = os.path.join(tmp, "input.png")
        output_path = os.path.join(tmp, "output.png")

        await file.download_to_drive(input_path)

        # 🔑 这里改成异步线程池执行 remove
        loop = asyncio.get_running_loop()
        with open(input_path, "rb") as i:
            input_bytes = i.read()

        result = await loop.run_in_executor(
            None,      # 使用默认线程池
            remove,    # 传入阻塞函数
            input_bytes
        )

        with open(output_path, "wb") as o:
            o.write(result)

        remaining = max(0, MAX_FREE_TIMES - user_usage[user_id]["count"])

        await update.message.reply_photo(
            photo=open(output_path, "rb"),
            caption=f"✅ 抠图完成\n今日剩余 {remaining} 次"
        )

# 启动
# ================================
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, reply))

    print("🤖 Echo AI Bot 已启动")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
