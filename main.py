# ====== 一、导入库 ======
import os
import json
import tempfile
import traceback
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    MessageHandler,
    ContextTypes,
    filters,
    CommandHandler,
    ChatMemberHandler
)
import requests

# ====== 二、环境变量读取（必须在平台设置 Variables） ======
BOT_TOKEN = os.getenv("BOT_TOKEN")
REMOVE_BG_API_KEY = os.getenv("REMOVE_BG_API_KEY")
CHANNEL_LINK = os.getenv("CHANNEL_LINK", "https://t.me/EchoAICut")

if not BOT_TOKEN or not REMOVE_BG_API_KEY:
    print("错误：缺少 BOT_TOKEN 或 REMOVE_BG_API_KEY 环境变量！")
    exit(1)

# ====== 三、配置 ======
MAX_FREE_TIMES = 3
USAGE_FILE = "/tmp/user_usage.json"   # 使用 /tmp/ 持久化（重启后保留）

# 加载使用次数
def load_usage():
    if os.path.exists(USAGE_FILE):
        try:
            with open(USAGE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_usage(usage_dict):
    try:
        with open(USAGE_FILE, "w", encoding="utf-8") as f:
            json.dump(usage_dict, f, ensure_ascii=False)
    except Exception as e:
        print(f"保存使用次数失败: {e}")

user_usage = load_usage()

# 按钮键盘
MAIN_KEYBOARD = [["✂️ 抠图"], ["📊 今日剩余次数"], ["💎 升级会员"]]

# ====== 四、处理器 ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reply_markup = ReplyKeyboardMarkup(MAIN_KEYBOARD, resize_keyboard=True)
    await update.message.reply_text(
        "欢迎使用智能抠图 Bot 👋\n\n"
        "📸 直接发送图片即可自动抠图（透明背景）\n"
        "免费用户每天限 3 次，加入群组可额外 +1 次！",
        reply_markup=reply_markup
    )

async def reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)  # 用 str 做 key，避免 json 问题
    text = update.message.text.strip()

    if text == "📊 今日剩余次数":
        used = user_usage.get(user_id, 0)
        remaining = max(0, MAX_FREE_TIMES - used)
        msg = f"今日已使用 {used} 次，剩余 {remaining} 次"
        if remaining == 0:
            msg += f"\n\n🚫 今日免费抠图次数已用完🎁 加入 Echo AI 群组即可解锁「+1 次免费抠图」
                         💡 很多人每天都在群里用
                         👇 点击加入：{CHANNEL_LINK}"
        await update.message.reply_text(msg)
        return

    if text == "💎 升级会员":
        await update.message.reply_text(
            "💎 会员功能即将上线！\n\n"
            "即将解锁：\n"
            "✅ 无限抠图\n"
            "✅ 更高清输出\n"
            "✅ 优先处理\n\n"
            "私聊管理员了解详情～"
        )
        return

    # 其他文字 → 引导发图或用按钮
    reply_markup = ReplyKeyboardMarkup(MAIN_KEYBOARD, resize_keyboard=True)
    await update.message.reply_text("请直接发送照片，或使用下方按钮操作～", reply_markup=reply_markup)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)

    # 初始化 & 检查次数
    if user_id not in user_usage:
        user_usage[user_id] = 0

    if user_usage[user_id] >= MAX_FREE_TIMES:
        try:
            member = await context.bot.get_chat_member(chat_id="@EchoAICut", user_id=int(user_id))
            if member.status in ["member", "administrator", "creator"]:
                text = "🚫 今日免费次数已用完\n\n✅ 你已在 Echo AI 群组，可购买会员无限使用"
            else:
                text = f"🚫 今日免费次数已用完\n\n加入群组额外 +1 次：{CHANNEL_LINK}"
        except:
            text = f"🚫 今日免费次数已用完\n\n加入群组额外 +1 次：{CHANNEL_LINK}"
        await update.message.reply_text(text)
        return

    # 使用 +1 并保存
    user_usage[user_id] += 1
    save_usage(user_usage)

    await update.message.reply_text("⏳ 正在智能抠图，请稍等 3~8 秒...")

    try:
        photo = update.message.photo[-1]
        file = await photo.get_file()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = os.path.join(tmpdir, "input.jpg")
            output_path = os.path.join(tmpdir, "output.png")

            await file.download_to_drive(input_path)

            response = requests.post(
                "https://api.remove.bg/v1.0/removebg",
                files={"image_file": open(input_path, "rb")},
                data={"size": "auto"},
                headers={"X-Api-Key": REMOVE_BG_API_KEY},
                timeout=90
            )

            if response.status_code == 200:
                with open(output_path, "wb") as out:
                    out.write(response.content)

                reply_markup = ReplyKeyboardMarkup([["📊 今日剩余次数"], ["💎 升级会员"]], resize_keyboard=True)
                await update.message.reply_photo(
                    photo=open(output_path, "rb"),
                    caption=f"✅ 抠图完成！（PNG 透明背景）\n今日剩余 {max(0, MAX_FREE_TIMES - user_usage[user_id])} 次",
                    reply_markup=reply_markup
                )
            else:
                await update.message.reply_text(
                    f"❌ 抠图失败（状态码 {response.status_code}）\n可能是 API 额度问题或图片太复杂，请稍后再试"
                )

    except Exception as e:
        print(f"用户 {user_id} 抠图异常: {type(e).__name__} - {str(e)}")
        traceback.print_exc()
        await update.message.reply_text("⚠️ 服务器忙碌中，请稍后再试～")

    # TemporaryDirectory 会自动清理，无需手动 remove

async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_member = update.chat_member
    if chat_member.new_chat_member.status == "member":
        user_id = str(chat_member.new_chat_member.user.id)
        if user_id not in user_usage:
            user_usage[user_id] = 0
        user_usage[user_id] += 1
        save_usage(user_usage)

        remaining = max(0, MAX_FREE_TIMES - user_usage[user_id])
        try:
            await context.bot.send_message(
                chat_id=chat_member.new_chat_member.user.id,
                text=f"🎉 欢迎加入 Echo AI 群组！\n已为你增加 1 次免费抠图机会～\n今日剩余：{remaining} 次"
            )
        except Exception as e:
            print(f"无法私聊 {user_id}: {e}")

# ====== 五、启动 ======
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, reply))
    app.add_handler(ChatMemberHandler(welcome_new_member, ChatMemberHandler.CHAT_MEMBER))

    print("🤖 Bot 启动成功，正在轮询...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)
    drop_pending_updates=True,       # 强烈推荐加，丢弃旧更新，避免卡住
    poll_interval=0.5,               # 加快响应
    timeout=20                       # 超时设置
if __name__ == "__main__":
    main()# ← 只调用 main() 函数，不要重复写 app 和 run_polling
    
