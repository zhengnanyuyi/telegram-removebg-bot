# ================================
# Echo AI 抠图 Bot（Railway 稳定版）
# ================================

import os
import json
import tempfile
import traceback
import requests

import torch
from PIL import Image
from realesrgan import RealESRGAN

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    MessageHandler,
    ContextTypes,
    filters,
    CommandHandler,
    ChatMemberHandler
)

# ================================
# 一、环境变量
# ================================
BOT_TOKEN = os.getenv("BOT_TOKEN")
REMOVE_BG_API_KEY = os.getenv("REMOVE_BG_API_KEY")
CHANNEL_LINK = os.getenv("CHANNEL_LINK", "https://t.me/EchoAICut")

if not BOT_TOKEN or not REMOVE_BG_API_KEY:
    raise RuntimeError("❌ 缺少 BOT_TOKEN 或 REMOVE_BG_API_KEY")

# ================================
# 二、基础配置
# ================================
MAX_FREE_TIMES = 3
USAGE_FILE = "/tmp/user_usage.json"  # Railway 可写目录

# ================================
# 三、用户数据
# ================================
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
        json.dump(data, f, ensure_ascii=False)

user_usage = load_usage()

# ================================
# 四、按钮
# ================================
MAIN_KEYBOARD = [
    ["📊 今日剩余次数"],
    ["💎 升级会员"]
]

# ================================
# 五、/start
# ================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 欢迎使用 Echo AI 抠图 Bot\n\n"
        "📸 直接发送图片即可自动抠图\n"
        "🎁 每天免费 3 次\n"
        "➕ 加群可额外解锁 1 次",
        reply_markup=ReplyKeyboardMarkup(MAIN_KEYBOARD, resize_keyboard=True)
    )

# ================================
# 六、文字按钮
# ================================
async def reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    text = update.message.text.strip()

    if user_id not in user_usage:
        user_usage[user_id] = {"count": 0, "bonus_granted": False}
        save_usage(user_usage)

    if text == "📊 今日剩余次数":
        used = user_usage[user_id]["count"]
        remaining = max(0, MAX_FREE_TIMES - used)

        msg = f"📊 今日已使用 {used} 次\n剩余 {remaining} 次"

        if remaining == 0:
            if user_usage[user_id]["bonus_granted"]:
                msg += "\n\n💎 会员功能内测中\n👉 回复「会员」加入候补"
            else:
                msg += f"\n\n🎁 加群解锁 +1 次：\n{CHANNEL_LINK}"

        await update.message.reply_text(msg)
        return

    if text == "💎 升级会员":
        await update.message.reply_text(
            "💎 会员功能内测中\n\n"
            "• 无限抠图\n"
            "• 更快处理\n"
            "• 高清输出\n\n"
            "👉 回复「会员」加入候补"
        )
        return

    await update.message.reply_text("请直接发送图片 📸")

# ================================
# 七、图片处理
# ================================
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)

    if user_id not in user_usage:
        user_usage[user_id] = {"count": 0, "bonus_granted": False}

    if user_usage[user_id]["count"] >= MAX_FREE_TIMES:
        if user_usage[user_id]["bonus_granted"]:
            await update.message.reply_text("🚫 今日次数已用完\n💎 回复「会员」了解升级")
        else:
            await update.message.reply_text(
                f"🚫 今日次数已用完\n🎁 加群解锁 +1 次：\n{CHANNEL_LINK}"
            )
        return

    user_usage[user_id]["count"] += 1
    save_usage(user_usage)

    await update.message.reply_text("⏳ 正在抠图并高清增强，请稍等...")

    try:
        photo = update.message.photo[-1]
        file = await photo.get_file()

        with tempfile.TemporaryDirectory() as tmp:
            input_path = os.path.join(tmp, "input.jpg")
            output_path = os.path.join(tmp, "output.png")
            enhanced_path = os.path.join(tmp, "enhanced.png")

            await file.download_to_drive(input_path)

            # remove.bg
            response = requests.post(
                "https://api.remove.bg/v1.0/removebg",
                files={"image_file": open(input_path, "rb")},
                data={"size": "auto"},
                headers={"X-Api-Key": REMOVE_BG_API_KEY},
                timeout=60
            )

            if response.status_code != 200:
                await update.message.reply_text("❌ 抠图失败，请稍后再试")
                return

            with open(output_path, "wb") as f:
                f.write(response.content)

            # Real-ESRGAN
            weights = "/tmp/RealESRGAN_x2.pth"
            if not os.path.exists(weights):
                url = "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/RealESRGAN_x2.pth"
                r = requests.get(url, stream=True)
                with open(weights, "wb") as f:
                    for c in r.iter_content(8192):
                        f.write(c)

            device = "cuda" if torch.cuda.is_available() else "cpu"
            model = RealESRGAN(device, scale=2)
            model.load_weights(weights)

            img = Image.open(output_path).convert("RGB")
            out = model.predict(img)
            out.save(enhanced_path)

            remaining = max(0, MAX_FREE_TIMES - user_usage[user_id]["count"])

            await update.message.reply_photo(
                photo=open(enhanced_path, "rb"),
                caption=f"✅ 抠图完成\n今日剩余 {remaining} 次"
            )

    except Exception:
        traceback.print_exc()
        await update.message.reply_text("⚠️ 系统异常，请稍后再试")

# ================================
# 八、加群奖励
# ================================
async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.chat_member.new_chat_member.user.id)

    if user_id not in user_usage:
        user_usage[user_id] = {"count": 0, "bonus_granted": False}

    if user_usage[user_id]["bonus_granted"]:
        return

    user_usage[user_id]["count"] += 1
    user_usage[user_id]["bonus_granted"] = True
    save_usage(user_usage)

    try:
        await context.bot.send_message(
            chat_id=user_id,
            text="🎉 欢迎加入 Echo AI！已解锁 +1 次抠图"
        )
    except:
        pass

# ================================
# 九、启动
# ================================
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, reply))
    app.add_handler(ChatMemberHandler(welcome_new_member, ChatMemberHandler.CHAT_MEMBER))

    print("🤖 Echo AI Bot 已启动")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
