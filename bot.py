import asyncio
import logging
import os
import random
import time
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor
from aiohttp import web, ClientSession

from pyrogram import Client, filters, idle
from pyrogram.enums import ChatMemberStatus
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

# قائمة الإيموجيات للتفاعلات المدعومة
REACTION_EMOJIS = ["👍", "❤️", "🔥", "🎉", "👏", "😍", "⚡", "🌟"]

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
    joined_at TIMESTAMP DEFAULT NOW()
)
""")

try:
    cursor.execute("ALTER TABLE channels ADD CONSTRAINT unique_user_id UNIQUE (user_id);")
except Exception:
    pass

cursor.execute("""
CREATE TABLE IF NOT EXISTS spam(
    user_id BIGINT PRIMARY KEY,
    messages INTEGER DEFAULT 0,
    last_message BIGINT DEFAULT 0
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS pending_orders (
    id SERIAL PRIMARY KEY,
    user_id BIGINT,
    channel_link TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    status TEXT DEFAULT 'pending'
)
""")

cursor.execute("""
INSERT INTO settings(key,value)
VALUES('main_channel','https://t.me/KKEK2')
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
    """تضيف المستخدم وتتحقق مما إذا كان عضواً جديداً"""
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


def save_channel(user_id: int, channel: str):
    cursor.execute("DELETE FROM channels WHERE user_id=%s", (user_id,))
    cursor.execute(
        "INSERT INTO channels (user_id, channel) VALUES (%s, %s)",
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

# ================= API INTEGRATION (طلب خدمات الموقع) =================

async def order_smm_services(target_link: str, quantity: int = 1):
    """إرسال طلب إلى الـ API الخارجي لطلب الأعضاء"""
    if not SMM_API_KEY or not SMM_API_URL:
        logging.warning("SMM_API_KEY or SMM_API_URL is not configured.")
        return False, "إعدادات الـ API غير مكتملة"

    payload = {
        'key': SMM_API_KEY,
        'action': 'add',
        'service': SMM_SERVICE_ID,
        'link': target_link,
        'quantity': quantity
    }

    try:
        async with ClientSession() as session:
            async with session.post(SMM_API_URL, data=payload) as resp:
                data = await resp.json()
                if "order" in data:
                    return True, data["order"]
                else:
                    return False, str(data.get("error", "فشل طلب الخدمة"))
    except Exception as e:
        logging.error(f"SMM API Error: {e}")
        return False, str(e)

# ================= BACKGROUND TASK (12 HOURS DELAY) =================

async def process_delayed_order(user_id: int, channel_link: str, delay_hours: int = 12):
    """تنفيذ عملية الطلب من الموقع بعد انقضاء المهلة الزمانية المحدد (12 ساعة)"""
    delay_seconds = delay_hours * 3600
    await asyncio.sleep(delay_seconds)
    
    api_success, api_result = await order_smm_services(channel_link, quantity=5)
    
    if api_success:
        await safe_send(
            user_id,
            f"🎉 **تم اكتمال طلب التبادل بالكامل!**\n\n"
            f"📢 **القناة:** {channel_link}\n"
            f"✅ تم إرسال كافة الحسابات المخصصة لقناتك بنجاح (رقم الطلب: `{api_result}`)."
        )
        await safe_send(
            ADMIN_ID,
            f"✅ **اكتمل طلب تبادل مؤجل (12 ساعة)**\n\n"
            f"👤 **المستخدم:** `{user_id}`\n"
            f"📢 **القناة:** {channel_link}\n"
            f"🆔 **رقم الطلب:** `{api_result}`"
        )
    else:
        await safe_send(
            ADMIN_ID,
            f"❌ **فشل طلب التبادل المؤجل**\n\n"
            f"👤 **المستخدم:** `{user_id}`\n"
            f"📢 **القناة:** {channel_link}\n"
            f"⚠️ **السبب:** {api_result}"
        )

# ================= HELPERS & FIXED REACTIONS =================

async def add_random_reaction(chat_id: int, message_id: int):
    """إصلاح التفاعلات العشوائية"""
    try:
        random_emoji = random.choice(REACTION_EMOJIS)
        await bot.send_reaction(chat_id=chat_id, message_id=message_id, emoji=random_emoji)
    except Exception as e:
        logging.debug(f"Reaction error: {e}")


async def safe_send(chat_id, text, **kwargs):
    try:
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
        return False, f"❌تعذر الانضمام: {str(e)}"


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

    if user_id == ADMIN_ID:
        return True

    username = channel.replace("https://t.me/", "").replace("http://t.me/", "").replace("@", "").strip()

    try:
        member = await userbot.get_chat_member(f"@{username}", user_id)
        if member.status in (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
            return True
    except (UserNotParticipant, PeerIdInvalid):
        return False
    except Exception as e:
        logging.error(f"Subscription Check Error for @{username}: {e}")
        return True

    return False

# ================= ADMIN PANEL HANDLERS =================

def get_admin_keyboard():
    return InlineKeyboardMarkup(
        [
            [
                create_styled_button("📊 إحصائيات البوت", callback_data="admin_stats"),
                create_styled_button("⚙️ القناة الرئيسية", callback_data="admin_set_channel")
            ],
            [
                create_styled_button("📢 إذاعة للمستخدمين", callback_data="admin_broadcast"),
                create_styled_button("🚫 إدارة الحظر", callback_data="admin_ban_menu")
            ],
            [
                create_styled_button("❌ إغلاق اللوحة", callback_data="admin_close")
            ]
        ]
    )


@bot.on_message(filters.private & filters.command("admin"))
async def admin_panel_cmd(client: Client, message: Message):
    if message.from_user.id != ADMIN_ID:
        return

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
        await query.answer()
        await query.message.edit_text(
            f"📊 **إحصائيات البوت الحالية:**\n\n"
            f"👤 **إجمالي المستخدمين:** `{u_count}`\n"
            f"🔄 **إجمالي التبادلات النشطة:** `{c_count}`",
            reply_markup=InlineKeyboardMarkup([[create_styled_button("🔙 العودة للوحة", callback_data="admin_home")]])
        )

    elif data == "admin_set_channel":
        ADMIN_STATES[ADMIN_ID] = "WAITING_FOR_MAIN_CHANNEL"
        current_ch = get_setting("main_channel")
        await query.answer()
        await query.message.edit_text(
            f"⚙️ **تغيير القناة الرئيسية:**\n\n"
            f"📌 القناة الحالية: `{current_ch}`\n\n"
            f"💬 أرسل الآن الرابط الجديد للقناة الرئيسية (أو ارسل /cancel للإلغاء):",
            reply_markup=InlineKeyboardMarkup([[create_styled_button("🔙 العودة", callback_data="admin_home")]])
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
    try:
        target_id = int(message.text.split()[1])
        set_ban_status(target_id, False)
        await message.reply_text(f"✅ تم فك حظر المستخدم `{target_id}` بنجاح.")
    except Exception:
        await message.reply_text("⚠️ استخدام خاطئ. الصيغة الصحيحة: `/unban 123456789`")


@bot.on_message(filters.private & filters.command("cancel"))
async def cancel_admin_state(client: Client, message: Message):
    if message.from_user.id == ADMIN_ID and ADMIN_ID in ADMIN_STATES:
        ADMIN_STATES.pop(ADMIN_ID, None)
        await message.reply_text("✅ تم إلغاء العملية والعودة للوضع الطبيعي.")

# ================= START COMMAND & NEW USER NOTIFICATION =================

@bot.on_message(filters.private & filters.command("start"))
async def start_handler(client: Client, message: Message):
    user_id = message.from_user.id

    if is_banned(user_id) or not await anti_spam(message):
        return

    asyncio.create_task(add_random_reaction(message.chat.id, message.id))

    username = message.from_user.username or ""
    full_name = message.from_user.first_name or ""
    if message.from_user.last_name:
        full_name += f" {message.from_user.last_name}"

    # حفظ وتفقد العضو الجديد لإرسال تنبيه للمالك
    is_new = add_or_update_user(user_id, username, full_name)
    if is_new and user_id != ADMIN_ID:
        user_mention = message.from_user.mention
        new_user_text = (
            f"👤 **عضو جديد انضم للبوت!**\n\n"
            f"▫️ **الاسم:** {user_mention}\n"
            f"▫️ **الآيدي:** `{user_id}`\n"
            f"▫️ **اليوزر:** @{username if username else 'بدون يوزر'}"
        )
        await safe_send(ADMIN_ID, new_user_text)

    if not await is_subscribed(user_id):
        channel = get_setting("main_channel")
        kb = InlineKeyboardMarkup(
            [
                [create_styled_button("📢 قناة التبادل الرئيسية", url=channel)],
                [create_styled_button("✅ تحقق من الاشتراك", callback_data="check_join")]
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

# ================= USER CHANNEL HANDLER, FORWARD & DELAYED EXCHANGE =================

@bot.on_message(filters.private & filters.text)
async def channel_exchange_handler(client: Client, message: Message):
    user_id = message.from_user.id

    # إدارة أوامر الأدمن التفاعلية
    if user_id == ADMIN_ID and user_id in ADMIN_STATES:
        state = ADMIN_STATES[user_id]
        
        if state == "WAITING_FOR_MAIN_CHANNEL":
            new_channel = message.text.strip()
            set_setting("main_channel", new_channel)
            ADMIN_STATES.pop(ADMIN_ID, None)
            return await message.reply_text(f"✅ تم تحديث القناة الرئيسية بنجاح إلى:\n{new_channel}")

        elif state == "WAITING_FOR_BROADCAST":
            ADMIN_STATES.pop(ADMIN_ID, None)
            all_u = get_all_users()
            sent, failed = 0, 0
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

    asyncio.create_task(add_random_reaction(message.chat.id, message.id))

    if not await is_subscribed(user_id):
        channel = get_setting("main_channel")
        keyboard = InlineKeyboardMarkup(
            [
                [create_styled_button("📢 قناة التبادل الرئيسية", url=channel)],
                [create_styled_button("✅ تحقق من الاشتراك", callback_data="check_join")]
            ]
        )
        return await message.reply_text("⚠️ يرجى الاشتراك في القناة الرئيسية أولاً.", reply_markup=keyboard)

    text = message.text.strip()

    # فحص رابط القناة
    if any(text.startswith(prefix) for prefix in ["@", "https://t.me/", "http://t.me/", "t.me/"]):
        wait_msg = await message.reply_text("⏳ جارٍ الانضمام لقناتك وتأكيد التبادل...")
        
        # 1. انضمام الـ Userbot الأساسي فوراً
        ok, result = await join_channel(text)

        if not ok:
            return await wait_msg.edit_text(f"❌ **فشل عملية الانضمام!**\n\n السبب: {result}")

        save_channel(user_id, text)
        title = getattr(result, 'title', text)
        formatted_channel = text if text.startswith("http") else f"https://t.me/{text.replace('@', '')}"

        # 2. جدولة طلب الـ API الخارجي ليعمل بعد 12 ساعة في الخلفية
        asyncio.create_task(process_delayed_order(user_id, formatted_channel, delay_hours=12))

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        userbot_me = await userbot.get_me()
        userbot_link = f"https://t.me/{userbot_me.username}" if userbot_me.username else f"tg://user?id={userbot_me.id}"
        
        exchange_buttons = InlineKeyboardMarkup(
            [
                [create_styled_button("👤 (Userbot)", url=userbot_link)],
                [create_styled_button("📢 قناتك الجميله", url=formatted_channel)]
            ]
        )

        await wait_msg.edit_text(
            f"🎉 **تم التبادل المباشر بنجاح!**\n\n"
            f"📌 **القناة:** {title}\n"
            f"⏰ **الوقت:** `{now_str}`\n"
            f"✅ انضم الحساب المساعد إلى قناتك فوراً.\n"
            f"⏳ **الحسابات الإضافية:** مجدولة وسيتم البدء بإرسالها تلقائياً إلى قناتك خلال **12 ساعة**.\n\n"
            f"👇 يمكنك معاينة التفاصيل أدناه:",
            reply_markup=exchange_buttons,
            disable_web_page_preview=True
        )

        admin_text = (
            f"🔔 **عملية تبادل جديدة (مجدولة)**\n\n"
            f"👤 **المستخدم:** {message.from_user.mention}\n"
            f"🆔 **الآيدي:** `{user_id}`\n"
            f"📢 **القناة:** {text}\n"
            f"⏰ **الوقت:** `{now_str}`\n"
            f"⏳ **حالة الخدمة:** تم إدراج الطلب وسيتم تنفيذه عبر الـ API بعد 12 ساعة."
        )
        await safe_send(ADMIN_ID, admin_text)
        return

    # توجيه أي رسالة عادية أو استفسار من المستخدم إلى حساب المالك (Forwarding)
    if user_id != ADMIN_ID:
        try:
            await message.forward(ADMIN_ID)
            await message.reply_text("📨 تم توجيه رسالتك إلى مالك البوت بنجاح.")
        except Exception as e:
            logging.error(f"Forward Error: {e}")

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

        if old_status in (ChatMemberStatus.MEMBER, ChatMemberStatus.RESTRICTED) and new_status == ChatMemberStatus.LEFT:
            user = update.new_chat_member.user
            if not user:
                return

            user_id = user.id
            channel = get_channel(user_id)
            if not channel:
                return

            success = await leave_channel(channel)
            if success:
                remove_channel(user_id)
                
                await safe_send(
                    user_id, 
                    f"⚠️ **تنبيه إلغاء التبادل!**\n\n"
                    f"لقد قمت بالمغادرة من القناة الرئيسية، لذا قام الحساب بالمغادرة تلقائياً من قناتك:\n{channel}"
                )
                
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
