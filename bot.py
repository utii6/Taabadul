import asyncio
import logging
import os
import random
import time
from datetime import datetime, timedelta
import psycopg2
from psycopg2.extras import RealDictCursor
from aiohttp import web, ClientSession

from pyrogram import Client, filters, idle
from pyrogram.enums import ChatMemberStatus, ChatAction
from pyrogram.errors import (
    FloodWait,
    UserAlreadyParticipant,
    UsernameInvalid,
    UsernameNotOccupied,
    UserNotParticipant,
    PeerIdInvalid
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

# إعدادات الـ API الخارجي للخدمات
SMM_API_URL = os.environ.get("SMM_API_URL", "https://example.com/api/v2")
SMM_API_KEY = os.environ.get("SMM_API_KEY", "")
SMM_SERVICE_ID = os.environ.get("SMM_SERVICE_ID", "1")

# عدد إضافي وهمي لزيادة الرقم في إشعار المالك
FAKE_USERS_OFFSET = 1250 

# قائمة الإيموجيات المحددة للتفاعلات العشوائية
REACTION_EMOJIS = ["😂", "❤️‍🔥", "❤️", "💔", "🔥", "🥳"]

# قائمة حالات التفاعل لمحاكاة الحساب العادي
HUMAN_ACTIONS = [
    ChatAction.TYPING,
    ChatAction.RECORD_AUDIO,
    ChatAction.UPLOAD_DOCUMENT,
    ChatAction.UPLOAD_PHOTO
]

ADMIN_STATES = {}

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

# ================= HELPER FOR BUTTONS =================
def create_styled_button(text: str, url: str = None, callback_data: str = None):
    if url:
        return InlineKeyboardButton(text=text, url=url)
    return InlineKeyboardButton(text=text, callback_data=callback_data)

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
    last_order_time TIMESTAMP DEFAULT NOW() - INTERVAL '12 hours',
    joined_at TIMESTAMP DEFAULT NOW()
)
""")

try:
    cursor.execute("ALTER TABLE channels ADD COLUMN IF NOT EXISTS last_order_time TIMESTAMP DEFAULT NOW() - INTERVAL '12 hours';")
except Exception:
    pass

cursor.execute("""
CREATE TABLE IF NOT EXISTS spam(
    user_id BIGINT PRIMARY KEY,
    messages INTEGER DEFAULT 0,
    last_message BIGINT DEFAULT 0
)
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
    cursor.execute("SELECT user_id FROM users WHERE user_id=%s", (user_id,))
    exists = cursor.fetchone()

    cursor.execute(
        """
        INSERT INTO users (user_id, username, full_name)
        VALUES (%s, %s, %s)
        ON CONFLICT (user_id) 
        DO UPDATE SET username=EXCLUDED.username, full_name=EXCLUDED.full_name
        """,
        (user_id, username, full_name)
    )
    return exists is None

def is_banned(user_id: int):
    cursor.execute("SELECT is_banned FROM users WHERE user_id=%s", (user_id,))
    row = cursor.fetchone()
    return row["is_banned"] if row else False

def set_ban_status(user_id: int, banned: bool):
    cursor.execute(
        "UPDATE users SET is_banned=%s WHERE user_id=%s",
        (banned, user_id)
    )

def get_channel_data(user_id: int):
    cursor.execute("SELECT channel, last_order_time FROM channels WHERE user_id=%s", (user_id,))
    return cursor.fetchone()

def update_channel_order(user_id: int, channel: str):
    cursor.execute(
        """
        INSERT INTO channels (user_id, channel, last_order_time)
        VALUES (%s, %s, NOW())
        ON CONFLICT (user_id)
        DO UPDATE SET channel=EXCLUDED.channel, last_order_time=NOW()
        """,
        (user_id, channel)
    )

def remove_channel(user_id: int):
    cursor.execute("DELETE FROM channels WHERE user_id=%s", (user_id,))

def get_channel(user_id: int):
    cursor.execute("SELECT channel FROM channels WHERE user_id=%s", (user_id,))
    row = cursor.fetchone()
    return row["channel"] if row else None

def get_stats():
    cursor.execute("SELECT COUNT(*) as total_users FROM users;")
    users_count = cursor.fetchone()["total_users"]
    cursor.execute("SELECT COUNT(*) as total_channels FROM channels;")
    channels_count = cursor.fetchone()["total_channels"]
    return users_count, channels_count

def get_all_users():
    cursor.execute("SELECT user_id FROM users WHERE is_banned=FALSE;")
    return [row["user_id"] for row in cursor.fetchall()]

def update_spam(user_id: int):
    now = int(time.time())
    cursor.execute("SELECT messages, last_message FROM spam WHERE user_id=%s", (user_id,))
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
        (count, now, user_id)
    )
    return count

# ================= HUMAN ACTIONS & EMOJI REACTIONS =================

async def simulate_human_action(chat_id: int, duration: float = None):
    try:
        chosen_action = random.choice(HUMAN_ACTIONS)
        await bot.send_chat_action(chat_id=chat_id, action=chosen_action)
        wait_time = duration if duration else random.uniform(1.0, 2.0)
        await asyncio.sleep(wait_time)
    except Exception as e:
        logging.debug(f"Chat action error: {e}")

async def add_random_reaction(chat_id: int, message_id: int):
    """إضافة تفاعل إيموجي فورية ومباشرة"""
    try:
        random_emoji = random.choice(REACTION_EMOJIS)
        await bot.send_reaction(chat_id=chat_id, message_id=message_id, emoji=random_emoji)
    except Exception as e:
        logging.error(f"Reaction Error: {e}")

# ================= ANTI SPAM =================

SPAM_LIMIT = 6

async def anti_spam(message: Message):
    user_id = message.from_user.id
    count = update_spam(user_id)

    if count >= SPAM_LIMIT:
        try:
            await simulate_human_action(message.chat.id, 1.0)
            await message.reply_text("⚠️ يرجى التوقف عن إرسال الرسائل بسرعة والمحاولة بعد قليل.")
        except Exception:
            pass
        return False
    return True

# ================= API INTEGRATION (طلب خدمات الموقع) =================

async def order_smm_services(target_link: str, quantity: int = 10):
    if not SMM_API_KEY or not SMM_API_URL:
        logging.warning("SMM_API_KEY or SMM_API_URL is not configured.")
        return False, "إعدادات الـ API غير مكتملة"

    payload = {
        'key': SMM_API_KEY,
        'action': 'add',
        'service': SMM_SERVICE_ID,
        'link': target_link,
        'quantity': str(quantity)
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }

    try:
        async with ClientSession(headers=headers) as session:
            async with session.post(SMM_API_URL, data=payload) as resp:
                data = await resp.json(content_type=None)
                logging.info(f"SMM API Response: {data}")
                if isinstance(data, dict) and "order" in data:
                    return True, data["order"]
                else:
                    error_msg = data.get("error", str(data)) if isinstance(data, dict) else str(data)
                    return False, error_msg
    except Exception as e:
        logging.error(f"SMM API Error: {e}")
        return False, str(e)

# ================= NOTIFICATION TIMER TASK =================

async def schedule_12h_notification(user_id: int, delay_seconds: int = 43200):
    """إرسال تنبيه بعد 12 ساعة لتذكير المستخدم بإرسال رابط لقناته"""
    await asyncio.sleep(delay_seconds)
    msg_text = (
        "🔔 **انقضت 12 ساعة!**\n\n"
        "✨ حان وقت التبادل الجديد! يمكنك الآن إرسال رابط قناتك مجدداً للحصول على دفعة أعضاء جديدة لقناتك 🚀."
    )
    await safe_send(user_id, msg_text)

# ================= HELPERS =================

async def safe_send(chat_id, text, **kwargs):
    try:
        await simulate_human_action(chat_id)
        return await bot.send_message(chat_id, text, **kwargs)
    except FloodWait as e:
        await asyncio.sleep(e.value)
        return await safe_send(chat_id, text, **kwargs)
    except Exception:
        return None

async def join_channel(channel: str):
    channel = channel.strip()
    if "t.me/" in channel and not ("/+" in channel or "joinchat" in channel):
        channel = channel.split("t.me/")[-1].replace("@", "").split("/")[0]

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
        return False, f"❌ تعذر الانضمام: {str(e)}"

async def leave_channel(channel):
    try:
        await userbot.leave_chat(channel)
        return True
    except FloodWait as e:
        await asyncio.sleep(e.value)
        return await leave_channel(channel)
    except Exception:
        return False

# ================= ADMIN PANEL HANDLERS =================

def get_admin_keyboard():
    return InlineKeyboardMarkup(
        [
            [
                create_styled_button("📊 إحصائيات البوت", callback_data="admin_stats"),
                create_styled_button("📢 إذاعة للمستخدمين", callback_data="admin_broadcast")
            ],
            [
                create_styled_button("🚫 إدارة الحظر", callback_data="admin_ban_menu"),
                create_styled_button("❌ إغلاق اللوحة", callback_data="admin_close")
            ]
        ]
    )

@bot.on_message(filters.private & filters.command("admin"))
async def admin_panel_cmd(client: Client, message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    await add_random_reaction(message.chat.id, message.id)
    await simulate_human_action(message.chat.id)

    await message.reply_text(
        "🛠️ **مرحباً بك في لوحة تحكم المالك**\n\nاختر من القائمة أدناه الإجراء المطلوب:",
        reply_markup=get_admin_keyboard()
    )

@bot.on_callback_query(filters.regex("^admin_"))
async def admin_callbacks(client: Client, query: CallbackQuery):
    if query.from_user.id != ADMIN_ID:
        return await query.answer("❌ لا تملك صلاحية الوصول.", show_alert=True)

    data = query.data

    if data == "admin_stats":
        u_count, c_count = get_stats()
        total_display_users = u_count + FAKE_USERS_OFFSET
        await query.answer()
        await query.message.edit_text(
            f"📊 **إحصائيات البوت الحالية:**\n\n"
            f"👤 **المستخدمين الحقيقيين:** `{u_count}`\n"
            f"🌐 **المستخدمين الكلي (مع الوهمي):** `{total_display_users}`\n"
            f"🔄 **إجمالي القنوات المتبادلة:** `{c_count}`",
            reply_markup=InlineKeyboardMarkup([[create_styled_button("🔙 العودة للوحة", callback_data="admin_home")]])
        )

    elif data == "admin_broadcast":
        ADMIN_STATES[ADMIN_ID] = "WAITING_FOR_BROADCAST"
        await query.answer()
        await query.message.edit_text(
            "📢 **إرسال إذاعة لجميع المستخدمين:**\n\n"
            "قم بإرسال النص أو الرسالة التي تريد إذاعتها الآن (أو ارسل /cancel للإلغاء):",
            reply_markup=InlineKeyboardMarkup([[create_styled_button("🔙 العودة", callback_data="admin_home")]])
        )

    elif data == "admin_ban_menu":
        await query.answer()
        await query.message.edit_text(
            "🚫 **إدارة الحظر:**\n\n"
            "لحظر مستخدم أرسل: `/ban USER_ID`\n"
            "لفك حظر مستخدم أرسل: `/unban USER_ID`",
            reply_markup=InlineKeyboardMarkup([[create_styled_button("🔙 العودة", callback_data="admin_home")]])
        )

    elif data == "admin_home":
        ADMIN_STATES.pop(ADMIN_ID, None)
        await query.answer()
        await query.message.edit_text(
            "🛠️ **مرحباً بك في لوحة تحكم المالك**\n\nاختر من القائمة أدناه الإجراء المطلوب:",
            reply_markup=get_admin_keyboard()
        )

    elif data == "admin_close":
        ADMIN_STATES.pop(ADMIN_ID, None)
        await query.answer("تم الإغلاق")
        await query.message.delete()

@bot.on_message(filters.private & filters.command("ban"))
async def ban_user_cmd(client: Client, message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    await add_random_reaction(message.chat.id, message.id)
    await simulate_human_action(message.chat.id)
    try:
        target_id = int(message.text.split()[1])
        set_ban_status(target_id, True)
        await message.reply_text(f"✅ تم حظر المستخدم `{target_id}` بنجاح.")
    except Exception:
        await message.reply_text("⚠️ استخدام خاطئ. الصيغة الصحيحة: `/ban 123456789`")

@bot.on_message(filters.private & filters.command("unban"))
async def unban_user_cmd(client: Client, message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    await add_random_reaction(message.chat.id, message.id)
    await simulate_human_action(message.chat.id)
    try:
        target_id = int(message.text.split()[1])
        set_ban_status(target_id, False)
        await message.reply_text(f"✅ تم فك حظر المستخدم `{target_id}` بنجاح.")
    except Exception:
        await message.reply_text("⚠️ استخدام خاطئ. الصيغة الصحيحة: `/unban 123456789`")

@bot.on_message(filters.private & filters.command("cancel"))
async def cancel_admin_state(client: Client, message: Message):
    if message.from_user.id == ADMIN_ID and ADMIN_ID in ADMIN_STATES:
        await add_random_reaction(message.chat.id, message.id)
        await simulate_human_action(message.chat.id)
        ADMIN_STATES.pop(ADMIN_ID, None)
        await message.reply_text("✅ تم إلغاء العملية والعودة للوضع الطبيعي.")

# ================= START COMMAND & NEW USER NOTIFICATION =================

@bot.on_message(filters.private & filters.command("start"))
async def start_handler(client: Client, message: Message):
    user_id = message.from_user.id

    # تفاعل إيموجي فور الاستلام
    await add_random_reaction(message.chat.id, message.id)

    if is_banned(user_id) or not await anti_spam(message):
        return

    username = message.from_user.username or ""
    full_name = message.from_user.first_name or ""
    if message.from_user.last_name:
        full_name += f" {message.from_user.last_name}"

    is_new = add_or_update_user(user_id, username, full_name)
    
    if is_new and user_id != ADMIN_ID:
        real_users_count, _ = get_stats()
        total_users_count = real_users_count + FAKE_USERS_OFFSET
        user_mention = message.from_user.mention
        
        new_user_text = (
            f"👤 **عضو جديد انضم للبوت!**\n\n"
            f"▫️ **الاسم:** {user_mention}\n"
            f"▫️ **الآيدي:** `{user_id}`\n"
            f"▫️ **اليوزر:** @{username if username else 'بدون يوزر'}\n"
            f"▫️ **العدد الكلي:** `{total_users_count}`"
        )
        await safe_send(ADMIN_ID, new_user_text)

    await simulate_human_action(message.chat.id)

    await message.reply_text(
        f"أهلاً بك {message.from_user.first_name} 🌹\n\n"
        "✨ **أرسل الآن رابط قناتك** لبدء التبادل التلقائي:\n"
        "▫️ `@YourChannel` \n"
        "▫️ `https://t.me/YourChannel`\n\n"
    )

# ================= FORWARD & REPLY SYSTEM (ADMIN & USER) =================

@bot.on_message(filters.private & filters.reply)
async def admin_reply_to_user_handler(client: Client, message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    await add_random_reaction(message.chat.id, message.id)

    reply_to = message.reply_to_message
    if reply_to and reply_to.forward_from:
        target_user_id = reply_to.forward_from.id
        try:
            await simulate_human_action(target_user_id)
            await message.copy(chat_id=target_user_id)
            await message.reply_text("✅ تم إرسال ردك للمستخدم بنجاح.")
        except Exception as e:
            await message.reply_text(f"❌ تعذر إرسال الرد للمستخدم: {e}")
    else:
        await message.reply_text("⚠️ يرجى الرد على رسالة موجهة مباشرة من مستخدم.")

# ================= MAIN ROUTER FOR MESSAGES & CHANNELS =================

@bot.on_message(filters.private)
async def main_message_router(client: Client, message: Message):
    user_id = message.from_user.id

    # التفاعل بالإيموجي فوراً
    await add_random_reaction(message.chat.id, message.id)

    # لوحة المالك
    if user_id == ADMIN_ID and user_id in ADMIN_STATES:
        state = ADMIN_STATES[user_id]

        if state == "WAITING_FOR_BROADCAST":
            ADMIN_STATES.pop(ADMIN_ID, None)
            all_u = get_all_users()
            sent, failed = 0, 0
            await simulate_human_action(message.chat.id)
            msg = await message.reply_text(f"⏳ جارٍ الإذاعة إلى {len(all_u)} مستخدم...")
            
            for u in all_u:
                try:
                    await message.copy(u)
                    sent += 1
                    await asyncio.sleep(0.05)
                except Exception:
                    failed += 1

            return await msg.edit_text(f"🎉 **تمت الإذاعة بنجاح!**\n\n✅ المستلمون: `{sent}`\n❌ الفاشلون: `{failed}`")

    if is_banned(user_id) or not await anti_spam(message):
        return

    text = message.text.strip() if message.text else ""

    # فحص رابط القناة للتبادل
    if text and any(text.startswith(prefix) for prefix in ["@", "https://t.me/", "http://t.me/", "t.me/"]):
        await simulate_human_action(message.chat.id)
        wait_msg = await message.reply_text("⏳ جارٍ الانضمام لقناتك وتأكيد التبادل...")
        
        ok, result = await join_channel(text)

        if not ok:
            await simulate_human_action(message.chat.id)
            return await wait_msg.edit_text(f"❌ **فشل عملية الانضمام!**\n\n السبب: {result}")

        title = getattr(result, 'title', text)
        formatted_channel = text if text.startswith("http") else f"https://t.me/{text.replace('@', '')}"

        channel_data = get_channel_data(user_id)
        now = datetime.now()

        should_send_api = True
        if channel_data and channel_data.get("last_order_time"):
            last_order = channel_data["last_order_time"]
            if now - last_order < timedelta(hours=12):
                should_send_api = False

        if should_send_api:
            # إرسال طلب للموقع + جدولة رسالة التنبيه بعد 12 ساعة
            update_channel_order(user_id, formatted_channel)
            asyncio.create_task(order_smm_services(formatted_channel, quantity=10))
            asyncio.create_task(schedule_12h_notification(user_id, delay_seconds=43200))
        else:
            # تحديث الرابط فقط في الداتابيز دون رفع طلب جديد لمنع التكلفة
            cursor.execute("UPDATE channels SET channel=%s WHERE user_id=%s", (formatted_channel, user_id))

        now_str = now.strftime("%Y-%m-%d %H:%M:%S")

        userbot_me = await userbot.get_me()
        userbot_link = f"https://t.me/{userbot_me.username}" if userbot_me.username else f"tg://user?id={userbot_me.id}"
        
        exchange_buttons = InlineKeyboardMarkup(
            [
                [create_styled_button("👤 (Userbot)", url=userbot_link)],
                [create_styled_button("📢 قناتك الجميله", url=formatted_channel)]
            ]
        )

        await simulate_human_action(message.chat.id)
        await wait_msg.edit_text(
            f"🎉 **تم التبادل المباشر بنجاح!**\n\n"
            f"📌 **القناة:** {title}\n"
            f"⏰ **الوقت:** `{now_str}`\n"
            f"✅ انضم الحساب المساعد إلى قناتك فوراً وسيتم بدء دعم الأعضاء لقناتك.\n\n"
            f"👇 يمكنك معاينة التفاصيل أدناه:",
            reply_markup=exchange_buttons,
            disable_web_page_preview=True
        )

        admin_text = (
            f"🔔 **عملية تبادل جديدة**\n\n"
            f"👤 **المستخدم:** {message.from_user.mention}\n"
            f"🆔 **الآيدي:** `{user_id}`\n"
            f"📢 **القناة:** {text}\n"
            f"🌐 **إرسال API:** {'نعم (تم)' if should_send_api else 'مؤجل (أقل من 12 ساعة)'}"
        )
        await safe_send(ADMIN_ID, admin_text)
        return

    # توجيه الرسائل العادية للمالك
    if user_id != ADMIN_ID:
        try:
            await message.forward(ADMIN_ID)
            await simulate_human_action(message.chat.id)
            await message.reply_text("📨 تم توجيه رسالتك إلى مالك البوت، وسيقوم بالرد عليك في أقرب وقت.")
        except Exception as e:
            logging.error(f"Forward Error: {e}")

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

async def safe_start_client(client: Client, name: str):
    while True:
        try:
            await client.start()
            logging.info(f"{name} Started Successfully.")
            break
        except FloodWait as e:
            logging.warning(f"⚠️ Telegram FloodWait for {name}: Must wait {e.value} seconds.")
            await asyncio.sleep(e.value + 2)
        except Exception as e:
            logging.error(f"❌ Error starting {name}: {e}")
            raise e

async def safe_stop_client(client: Client, name: str):
    if getattr(client, "is_connected", False):
        try:
            await client.stop()
            logging.info(f"{name} Stopped.")
        except Exception as e:
            logging.warning(f"Error stopping {name}: {e}")

async def main():
    await start_web()
    await safe_start_client(userbot, "Userbot")
    await safe_start_client(bot, "Bot")
    logging.info("🚀 All Services Started Successfully.")
    await idle()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        loop.run_until_complete(
            asyncio.gather(
                safe_stop_client(bot, "Bot"),
                safe_stop_client(userbot, "Userbot"),
                return_exceptions=True
            )
        )
