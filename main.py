# ====== 一、导入库 ======
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters
from telegram import ReplyKeyboardMarkup
import requests  # 用来请求 remove.bg API
import os  # 删除临时文件
from telegram.ext import ChatMemberHandler


BOT_TOKEN = os.getenv("BOT_TOKEN")# ====== 机器人Token
REMOVE_BG_API_KEY = os.getenv("REMOVE_BG_API_KEY") # ====== remove.bg API KEY
CHANNEL_LINK = os.getenv("CHANNEL_LINK") # ====== 频道链接

# ====== 频道链接（用户超过次数时引导关注） ======
CHANNEL_LINK = "t.me/EchoAICut"

# ====== 使用次数限制配置 ======
MAX_FREE_TIMES = 3

# 用字典记录：{user_id: 使用次数}
user_usage = {}

# ====== 二、配置区 ======

# ⚠️ 换成你【新的】Telegram Bot Token
BOT_TOKEN = "8538021469:AAFziET1hRmGKCb_EP6m-7h8ZZnaNz_MCgY"
# ⚠️ 换成你自己的 remove.bg API Key
REMOVE_BG_API_KEY = "A8Tiwh7HpUhYe3Q3qtBbQfyi"


# ====== 三、处理文字消息 ======
async def reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text

    # ====== 按钮菜单 ======
    keyboard = [["✂️ 抠图"], ["📊 今日剩余次数"], ["💎 升级会员"]]

    reply_markup = ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

    # ====== 点击「今日剩余次数」=====
    if text == "📊 今日剩余次数":
        used = user_usage.get(user_id, 0)
        remaining = MAX_FREE_TIMES - used
        if remaining < 0:
            remaining = 0
        await update.message.reply_text(f"🚫 今日免费次数已用完（剩余 {remaining} 次）\n\n"
                                        "👉 加入Echo AI即可继续使用更多次数：\n" + CHANNEL_LINK)
        return


    
    # ====== 点击「升级会员」=====
    if text == "💎 升级会员":
        await update.message.reply_text("💎 会员功能即将上线\n\n"
                                        "✅ 无限抠图\n"
                                        "✅ 高清输出\n"
                                        "📩 私聊管理员了解")
        return

    # ====== 默认欢迎消息 ======
    await update.message.reply_text("欢迎使用智能抠图 Bot 👋\n\n"
                                    "📸 直接发送图片即可抠图",
                                    reply_markup=reply_markup)

group_members = set()  # 存 user_id
# 加入群组增加 1 次免费抠图机会
# 新增一个处理函数：用户加入群组时 +1 次数
async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_member = update.chat_member
    user = chat_member.new_chat_member.user

    if chat_member.new_chat_member.status == "member":
        user_id = user.id

        # 标记用户已经加入群组
        group_members.add(user_id)

        # 初始化次数
        if user_id not in user_usage:
            user_usage[user_id] = 0

        # 增加一次免费机会
        user_usage[user_id] += 1

        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"🎉 欢迎加入 Echo AI 群组！\n已为你增加 1 次免费抠图机会～\n今日剩余次数：{MAX_FREE_TIMES - user_usage[user_id] if user_usage[user_id] < MAX_FREE_TIMES else 0}"
            )
        except Exception as e:
            print(f"无法私聊用户 {user_id}: {e}")


# =====添加按钮功能
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    keyboard = [["✂️ 抠图"], ["📊 今日剩余次数"], ["💎 升级会员"]]
    reply_markup = ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)
    await update.message.reply_text(
        "欢迎使用智能抠图 Bot 👋\n\n📸 直接发送图片即可抠图\n请选择下面按钮操作：",
        reply_markup=reply_markup
    )


# ====== 四、处理图片消息（核心功能） ======
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ====== 0️⃣ 使用次数限制（必须最先） ======
    user_id = update.message.from_user.id

    # 初始化次数
 
    if user_id not in user_usage:
        user_usage[user_id] = 0

    # 超过免费次数 → 判断是否在群里
    if user_usage[user_id] >= MAX_FREE_TIMES:
        try:
            member = await context.bot.get_chat_member(chat_id="@EchoAICut", user_id=user_id)
            if member.status in ["member", "administrator", "creator"]:
                await update.message.reply_text(
                    "🚫 今日免费次数已用完\n\n✅ 你已在 Echo AI 群组，可通过购买会员获得更多抠图次数"
                )
            else:
                await update.message.reply_text(
                    "🚫 今日免费次数已用完\n\n👉 加入Echo AI即可获得额外 1 次机会：\n" + CHANNEL_LINK
                )
        except Exception:
            await update.message.reply_text(
                "🚫 今日免费次数已用完\n\n👉 加入Echo AI即可获得额外 1 次机会：\n" + CHANNEL_LINK
            )
        return

    # ✅ 次数有效 → 增加一次使用
    user_usage[user_id] += 1

    # 提示用户
    await update.message.reply_text("⏳ 正在抠图，请稍等 3~5 秒...")

    # 1️⃣ 获取用户发送的最高分辨率图片
    photo = update.message.photo[-1]
    file = await photo.get_file()

    input_path = "input.jpg"
    output_path = "output.png"

    # 2️⃣ 下载图片到本地
    await file.download_to_drive(input_path)

    try:
    # 3️⃣ 调用 remove.bg API
    response = requests.post(
        "https://api.remove.bg/v1.0/removebg",
        files={"image_file": open(input_path, "rb")},
        data={"size": "auto"},
        headers={"X-Api-Key": REMOVE_BG_API_KEY},
        timeout=60
    )

    # 4️⃣ 判断是否成功
  if response.status_code == 200:
    # 保存抠图结果
    with open(output_path, "wb") as out:
        out.write(response.content)

    # 发送结果给用户
    keyboard = [["📊 今日剩余次数"], ["💎 升级会员"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_photo(
        photo=open(output_path, "rb"),
        caption="✅ 抠图完成（PNG 透明背景）",
        reply_markup=reply_markup
    )
else:
    await update.message.reply_text("❌ 抠图失败，可能是额度用完了")

except Exception as e:
    await update.message.reply_text("⚠️ 出现错误，请稍后再试")


# 6️⃣ 清理临时文件
if os.path.exists(input_path):
    os.remove(input_path)
if os.path.exists(output_path):
    os.remove(output_path)


# ====== 五、创建 Bot 应用 ======
#==app = ApplicationBuilder().token(BOT_TOKEN).build()
from telegram.ext import Application  # 确保导入 Application（你已经导入了 telegram.ext，但保险起见加这一行）
app = Application.builder().token(BOT_TOKEN).build()
# ====== 六、注册处理器 ======
app.add_handler(CommandHandler("start", start))# 注册开始按钮
app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, reply))
#=== 注册这个 handler
app.add_handler(ChatMemberHandler(welcome_new_member, ChatMemberHandler.CHAT_MEMBER))
# ====== 七、启动 Bot ======
print("🤖 Bot 正在运行...")
app.run_polling()
