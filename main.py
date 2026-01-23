# =========================================
# Echo AI Bot - 稳定可运行版（Railway 免费）
# 功能：
# - 抠图（OpenCV GrabCut，稳定）
# - 背景替换
# - 原图 vs 处理图 对比
# - 使用次数限制（每日重置）
#
# ⚠️ AI 功能（rembg / LaMa）已保留但【全部注释】
# =========================================

import os
import json
import tempfile
import shutil
from datetime import date

import cv2
import numpy as np
from PIL import Image

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
    CallbackQueryHandler
)

# =========================================
# 配置
# =========================================
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_LINK = os.getenv("CHANNEL_LINK", "https://t.me/EchoAICut")

MAX_FREE_TIMES = 3
USAGE_FILE = "user_usage.json"

if not BOT_TOKEN:
    raise RuntimeError("❌ 缺少 BOT_TOKEN 环境变量")

BG_COLORS = {
    "透明": None,
    "白色": (255, 255, 255),
    "黑色": (0, 0, 0),
    "红色": (255, 0, 0),
    "蓝色": (0, 0, 255),
}

# =========================================
# AI 抠图（⚠️ 保留但禁用）
# =========================================
"""
from rembg import remove
from lama_cleaner.model_manager import get_model
from lama_cleaner.inference import load_model, inpaint_image
"""

# =========================================
# 使用记录
# =========================================
def load_usage():
    if os.path.exists(USAGE_FILE):
        try:
            with open(USAGE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_usage(data):
    with open(USAGE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

user_usage = load_usage()

# =========================================
# 键盘
# =========================================
MAIN_KEYBOARD = [
    ["✂️ 抠图"],
    ["📊 今日剩余次数"]
]

BG_KEYBOARD = [
    [InlineKeyboardButton(name, callback_data=name)]
    for name in BG_COLORS.keys()
]

# =========================================
# /start
# =========================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Echo AI Bot\n\n"
        "📸 发图 → 抠图\n"
        "🎨 选颜色 → 背景替换\n"
        "🔍 输出对比图\n\n"
        "🎁 每天免费 3 次",
        reply_markup=ReplyKeyboardMarkup(MAIN_KEYBOARD, resize_keyboard=True)
    )

# =========================================
# 文本消息
# =========================================
async def reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    today = str(date.today())
    text = update.message.text.strip()

    if user_id not in user_usage:
        user_usage[user_id] = {"count": 0, "last_date": today}

    if user_usage[user_id]["last_date"] != today:
        user_usage[user_id]["count"] = 0
        user_usage[user_id]["last_date"] = today

    save_usage(user_usage)

    if text == "📊 今日剩余次数":
        used = user_usage[user_id]["count"]
        remaining = max(0, MAX_FREE_TIMES - used)
        await update.message.reply_text(
            f"📊 今日已使用 {used} 次\n剩余 {remaining} 次"
        )
        return

    await update.message.reply_text("📸 请直接发送图片")

# =========================================
# 核心：稳定抠图（GrabCut）
# =========================================
def grabcut_cutout(input_path, output_path):
    img = cv2.imread(input_path)
    h, w = img.shape[:2]

    mask = np.zeros((h, w), np.uint8)
    rect = (10, 10, w - 20, h - 20)

    bgdModel = np.zeros((1, 65), np.float64)
    fgdModel = np.zeros((1, 65), np.float64)

    cv2.grabCut(
        img, mask, rect,
        bgdModel, fgdModel,
        5, cv2.GC_INIT_WITH_RECT
    )

    mask2 = np.where(
        (mask == 2) | (mask == 0),
        0, 1
    ).astype("uint8")

    img = img * mask2[:, :, np.newaxis]

    rgba = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
    rgba[:, :, 3] = mask2 * 255

    Image.fromarray(rgba).save(output_path)

# =========================================
# 图片处理
# =========================================
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    today = str(date.today())

    if user_id not in user_usage:
        user_usage[user_id] = {"count": 0, "last_date": today}

    if user_usage[user_id]["last_date"] != today:
        user_usage[user_id]["count"] = 0
        user_usage[user_id]["last_date"] = today

    if user_usage[user_id]["count"] >= MAX_FREE_TIMES:
        await update.message.reply_text(
            f"🚫 今日次数用完\n👉 {CHANNEL_LINK}"
        )
        return

    user_usage[user_id]["count"] += 1
    save_usage(user_usage)

    await update.message.reply_text("⏳ 正在抠图，请稍等...")

    tmp_dir = tempfile.mkdtemp(prefix="echo_")

    try:
        photo = update.message.photo[-1]
        file = await photo.get_file()

        input_path = os.path.join(tmp_dir, "input.jpg")
        output_path = os.path.join(tmp_dir, "cut.png")
        compare_path = os.path.join(tmp_dir, "compare.jpg")

        await file.download_to_drive(input_path)

        # ===== 稳定抠图 =====
        grabcut_cutout(input_path, output_path)

        # ===== 对比图 =====
        orig = Image.open(input_path).convert("RGB")
        cut = Image.open(output_path).convert("RGB")

        compare = Image.new("RGB", (orig.width * 2, orig.height))
        compare.paste(orig, (0, 0))
        compare.paste(cut, (orig.width, 0))
        compare.save(compare_path)

        context.user_data["tmp_dir"] = tmp_dir
        context.user_data["output"] = output_path
        context.user_data["compare"] = compare_path
        context.user_data["remaining"] = MAX_FREE_TIMES - user_usage[user_id]["count"]

        await update.message.reply_text(
            "🎨 请选择背景颜色",
            reply_markup=InlineKeyboardMarkup(BG_KEYBOARD)
        )

    except Exception as e:
        print("❌ 错误:", e)
        await update.message.reply_text("⚠️ 处理失败")
        shutil.rmtree(tmp_dir, ignore_errors=True)

# =========================================
# 背景选择
# =========================================
async def bg_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    color = query.data
    output = context.user_data.get("output")
    compare = context.user_data.get("compare")
    tmp_dir = context.user_data.get("tmp_dir")
    remaining = context.user_data.get("remaining", 0)

    fg = Image.open(output).convert("RGBA")
    bg_color = BG_COLORS[color]

    if bg_color:
        bg = Image.new("RGBA", fg.size, bg_color + (255,))
        bg.paste(fg, (0, 0), fg)
    else:
        bg = fg

    final_path = os.path.join(tmp_dir, "final.png")
    bg.save(final_path)

    await query.edit_message_text(
        f"✅ 完成（背景：{color}）\n今日剩余 {remaining} 次"
    )

    await query.message.reply_photo(open(final_path, "rb"))
    await query.message.reply_photo(open(compare, "rb"))

    shutil.rmtree(tmp_dir, ignore_errors=True)

# =========================================
# 启动
# =========================================
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, reply))
    app.add_handler(CallbackQueryHandler(bg_callback))

    print("🤖 Echo AI Bot running (Railway Stable)")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
