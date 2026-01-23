# Echo AI Bot 全功能版（抠图 + 水印/马赛克还原 + 背景 + 并排对比图）
# 专为 Replit 优化版 - 2026

import os
import json
import tempfile
import asyncio
from datetime import date
from PIL import Image, ImageOps
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, filters, CallbackQueryHandler
)
from rembg import remove

# LaMa Inpainting（需要 lama-cleaner 包）
try:
    from lama_cleaner.model_manager import get_model
    from lama_cleaner.inference import load_model, inpaint_image
except ImportError:
    print("警告：未安装 lama-cleaner，请在 Shell 运行：pip install lama-cleaner")

# =========================================
# 配置（使用 Replit Secrets 环境变量）
# =========================================
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_LINK = os.getenv("CHANNEL_LINK", "https://t.me/EchoAICut")
MAX_FREE_TIMES = 3
USAGE_FILE = "user_usage.json"  # Replit 支持持久化文件

if not BOT_TOKEN:
    raise RuntimeError("缺少 BOT_TOKEN，请在 Replit Secrets 中添加 BOT_TOKEN")

# 可选背景颜色
BG_COLORS = {
    "透明": None,
    "白色": (255, 255, 255),
    "黑色": (0, 0, 0),
    "红色": (255, 0, 0),
    "蓝色": (0, 0, 255)
}

# =========================================
# 用户使用记录（每天重置）
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
        print(f"保存使用记录失败: {e}")

user_usage = load_usage()

# =========================================
# 键盘
# =========================================
MAIN_KEYBOARD = [
    ["✂️ 抠图"],
    ["📊 今日剩余次数"]
]

BG_KEYBOARD = [
    [InlineKeyboardButton(name, callback_data=name)] for name in BG_COLORS.keys()
]

# =========================================
# /start 欢迎
# =========================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 欢迎使用 Echo AI Bot\n\n"
        "📸 发送图片即可抠图 + 水印/马赛克还原\n"
        "🎨 可选择背景颜色\n"
        "🎁 每天免费 3 次\n\n"
        "直接发图开始吧！",
        reply_markup=ReplyKeyboardMarkup(MAIN_KEYBOARD, resize_keyboard=True)
    )

# =========================================
# 文本回复
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
            msg += f"\n\n免费次数用完啦！加入频道再领：{CHANNEL_LINK}"
        await update.message.reply_text(msg)
        return

    await update.message.reply_text("📸 请直接发送图片进行处理哦～")

# =========================================
# 异步执行阻塞函数（Replit 兼容）
# =========================================
async def run_blocking(func, *args):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, func, *args)

# =========================================
# 图片处理核心
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

    await update.message.reply_text("⏳ 正在高清处理图片（抠图 + 修复 + 对比），请稍等 5~15 秒...")

    try:
        photo = update.message.photo[-1]
        file = await photo.get_file()

        with tempfile.TemporaryDirectory() as tmp:
            input_path = os.path.join(tmp, "input.jpg")
            cutout_path = os.path.join(tmp, "cutout.png")
            restored_path = os.path.join(tmp, "restored.png")
            compare_path = os.path.join(tmp, "compare.jpg")

            await file.download_to_drive(input_path)

            # 阶段1：抠图 (rembg)
            with open(input_path, "rb") as f:
                input_bytes = f.read()
            cutout_bytes = await run_blocking(remove, input_bytes)
            with open(cutout_path, "wb") as f:
                f.write(cutout_bytes)

            # 阶段2：LaMa 水印/马赛克修复
            try:
                model = get_model("lama")
                inpaint_model = await run_blocking(load_model, model)
                im = Image.open(cutout_path).convert("RGBA")
                alpha = im.split()[-1]
                mask = Image.eval(alpha, lambda a: 255 if a < 250 else 0).convert("L")
                restored = await run_blocking(inpaint_image, inpaint_model, im.convert("RGB"), mask)
                restored.save(restored_path)
            except Exception as lama_err:
                print(f"LaMa 修复失败: {lama_err}")
                # 如果 LaMa 失败，fallback 到抠图结果
                Image.open(cutout_path).save(restored_path)

            # 阶段3：生成并排对比图
            orig = Image.open(input_path).convert("RGB")
            final = Image.open(restored_path).convert("RGB")
            compare_img = Image.new("RGB", (orig.width * 2, orig.height))
            compare_img.paste(orig, (0, 0))
            compare_img.paste(final, (orig.width, 0))
            compare_img.save(compare_path)

            remaining = max(0, MAX_FREE_TIMES - user_usage[user_id]["count"])

            # 发送临时对比图 + 背景选择
            context.user_data["restored_path"] = restored_path
            context.user_data["compare_path"] = compare_path
            context.user_data["remaining"] = remaining

            await update.message.reply_text(
                f"🎨 抠图 & 修复完成！请选择背景颜色（或透明）\n今日剩余 {remaining} 次",
                reply_markup=InlineKeyboardMarkup(BG_KEYBOARD)
            )

    except Exception as e:
        print(f"处理失败 - 用户 {user_id}: {str(e)}")
        await update.message.reply_text("⚠️ 处理失败，请稍后再试或换张清晰照片～")

# =========================================
# 背景选择回调
# =========================================
async def bg_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    color_name = query.data
    restored_path = context.user_data.get("restored_path")
    compare_path = context.user_data.get("compare_path")
    remaining = context.user_data.get("remaining", 0)

    if not restored_path:
        await query.edit_message_text("⚠️ 文件丢失，请重新发送图片。")
        return

    fg = Image.open(restored_path).convert("RGBA")
    bg_color = BG_COLORS.get(color_name)

    if bg_color:
        bg_img = Image.new("RGBA", fg.size, bg_color + (255,))
        bg_img.paste(fg, (0, 0), fg.split()[3])
    else:
        bg_img = fg

    final_bg_path = restored_path.replace(".png", "_bg.png")
    bg_img.save(final_bg_path)

    await query.edit_message_text(
        f"✅ 处理完成，背景：{color_name}\n今日剩余 {remaining} 次"
    )

    # 发送最终图片
    await query.message.reply_photo(
        photo=open(final_bg_path, "rb"),
        caption="📸 最终高清图片（点击可放大）"
    )

    # 发送对比图
    await query.message.reply_photo(
        photo=open(compare_path, "rb"),
        caption="🔍 原图 vs 处理后对比（左原右处理）"
    )

# =========================================
# 启动 Bot
# =========================================
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, reply))
    app.add_handler(CallbackQueryHandler(bg_callback))

    print("🤖 Echo AI Bot 全功能版已启动 - Replit 优化版")
    app.run_polling(
        drop_pending_updates=True,
        poll_interval=0.5,
        timeout=20
    )

if __name__ == "__main__":
    main()
