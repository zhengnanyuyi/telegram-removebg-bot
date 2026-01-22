# ================================
# Echo AI 抠图 Bot（完整稳定版）
# ================================

import os
import json
import tempfile
import traceback
import requests

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
# 一、环境变量（在 Railway 设置）
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
USAGE_FILE = "/tmp/user_usage.json"  # Railway 可用

# ================================
# 三、用户数据读写
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

# 用户数据结构：
# user_usage[user_id] = {
#   "count": 已使用次数,
#   "bonus_granted": 是否已给过加群奖励
# }
user_usage = load_usage()

# ================================
# 四、按钮
# ================================
MAIN_KEYBOARD = [
    ["✂️ 抠图"],
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
# 六、文字按钮处理
# ================================
async def reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    text = update.message.text.strip()

    # 初始化用户
    if user_id not in user_usage:
        user_usage[user_id] = {
            "count": 0,
            "bonus_granted": False
        }
        save_usage(user_usage)

    # 今日剩余次数
    if text == "📊 今日剩余次数":
        used = user_usage[user_id]["count"]
        remaining = max(0, MAX_FREE_TIMES - used)

        msg = f"📊 今日已使用 {used} 次\n剩余 {remaining} 次"

        if remaining == 0:
            if user_usage[user_id]["bonus_granted"]:
                msg += (
                    "\n\n💎 会员功能内测中\n"
                    "📌 权益：\n"
                    "• 无限抠图\n"
                    "• 更快处理\n"
                    "• 高清输出\n\n"
                    "👉 回复「会员」加入候补"
                )
            else:
                msg += f"\n\n🎁 加入群组可解锁 +1 次：\n{CHANNEL_LINK}"

        await update.message.reply_text(msg)
        return

    # 升级会员
    if text == "💎 升级会员":
        await update.message.reply_text(
            "💎 会员功能内测中\n\n"
            "📌 权益：\n"
            "• 无限抠图\n"
            "• 更快处理\n"
            "• 高清输出\n\n"
            "👉 回复「会员」加入候补名单"
        )
        return

    await update.message.reply_text(
        "请直接发送图片，或使用下方按钮👇",
        reply_markup=ReplyKeyboardMarkup(MAIN_KEYBOARD, resize_keyboard=True)
    )

# ================================
# 七、图片抠图核心逻辑
# ================================

# ================================
# 七、图片抠图核心逻辑
# ================================
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import traceback
    from PIL import Image
    import tempfile
    import os
    import requests

    user_id = str(update.message.from_user.id)

    # 初始化用户
    if user_id not in user_usage:
        user_usage[user_id] = {
            "count": 0,
            "bonus_granted": False
        }

    # 次数检查
    if user_usage[user_id]["count"] >= MAX_FREE_TIMES:
        if user_usage[user_id]["bonus_granted"]:
            await update.message.reply_text(
                "🚫 今日免费次数已用完\n\n"
                "💎 会员功能内测中\n"
                "👉 回复「会员」加入候补"
            )
        else:
            await update.message.reply_text(
                f"🚫 今日免费次数已用完\n\n"
                f"🎁 加群即可解锁 +1 次：\n{CHANNEL_LINK}"
            )
        return

    # 使用次数 +1
    user_usage[user_id]["count"] += 1
    save_usage(user_usage)

    await update.message.reply_text("⏳ 正在抠图，请稍等 3~8 秒...")

    try:
        # 获取文件
        photo = update.message.photo[-1]
        file = await photo.get_file()

        with tempfile.TemporaryDirectory() as tmp:
            input_path = os.path.join(tmp, "input.jpg")
            output_path = os.path.join(tmp, "output.png")

            await file.download_to_drive(input_path)

            # 打印原图尺寸
            with Image.open(input_path) as img:
                print(f"📥 原图尺寸: {img.width} x {img.height}")

            # 调用 remove.bg
            with open(input_path, "rb") as f:
                response = requests.post(
                    "https://api.remove.bg/v1.0/removebg",
                    files={"image_file": f},
                    data={"size": "auto"},
                    headers={"X-Api-Key": REMOVE_BG_API_KEY},
                    timeout=60
                )

            if response.status_code == 200:
                with open(output_path, "wb") as f:
                    f.write(response.content)

                # 打印输出尺寸
                with Image.open(output_path) as out:
                    print(f"📤 输出尺寸: {out.width} x {out.height}")

                remaining = max(0, MAX_FREE_TIMES - user_usage[user_id]["count"])
                await update.message.reply_photo(
                    photo=open(output_path, "rb"),
                    caption=f"✅ 抠图完成\n今日剩余 {remaining} 次"
                )
            else:
                await update.message.reply_text("❌ 抠图失败，请稍后再试")

    except Exception as e:
        # 打印完整异常堆栈
        traceback_str = traceback.format_exc()
        print("🚨 异常信息:\n", traceback_str)
        await update.message.reply_text(
            f"⚠️ 系统异常，请稍后再试\n错误信息: {str(e)}"
        )



    except Exception as e:
        import traceback
        traceback_str = traceback.format_exc()
        print("🚨 异常信息:\n", traceback_str)  # 打印到服务器日志
        await update.message.reply_text(
            f"⚠️ 系统异常，请稍后再试\n错误信息: {str(e)}"
        )

# ================================
# 八、加群奖励（只给一次）
# ================================
async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.chat_member.new_chat_member.user.id)

    if user_id not in user_usage:
        user_usage[user_id] = {
            "count": 0,
            "bonus_granted": False
        }

    if user_usage[user_id]["bonus_granted"]:
        return

    user_usage[user_id]["count"] += 1
    user_usage[user_id]["bonus_granted"] = True
    save_usage(user_usage)

    try:
        await context.bot.send_message(
            chat_id=user_id,
            text="🎉 欢迎加入 Echo AI！\n已解锁 +1 次免费抠图"
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
