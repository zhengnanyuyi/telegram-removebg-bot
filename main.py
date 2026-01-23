# Echo AI Bot - 修复版（持久化临时文件，避免回调时文件丢失）

import os
import json
import tempfile
import shutil  # 用于清理
from datetime import date
from PIL import Image
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
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
    raise RuntimeError("缺少 BOT_TOKEN 环境变量！请检查 Railway Variables")

BG_COLORS = {
    "透明": None,
    "白色": (255, 255, 255),
    "黑色": (0, 0, 0),
    "红色": (255, 0, 0),
    "蓝色": (0, 0, 255)
}

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
    try:
        with open(USAGE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"保存失败: {e}")

user_usage = load_usage()

# =========================================
# 键盘
# =========================================
MAIN_KEYBOARD = [["✂️ 抠图"], ["📊 今日剩余次数"]]
BG_KEYBOARD = [[InlineKeyboardButton(name, callback_data=name)] for name in BG_COLORS.keys()]

# =========================================
# /start
# =========================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 欢迎使用 Echo AI Bot\n\n"
        "📸 发送图片即可简单抠图 + 背景替换\n"
        "🎨 支持透明/白/黑/红/蓝背景\n"
        "🎁 每天免费 3 次\n\n"
        "直接发图开始吧！",
        reply_markup=ReplyKeyboardMarkup(MAIN_KEYBOARD, resize_keyboard=True)
    )

# =========================================
# 文本处理
# =========================================
async def reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    text = update.message.text.strip()
    today = str(date.today())

    if user_id not in user_usage:
        user_usage[user_id] = {"count": 0, "last_date": today}
    if user_usage[user_id]["last_date"] != today:
        user_usage[user_id]["count"] = 0
        user_usage[user_id]["last_date"] = today
    save_usage(user_usage)

    if text == "📊 今日剩余次数":
        used = user_usage[user_id]["count"]
        remaining = max(0, MAX_FREE_TIMES - used)
        msg = f"📊 今日已使用 {used} 次\n剩余 {remaining} 次"
        if remaining == 0:
            msg += f"\n\n免费次数用完！加入频道再领：{CHANNEL_LINK}"
        await update.message.reply_text(msg)
        return

    await update.message.reply_text("📸 请直接发送图片进行处理哦～")

# =========================================
# 图片处理 - 保存到持久路径
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
        await update.message.reply_text(f"🚫 今日免费次数已用完\n\n👉 加入频道：{CHANNEL_LINK}")
        return

    user_usage[user_id]["count"] += 1
    save_usage(user_usage)

    await update.message.reply_text("⏳ 正在处理图片（简单抠图 + 对比），请稍等 2～5 秒...")

    try:
        photo = update.message.photo[-1]
        file = await photo.get_file()

        # 使用固定临时目录（不自动删）
        tmp_dir = tempfile.mkdtemp()
        input_path = os.path.join(tmp_dir, "input.jpg")
        output_path = os.path.join(tmp_dir, "output.png")
        compare_path = os.path.join(tmp_dir, "compare.jpg")

        await file.download_to_drive(input_path)

        # 简单阈值抠图
        im = Image.open(input_path).convert("RGBA")
        datas = im.getdata()
        new_data = []
        for item in datas:
            if item[0] > 240 and item[1] > 240 and item[2] > 240:
                new_data.append((255, 255, 255, 0))
            else:
                new_data.append(item)
        im.putdata(new_data)
        im.save(output_path)

        # 并排对比
        orig = Image.open(input_path).convert("RGB")
        final = Image.open(output_path).convert("RGB")
        compare_img = Image.new("RGB", (orig.width * 2, orig.height))
        compare_img.paste(orig, (0, 0))
        compare_img.paste(final, (orig.width, 0))
        compare_img.save(compare_path)

        remaining = max(0, MAX_FREE_TIMES - user_usage[user_id]["count"])

        # 保存路径给回调（包括 tmp_dir 以便清理）
        context.user_data["tmp_dir"] = tmp_dir
        context.user_data["output_path"] = output_path
        context.user_data["compare_path"] = compare_path
        context.user_data["remaining"] = remaining

        await update.message.reply_text(
            f"🎨 处理完成！请选择背景颜色（或透明）\n今日剩余 {remaining} 次",
            reply_markup=InlineKeyboardMarkup(BG_KEYBOARD)
        )

    except Exception as e:
        print(f"处理失败 - 用户 {user_id}: {str(e)}")
        await update.message.reply_text("⚠️ 处理失败，请稍后再试～")

# =========================================
# 背景回调（使用保存路径）
# =========================================
async def bg_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    color_name = query.data
    tmp_dir = context.user_data.get("tmp_dir")
    output_path = context.user_data.get("output_path")
    compare_path = context.user_data.get("compare_path")
    remaining = context.user_data.get("remaining", 0)

    if not output_path or not os.path.exists(output_path):
        await query.edit_message_text("⚠️ 文件已过期或丢失，请重新发送图片。")
        return

    fg = Image.open(output_path).convert("RGBA")
    bg_color = BG_COLORS.get(color_name)

    if bg_color:
        bg_img = Image.new("RGBA", fg.size, bg_color + (255,))
        bg_img.paste(fg, (0, 0), fg.split()[3])
    else:
        bg_img = fg

    final_bg_path = os.path.join(tmp_dir, "final_bg.png")
    bg_img.save(final_bg_path)

    await query.edit_message_text(
        f"✅ 处理完成，背景：{color_name}\n今日剩余 {remaining} 次"
    )

    await query.message.reply_photo(
        photo=open(final_bg_path, "rb"),
        caption="📸 最终图片"
    )

    await query.message.reply_photo(
        photo=open(compare_path, "rb"),
        caption="🔍 原图 vs 处理后对比"
    )

    # 清理临时文件夹（可选，防止积累）
    try:
        shutil.rmtree(tmp_dir)
    except:
        pass

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
    app.run_polling(
        drop_pending_updates=True,
        poll_interval=0.5,
        timeout=20
    )

if __name__ == "__main__":
    main()
