# =========================================
# Echo AI Bot - 最终稳定版
# 功能：AI 抠图（rembg）+ 背景替换 + 对比图
# 平台：Replit / Railway
# =========================================

import os
import json
import tempfile
import shutil
from datetime import date
from PIL import Image
from rembg import remove

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
    CallbackQueryHandler,
)

# =========================================
# 基础配置
# =========================================
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_LINK = os.getenv("CHANNEL_LINK", "https://t.me/EchoAICut")

MAX_FREE_TIMES = 3
USAGE_FILE = "user_usage.json"

if not BOT_TOKEN:
    raise RuntimeError("❌ 缺少 BOT_TOKEN，请在平台环境变量中设置")

# 可选背景颜色
BG_COLORS = {
    "透明": None,
    "白色": (255, 255, 255),
    "黑色": (0, 0, 0),
    "红色": (255, 0, 0),
    "蓝色": (0, 0, 255),
}

# =========================================
# 使用次数记录（每天重置）
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
MAIN_KEYBOARD = [["✂️ 抠图"], ["📊 今日剩余次数"]]
BG_KEYBOARD = [
    [InlineKeyboardButton(name, callback_data=name)]
    for name in BG_COLORS.keys()
]

# =========================================
# /start
# =========================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 欢迎使用 Echo AI 抠图 Bot\n\n"
        "📸 发送图片 → AI 自动抠图\n"
        "🎨 选择背景颜色（或透明）\n"
        "🔍 同时输出对比图\n"
        "🎁 每天免费 3 次\n\n"
        "直接发图开始吧！",
        reply_markup=ReplyKeyboardMarkup(MAIN_KEYBOARD, resize_keyboard=True),
    )

# =========================================
# 文本处理
# =========================================
async def reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    today = str(date.today())

    if user_id not in user_usage:
        user_usage[user_id] = {"count": 0, "last_date": today}

    if user_usage[user_id]["last_date"] != today:
        user_usage[user_id]["count"] = 0
        user_usage[user_id]["last_date"] = today

    save_usage(user_usage)

    if update.message.text == "📊 今日剩余次数":
        used = user_usage[user_id]["count"]
        remaining = max(0, MAX_FREE_TIMES - used)
        msg = f"📊 今日已使用 {used} 次\n剩余 {remaining} 次"
        if remaining == 0:
            msg += f"\n\n👉 加入频道可获取更多机会：\n{CHANNEL_LINK}"
        await update.message.reply_text(msg)
        return

    await update.message.reply_text("📸 请直接发送图片进行处理～")

# =========================================
# 图片处理（AI 抠图）
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
            f"🚫 今日免费次数已用完\n\n👉 加入频道获取更多机会：\n{CHANNEL_LINK}"
        )
        return

    user_usage[user_id]["count"] += 1
    save_usage(user_usage)

    await update.message.reply_text("⏳ 正在 AI 抠图，请稍等 3～8 秒...")
    user_id = str(update.effective_user.id)
    photo = update.message.photo[-1]
    file = await photo.get_file()

    tmp_dir = tempfile.mkdtemp(prefix="echoai_")
    input_path = os.path.join(tmp_dir, "input.jpg")
    cut_path = os.path.join(tmp_dir, "cut.png")
    compare_path = os.path.join(tmp_dir, "compare.jpg")

    try:
        await file.download_to_drive(input_path)

        # ===== 真·AI 抠图（rembg）=====
        with open(input_path, "rb") as f:
            result = remove(f.read())

        with open(cut_path, "wb") as f:
            f.write(result)

        # ===== 原图 vs 抠图对比 =====
        orig = Image.open(input_path).convert("RGB")
        cut = Image.open(cut_path).convert("RGBA")

        compare = Image.new("RGB", (orig.width * 2, orig.height))
        compare.paste(orig, (0, 0))
        compare.paste(cut.convert("RGB"), (orig.width, 0))
        compare.save(compare_path)

        remaining = max(0, MAX_FREE_TIMES - user_usage[user_id]["count"])

        context.user_data["tmp_dir"] = tmp_dir
        context.user_data["cut_path"] = cut_path
        context.user_data["compare_path"] = compare_path
        context.user_data["remaining"] = remaining

        await update.message.reply_text(
            f"✅ 抠图完成！请选择背景颜色\n今日剩余 {remaining} 次",
            reply_markup=InlineKeyboardMarkup(BG_KEYBOARD),
        )

    except Exception as e:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        print("处理失败:", e)
        await update.message.reply_text("⚠️ 图片处理失败，请稍后再试")

# =========================================
# 背景选择
# =========================================
async def bg_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    color_name = query.data
    cut_path = context.user_data.get("cut_path")
    compare_path = context.user_data.get("compare_path")
    tmp_dir = context.user_data.get("tmp_dir")
    remaining = context.user_data.get("remaining", 0)

    if not cut_path or not os.path.exists(cut_path):
        await query.edit_message_text("⚠️ 文件已失效，请重新发送图片")
        return

    fg = Image.open(cut_path).convert("RGBA")
    bg_color = BG_COLORS[color_name]

    if bg_color:
        bg = Image.new("RGBA", fg.size, bg_color + (255,))
        bg.paste(fg, (0, 0), fg.split()[3])
        final_img = bg
    else:
        final_img = fg

    final_path = os.path.join(tmp_dir, "final.png")
    final_img.save(final_path)

    await query.edit_message_text(
        f"✅ 处理完成，背景：{color_name}\n今日剩余 {remaining} 次"
    )

    await query.message.reply_photo(
        photo=open(final_path, "rb"),
        caption=f"最终图片（背景：{color_name}）",
    )

    await query.message.reply_photo(
        photo=open(compare_path, "rb"),
        caption="原图 vs 抠图对比（左原右处理）",
    )

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

    print("🤖 Echo AI Bot 已启动")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
