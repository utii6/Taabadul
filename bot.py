import asyncio
import logging
import os
import time
import psycopg2
from psycopg2.extras import RealDictCursor
from aiohttp import web

from pyrogram import Client, filters, idle
from pyrogram.enums import ChatAction, ChatMemberStatus
from pyrogram.errors import (
    FloodWait,
    UserAlreadyParticipant,
    UsernameInvalid,
    UsernameNotOccupied
)

from pyrogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)

# ================= LOGGING SETUP =================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

# ================= ENVIRONMENT VARIABLES =================
API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
BOT_TOKEN = os.environ["BOT_TOKEN"]
USERBOT_SESSION = os.environ["USERBOT_SESSION"]
DATABASE_URL = os.environ["DATABASE_URL"]
ADMIN_ID = int(os.environ["ADMIN_ID"])

# ================= PYROGRAM CLIENTS =================
bot = Client(
    "Bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    in_memory=True
)

userbot = Client(
    "Userbot",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=USERBOT_SESSION,
    in_memory=True
)

# ================= DATABASE CONNECTION =================
db = psycopg2.connect(
    DATABASE_URL,
    sslmode="require",
    cursor_factory=RealDictCursor
)
db.autocommit = True
cursor = db.cursor()

# ================= DATABASE TABLES INITIALIZATION =================
cursor.execute("""
CREATE TABLE IF NOT EXISTS settings(
    key TEXT PRIMARY KEY,
    value TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS users(
    user_id BIGINT PRIMARY KEY,
    username TEXT,
    full_name TEXT,
    is_banned BOOLEAN DEFAULT FALSE,
    join_date TIMESTAMP DEFAULT NOW()
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS channels(
    id SERIAL PRIMARY KEY,
    user_id BIGINT UNIQUE,
    channel TEXT,
    joined_at TIMESTAMP DEFAULT NOW()
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS spam(
    user_id BIGINT PRIMARY KEY,
    messages INTEGER DEFAULT 0,
    last_message BIGINT DEFAULT 0
)
""")

cursor.execute("""
INSERT INTO settings(key,value)
VALUES('main_channel','https://t.me/YourChannel')
ON CONFLICT(key) DO NOTHING
""")

# ================= DATABASE FUNCTIONS =================

def get_setting(key: str):
    cursor.execute("SELECT value FROM settings WHERE key=%s", (key,))
    row = cursor.fetchone()
    return row["value"] if row else None


def set_setting(key: str, value: str):
    cursor.execute(
        """
        INSERT INTO settings(key,value)
        VALUES(%s,%s)
        ON CONFLICT(key)
        DO UPDATE SET value=EXCLUDED.value
        """,
        (key, value)
    )


def add_or_update_user(user_id: int, username: str, full_name: str):
    cursor.execute(
        """
        INSERT INTO users (user_id, username, full_name)
        VALUES (%s, %s, %s)
        ON CONFLICT (user_id) 
        DO UPDATE SET username=EXCLUDED.username, full_name=EXCLUDED.full_name
        """,
        (user_id, username, full_name)
    )


def is_banned(user_id: int):
    cursor.execute("SELECT is_banned FROM users WHERE user_id=%s", (user_id,))
    row = cursor.fetchone()
    return row["is_banned"] if row else False


def save_channel(user_id: int, channel: str):
    cursor.execute(
        """
        INSERT INTO channels (user_id, channel)
        VALUES (%s, %s)
        ON CONFLICT (user_id)
        DO UPDATE SET channel=EXCLUDED.channel, joined_at=NOW()
        """,
        (user_id, channel)
    )


def remove_channel(user_id: int):
    cursor.execute("DELETE FROM channels WHERE user_id=%s", (user_id,))


def get_channel(user_id: int):
    cursor.execute("SELECT channel FROM channels WHERE user_id=%s", (user_id,))
    row = cursor.fetchone()
    return row["channel"] if row else None


def update_spam(user_id: int):
    now = int(time.time())
    cursor.execute("SELECT * FROM spam WHERE user_id=%s", (user_id,))
    row = cursor.fetchone()

    if row is None:
        cursor.execute(
            "INSERT INTO spam (user_id, messages, last_message) VALUES (%s, 1, %s)",
            (user_id, now)
        )
        return 1

    if now - row["last_message"] > 10:
        cursor.execute(
            "UPDATE spam SET messages=1, last_message=%s WHERE user_id=%s",
            (now, user_id)
        )
        return 1

    count = row["messages"] + 1
    cursor.execute(
        "UPDATE spam SET messages=%s, last_message=%s WHERE user_id=%s",
        (count, now)
    )
    return count

# ================= ANTI SPAM =================

SPAM_LIMIT = 6

async def anti_spam(message: Message):
    user_id = message.from_user.id
    count = update_spam(user_id)

    if count >= SPAM_LIMIT:
        try:
            await message.reply_text("⚠️ يرجى التوقف عن إرسال الرسائل بسرعة والمحاولة بعد قليل.")
        except Exception:
            pass
        return False
    return True

# ================= HELPERS =================

async def safe_send(chat_id, text, **kwargs):
    try:
        return await bot.send_message(chat_id, text, **kwargs)
    except FloodWait as e:
        await asyncio.sleep(e.value)
        return await safe_send(chat_id, text, **kwargs)
    except Exception:
        return None


async def join_channel(channel):
    try:
        chat = await userbot.join_chat(channel)
        return True, chat
    except UserAlreadyParticipant:
        chat = await userbot.get_chat(channel)
        return True, chat
    except (UsernameInvalid, UsernameNotOccupied):
        return False, "💔 رابط القناة غير صالح أو غير موجود."
    except FloodWait as e:
        await asyncio.sleep(e.value)
        return await join_channel(channel)
    except Exception as e:
        return False, f"تعذر الانضمام: {str(e)}"


async def leave_channel(channel):
    try:
        await userbot.leave_chat(channel)
        return True
    except FloodWait as e:
        await asyncio.sleep(e.value)
        return await leave_channel(channel)
    except Exception:
        return False


async def is_subscribed(user_id):
    channel = get_setting("main_channel")
    
    if not channel or "YourChannel" in channel:
        return True

    username = channel.replace("https://t.me/", "").replace("http://t.me/", "").replace("@", "").strip()

    if user_id == ADMIN_ID:
        return True

    try:
        member = await bot.get_chat_member(f"@{username}", user_id)
        if member.status in (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
            return True
    except Exception as e:
        logging.error(f"Subscription Check Error for @{username}: {e}")
        return True

    return False

# ================= START COMMAND =================

@bot.on_message(filters.private & filters.command("start"))
async def start_handler(client: Client, message: Message):
    user_id = message.from_user.id

    if is_banned(user_id):
        return await message.reply_text("🚫 تم حظرك من استخدام البوت.")

    if not await anti_spam(message):
        return

    username = message.from_user.username or ""
    full_name = message.from_user.first_name or ""
    if message.from_user.last_name:
        full_name += f" {message.from_user.last_name}"

    add_or_update_user(user_id, username, full_name)

    if not await is_subscribed(user_id):
        channel = get_setting("main_channel")
        kb = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("📢 قناة التبادل الرئيسية", url=channel)],
                [InlineKeyboardButton("✅ تحقق من الاشتراك", callback_data="check_join")]
            ]
        )
        return await message.reply_text(
            "👋 أهلاً بك عزيزي!\n\n⚠️ للاستفادة من البوت والتبادل، يرجى أولاً الاشتراك في القناة الرئيسية:",
            reply_markup=kb,
            disable_web_page_preview=True
        )

    await message.reply_text(
        f"أهلاً بك {message.from_user.first_name} 🌹\n\n"
        "✨ **أرسل الآن رابط قناتك** أو المعرف الخاص بها بالشكل التالي:\n"
        "▫️ `@YourChannel` \n"
        "▫️ `https://t.me/YourChannel`\n\n"
        "ليقوم حساب البوت بالانضمام إليها مباشرة!"
    )


@bot.on_callback_query(filters.regex("^check_join$"))
async def check_join_callback(client: Client, query: CallbackQuery):
    if await is_subscribed(query.from_user.id):
        await query.answer("تم التحقق بنجاح ✅", show_alert=True)
        await query.message.edit_text(
            "✅ **تم التحقق من الاشتراك بنجاح!**\n\n"
            "أرسل الآن رابط قناتك أو معرفها (`@channel`) لبدء التبادل."
        )
    else:
        await query.answer("❌ لم تشترك بعد في القناة الرئيسية!", show_alert=True)

# ================= USER CHANNEL HANDLER =================

@bot.on_message(filters.private & filters.text & ~filters.command(["start", "admin"]))
async def channel_exchange_handler(client: Client, message: Message):
    user_id = message.from_user.id

    if is_banned(user_id) or not await anti_spam(message):
        return

    if not await is_subscribed(user_id):
        channel = get_setting("main_channel")
        keyboard = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("📢 قناة التبادل الرئيسية", url=channel)],
                [InlineKeyboardButton("✅ تحقق من الاشتراك", callback_data="check_join")]
            ]
        )
        return await message.reply_text("⚠️ يرجى الاشتراك في القناة الرئيسية أولاً.", reply_markup=keyboard)

    text = message.text.strip()

    # فحص صيغة الرابط أو المعرف
    if any(text.startswith(prefix) for prefix in ["@", "https://t.me/", "http://t.me/", "t.me/"]):
        wait_msg = await message.reply_text("⏳ جارٍ الانضمام إلى قناتك وتأكيد التبادل...")
        
        ok, result = await join_channel(text)

        if not ok:
            return await wait_msg.edit_text(f"❌ **فشل عملية الانضمام!**\n\n السبب: {result}")

        # حفظ القناة
        save_channel(user_id, text)
        title = getattr(result, 'title', text)

        # جلب معلومات الـ Userbot للزر الشفاف
        userbot_me = await userbot.get_me()
        userbot_link = f"https://t.me/{userbot_me.username}" if userbot_me.username else f"tg://user?id={userbot_me.id}"

        # تجهيز الأزرار الشفافة التفاعلية (Inline Keyboard)
        formatted_channel = text if text.startswith("http") else f"https://t.me/{text.replace('@', '')}"
        exchange_buttons = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("👤 حساب الاشتراك (Userbot)", url=userbot_link)],
                [InlineKeyboardButton("📢 قناتك المقبولة في التبادل", url=formatted_channel)]
            ]
        )

        # رسالة النجاح للمستخدم
        await wait_msg.edit_text(
            f"🎉 **تم التبادل بنجاح!**\n\n"
            f"📌 **القناة:** {title}\n"
            f"✅ انضم الحساب المخصص إلى قناتك بنجاح.\n\n"
            f"👇 يمكنك استخدام الأزرار أدناه لمعاينة التفاصيل:",
            reply_markup=exchange_buttons,
            disable_web_page_preview=True
        )

        # إشعار مالك البوت (ADMIN)
        admin_text = (
            f"🔔 **عملية تبادل جديدة**\n\n"
            f"👤 **المستخدم:** {message.from_user.mention}\n"
            f"🆔 **الآيدي:** `{user_id}`\n"
            f"📢 **القناة:** {text}\n"
            f"⚡️ **النتيجة:** تم الانضمام بنجاح بواسطة Userbot."
        )
        await safe_send(ADMIN_ID, admin_text)
        return

    await message.reply_text("⚠️ الرجاء إرسال رابط قناة صحيح يبدأ بـ `@` أو `https://t.me/`.")

# ================= MEMBER UPDATE HANDLER (AUTOMATIC UNJOIN) =================

@bot.on_chat_member_updated()
async def member_update_handler(client, update):
    try:
        main_channel = get_setting("main_channel")
        if not main_channel or "YourChannel" in main_channel:
            return

        username = main_channel.replace("https://t.me/", "").replace("http://t.me/", "").replace("@", "").strip()

        if not update.chat or (update.chat.username or "").lower() != username.lower():
            return
        if not update.old_chat_member or not update.new_chat_member:
            return

        old_status = update.old_chat_member.status
        new_status = update.new_chat_member.status

        # اكتشاف مغادرة المستخدم للقناة الرئيسية
        if old_status in (ChatMemberStatus.MEMBER, ChatMemberStatus.RESTRICTED) and new_status == ChatMemberStatus.LEFT:
            user = update.new_chat_member.user
            if not user:
                return

            user_id = user.id
            channel = get_channel(user_id)
            if not channel:
                return

            # مغادرة الـ Userbot من قناة المستخدم
            success = await leave_channel(channel)
            if success:
                remove_channel(user_id)
                
                # 1. إرسال رسالة المغادرة للمستخدم
                await safe_send(
                    user_id, 
                    f"⚠️ **تنبيه إلغاء التبادل!**\n\n"
                    f"لقد قمت بالمغادرة من القناة الرئيسية، لذا قام الحساب بالمغادرة تلقائياً من قناتك:\n{channel}"
                )
                
                # 2. إرسال رسالة المغادرة للمالك (ADMIN)
                await safe_send(
                    ADMIN_ID, 
                    f"🚨 **إلغاء تبادل (مغادرة)**\n\n"
                    f"👤 **المستخدم:** {user.mention}\n"
                    f"🆔 **الآيدي:** `{user_id}`\n"
                    f"📢 **تمت المغادرة من قناته:** {channel}"
                )

    except Exception as e:
        logging.exception(e)

# ================= WEB SERVER =================

async def health(request):
    return web.Response(text="Bot is running smoothly.")

async def start_web():
    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_get("/health", health)

    runner = web.AppRunner(app)
    await runner.setup()

    port = int(os.getenv("PORT", "10000"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info(f"Web Server Started : {port}")

# ================= MAIN RUNNER =================

async def main():
    await start_web()
    
    await userbot.start()
    logging.info("Userbot Started.")
    
    await bot.start()
    logging.info("Bot Started.")
    
    logging.info("Project Started Successfully.")
    await idle()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        loop.run_until_complete(asyncio.gather(bot.stop(), userbot.stop(), return_exceptions=True))
