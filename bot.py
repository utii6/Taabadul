import asyncio
import logging
import os
import random
import json
import time
import traceback
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
    PeerIdInvalid,
    RPCError
)
from pyrogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)

from tasbeeh import send_random_zikr, register_tasbeeh_handlers
from time_avatar import update_profile_every_minute

# ================= LOGGING SETUP =================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | [%(levelname)s] | %(message)s"
)
logger = logging.getLogger("BotLogger")

# ================= ENVIRONMENT VARIABLES =================
API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
BOT_TOKEN = os.environ["BOT_TOKEN"]
USERBOT_SESSION = os.environ["USERBOT_SESSION"]
DATABASE_URL = os.environ["DATABASE_URL"]
ADMIN_ID = int(os.environ["ADMIN_ID"])

SMM_API_URL = os.environ.get("SMM_API_URL", "https://example.com/api/v2")
SMM_API_KEY = os.environ.get("SMM_API_KEY", "")
SMM_SERVICE_ID = os.environ.get("SMM_SERVICE_ID", "1")

FAKE_USERS_OFFSET = 1250 
REACTION_EMOJIS = ["😂", "❤️‍🔥", "❤️", "💔", "🔥", "🥳"]

HUMAN_ACTIONS = [
    ChatAction.TYPING,
    ChatAction.RECORD_AUDIO,
    ChatAction.UPLOAD_DOCUMENT,
    ChatAction.UPLOAD_PHOTO
]

ADMIN_STATES = {}
exchange_queue = asyncio.Queue(maxsize=1000)

# ================= TRANSLATION DICTIONARIES =================
LANG_AR = {
    "start_text": (
        "🚀 **أهلاً بك في بوت التبادل الآلي!**\n"
        "أرسل رابط أو معرف قناتك للبدء:\n"
        "▪️ `@KKEK2` | `https://t.me/KKEK2`\n"
        "⚙️ *سيتم تفعيل التبادل تلقائياً.*"
    ),
    "bio_btn": "⚙️ Bio",
    "lang_btn": "🌐 Language",
    "choose_lang": "🌐 **الرجاء اختيار لغتك المفضلة / Please select your language:**",
    "lang_changed": "✅ تم تغيير اللغة إلى العربية بنجاح!",
    "rules_text": (
        "💎 ═══ [ **دليل النظام والضوابط الشاملة** ] ═══ 💎\n\n"
        "🚀 **المميزات الاستثنائية للشبكة:**\n"
        " ├ 🤖 **تتبع آلي 100%:** مراقبة المنشورات ومنع الحذف المبكر.\n"
        " ├ 📊 **إحصائيات مباشرة:** تقارير فورية عن المشاهدات والتفاعل.\n"
        " └ 🎨 **تنسيق تلقائي:** محاذاة الإعلانات لتبدو احترافية.\n\n"
        "⚖️ **قواعد وشروط التبادل:**\n"
        " 𝟣️⃣ رفع البوت مشرفاً بصلاحية **النشر وتعديل الرسائل**.\n"
        " 𝟤️⃣ عدم حذف الإعلان أو نشر إعلانات منافسة أثناء فترة التبادل.\n"
        " 𝟥️⃣ الالتزام الكامل بشروط الخدمة والمحتوى المسموح.\n\n"
        "🌐 ═══ ═══ ═══ ═══ ═══ 🌐\n"
        "👨‍💻 **للمساعدة:** @E2E12"
    ),
    "dev_btn": "👨‍💻| DEV",
    "back_btn": "🔙 للقائمة الرئيسية",
    "exchange_success": (
        "🎉 **تم التبادل المباشر بنجاح!**\n\n"
        "📌 **القناة:** {title}\n"
        "⏰ **الوقت:** `{now_str}`\n"
        "✅ انضم الحساب المساعد إلى قناتك فوراً وسيتم بدء دعم الأعضاء لقناتك.\n\n"
        "👇 يمكنك معاينة التفاصيل أدناه:"
    ),
    "userbot_btn": "👤 (Userbot)",
    "your_channel_btn": "📢 قناتك الجميلة",
    "exchange_disabled": "⚠️ نظام التبادل متوقف حالياً للصيانة."
}

LANG_EN = {
    "start_text": (
        "🚀 **Welcome to Auto Exchange Bot!**\n"
        "Send your channel link or username to start:\n"
        "▪️ `@KKEK2` | `https://t.me/KKEK2`\n"
        "⚙️ *Exchange will be activated automatically.*"
    ),
    "bio_btn": "⚙️ Bio",
    "lang_btn": "🌐 Language",
    "choose_lang": "🌐 **Please select your preferred language:**",
    "lang_changed": "✅ Language changed to English successfully!",
    "rules_text": (
        "💎 ═══ [ **System Rules & Guide** ] ═══ 💎\n\n"
        "🚀 **Key Features:**\n"
        " ├ 🤖 **100% Automated:** Instant monitoring & auto-exchange.\n"
        " ├ 📊 **Live Stats:** Real-time metrics and audience updates.\n"
        " └ 🎨 **Auto Format:** Professional layout for messages.\n\n"
        "⚖️ **Exchange Rules:**\n"
        " 𝟣️⃣ Promote bot as admin with **Post & Edit** rights.\n"
        " 𝟤️⃣ Do not delete promotional posts during exchange.\n"
        " 𝟥️⃣ Comply with Telegram Terms of Service.\n\n"
        "🌐 ═══ ═══ ═══ ═══ ═══ 🌐\n"
        "👨‍💻 **Support:** @E2E12"
    ),
    "dev_btn": "👨‍💻| DEV",
    "back_btn": "🔙 Back to Main Menu",
    "exchange_success": (
        "🎉 **Exchange Completed Successfully!**\n\n"
        "📌 **Channel:** {title}\n"
        "⏰ **Time:** `{now_str}`\n"
        "✅ The assistant account joined your channel, members boost initiated.\n\n"
        "👇 Preview details below:"
    ),
    "userbot_btn": "👤 (Userbot)",
    "your_channel_btn": "📢 Your Channel",
    "exchange_disabled": "⚠️ Exchange system is currently undergoing maintenance."
}

def get_text(user_id: int, key: str) -> str:
    lang = get_user_language(user_id)
    dictionary = LANG_EN if lang == "en" else LANG_AR
    if key == "start_text":
        custom = get_setting(f"custom_start_{lang}", "")
        if custom:
            return custom
    return dictionary.get(key, LANG_AR.get(key, ""))

# ================= PYROGRAM CLIENTS =================
bot = Client("Bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)
register_tasbeeh_handlers(bot)

userbot = Client("Userbot", api_id=API_ID, api_hash=API_HASH, session_string=USERBOT_SESSION, in_memory=True)

# ================= BOT API DIRECT HELPER =================
async def send_colored_message(chat_id: int, text: str, reply_markup: dict = None, parse_mode: str = "Markdown"):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        async with ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                res_data = await resp.json()
                if not res_data.get("ok"):
                    logger.error(f"Bot API Direct Send Error: {res_data}")
                return res_data
    except Exception as e:
        logger.error(f"Failed to send colored message via Bot API: {e}")
        return None

# ================= DATABASE CONNECTION =================
def get_db_connection():
    while True:
        try:
            conn = psycopg2.connect(DATABASE_URL, sslmode="require", cursor_factory=RealDictCursor)
            conn.autocommit = True
            return conn
        except Exception as e:
            logger.error(f"Database connection error: {e}. Retrying in 3 seconds...")
            time.sleep(3)

db = get_db_connection()

def check_db_health():
    global db
    try:
        with db.cursor() as cursor:
            cursor.execute("SELECT 1;")
    except Exception:
        logger.warning("Database connection lost. Reconnecting...")
        db = get_db_connection()

# ================= DATABASE INIT =================
check_db_health()
with db.cursor() as cursor:
    cursor.execute("CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT)")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users(
        user_id BIGINT PRIMARY KEY,
        username TEXT,
        full_name TEXT,
        language TEXT DEFAULT 'ar',
        is_banned BOOLEAN DEFAULT FALSE,
        join_date TIMESTAMP DEFAULT NOW(),
        last_active TIMESTAMP DEFAULT NOW(),
        usage_count INT DEFAULT 0
    )
    """)
    cursor.execute("CREATE TABLE IF NOT EXISTS user_tasbeeh(user_id BIGINT PRIMARY KEY, count INT DEFAULT 0)")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS channels(
        id SERIAL PRIMARY KEY,
        user_id BIGINT UNIQUE,
        channel TEXT,
        last_order_time TIMESTAMP DEFAULT NOW() - INTERVAL '12 hours',
        joined_at TIMESTAMP DEFAULT NOW()
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS spam(
        user_id BIGINT PRIMARY KEY,
        messages INTEGER DEFAULT 0,
        last_message BIGINT DEFAULT 0,
        temp_ban_until TIMESTAMP DEFAULT NULL
    )
    """)
    cursor.execute("CREATE TABLE IF NOT EXISTS system_logs(id SERIAL PRIMARY KEY, event_type TEXT, details TEXT, created_at TIMESTAMP DEFAULT NOW())")
    cursor.execute("CREATE TABLE IF NOT EXISTS metrics(key TEXT PRIMARY KEY, value_count BIGINT DEFAULT 0)")

    try:
        cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS language TEXT DEFAULT 'ar';")
        cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_active TIMESTAMP DEFAULT NOW();")
        cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS usage_count INT DEFAULT 0;")
        cursor.execute("ALTER TABLE channels ADD COLUMN IF NOT EXISTS last_order_time TIMESTAMP DEFAULT NOW() - INTERVAL '12 hours';")
        cursor.execute("ALTER TABLE spam ADD COLUMN IF NOT EXISTS temp_ban_until TIMESTAMP DEFAULT NULL;")
    except Exception as e:
        logger.warning(f"Migration check passed: {e}")

# ================= LOGGING & METRICS =================
def log_event(event_type: str, details: str):
    check_db_health()
    try:
        with db.cursor() as cursor:
            cursor.execute("INSERT INTO system_logs (event_type, details) VALUES (%s, %s)", (event_type, details))
    except Exception as e:
        logger.error(f"Failed to log event: {e}")

def increment_metric(key: str, amount: int = 1):
    check_db_health()
    try:
        with db.cursor() as cursor:
            cursor.execute("""
            INSERT INTO metrics (key, value_count) VALUES (%s, %s)
            ON CONFLICT (key) DO UPDATE SET value_count = metrics.value_count + EXCLUDED.value_count;
            """, (key, amount))
    except Exception as e:
        logger.error(f"Failed metric increment: {e}")

def get_metric(key: str) -> int:
    check_db_health()
    try:
        with db.cursor() as cursor:
            cursor.execute("SELECT value_count FROM metrics WHERE key=%s", (key,))
            row = cursor.fetchone()
            return row["value_count"] if row else 0
    except Exception:
        return 0

# ================= SETTINGS & USER HELPERS =================
def get_setting(key: str, default: str = "true"):
    check_db_health()
    with db.cursor() as cursor:
        cursor.execute("SELECT value FROM settings WHERE key=%s", (key,))
        row = cursor.fetchone()
        return row["value"] if row else default

def set_setting(key: str, value: str):
    check_db_health()
    with db.cursor() as cursor:
        cursor.execute("""
            INSERT INTO settings(key,value) VALUES(%s,%s)
            ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value
            """, (key, str(value)))
    log_event("SETTINGS_UPDATE", f"Setting '{key}' set to '{value}'")

def get_user_language(user_id: int) -> str:
    check_db_health()
    with db.cursor() as cursor:
        cursor.execute("SELECT language FROM users WHERE user_id=%s", (user_id,))
        row = cursor.fetchone()
        return row["language"] if row and row.get("language") else "ar"

def set_user_language(user_id: int, lang: str):
    check_db_health()
    with db.cursor() as cursor:
        cursor.execute("UPDATE users SET language=%s WHERE user_id=%s", (lang, user_id))

def add_or_update_user(user_id: int, username: str, full_name: str):
    check_db_health()
    with db.cursor() as cursor:
        cursor.execute("SELECT user_id FROM users WHERE user_id=%s", (user_id,))
        exists = cursor.fetchone()
        cursor.execute("""
            INSERT INTO users (user_id, username, full_name, last_active, usage_count)
            VALUES (%s, %s, %s, NOW(), 1)
            ON CONFLICT (user_id) 
            DO UPDATE SET username=EXCLUDED.username, full_name=EXCLUDED.full_name, last_active=NOW(), usage_count=users.usage_count + 1
            """, (user_id, username, full_name))
        return exists is None

def is_banned(user_id: int):
    check_db_health()
    with db.cursor() as cursor:
        cursor.execute("SELECT is_banned FROM users WHERE user_id=%s", (user_id,))
        row = cursor.fetchone()
        return row["is_banned"] if row else False

def set_ban_status(user_id: int, banned: bool):
    check_db_health()
    with db.cursor() as cursor:
        cursor.execute("UPDATE users SET is_banned=%s WHERE user_id=%s", (banned, user_id))
    log_event("USER_BAN_TOGGLE", f"User {user_id} ban set to {banned}")

def get_channel_data(user_id: int):
    check_db_health()
    with db.cursor() as cursor:
        cursor.execute("SELECT channel, last_order_time FROM channels WHERE user_id=%s", (user_id,))
        return cursor.fetchone()

def update_channel_order(user_id: int, channel: str):
    check_db_health()
    with db.cursor() as cursor:
        cursor.execute("""
            INSERT INTO channels (user_id, channel, last_order_time)
            VALUES (%s, %s, NOW())
            ON CONFLICT (user_id) DO UPDATE SET channel=EXCLUDED.channel, last_order_time=NOW()
            """, (user_id, channel))

def remove_channel(user_id: int):
    check_db_health()
    with db.cursor() as cursor:
        cursor.execute("DELETE FROM channels WHERE user_id=%s", (user_id,))
    log_event("CHANNEL_REMOVE", f"Channel removed for user {user_id}")

def get_channel(user_id: int):
    check_db_health()
    with db.cursor() as cursor:
        cursor.execute("SELECT channel FROM channels WHERE user_id=%s", (user_id,))
        row = cursor.fetchone()
        return row["channel"] if row else None

def get_stats():
    check_db_health()
    with db.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) as total_users FROM users;")
        users_count = cursor.fetchone()["total_users"]
        cursor.execute("SELECT COUNT(*) as total_channels FROM channels;")
        channels_count = cursor.fetchone()["total_channels"]
        return users_count, channels_count

def get_all_users():
    check_db_health()
    with db.cursor() as cursor:
        cursor.execute("SELECT user_id FROM users WHERE is_banned=FALSE;")
        return [row["user_id"] for row in cursor.fetchall()]

# ================= ANTI SPAM =================
def update_spam(user_id: int):
    check_db_health()
    now_ts = int(time.time())
    now_dt = datetime.now()
    with db.cursor() as cursor:
        cursor.execute("SELECT messages, last_message, temp_ban_until FROM spam WHERE user_id=%s", (user_id,))
        row = cursor.fetchone()
        if row and row["temp_ban_until"] and row["temp_ban_until"] > now_dt:
            return -2 
        if row is None:
            cursor.execute("INSERT INTO spam (user_id, messages, last_message) VALUES (%s, 1, %s)", (user_id, now_ts))
            return 1
        if now_ts - row["last_message"] > 10:
            cursor.execute("UPDATE spam SET messages=1, last_message=%s WHERE user_id=%s", (now_ts, user_id))
            return 1
        count = row["messages"] + 1
        if count >= 8:
            ban_until = now_dt + timedelta(minutes=5)
            cursor.execute("UPDATE spam SET messages=%s, last_message=%s, temp_ban_until=%s WHERE user_id=%s", (count, now_ts, ban_until, user_id))
            log_event("SPAM_TEMP_BAN", f"User {user_id} temporarily banned for spam.")
            return -1 
        cursor.execute("UPDATE spam SET messages=%s, last_message=%s WHERE user_id=%s", (count, now_ts, user_id))
        return count

async def anti_spam(message: Message):
    if not message or not message.from_user or message.from_user.id == ADMIN_ID:
        return True
    if get_setting("anti_spam", "true") == "false":
        return True
    user_id = message.from_user.id
    status = update_spam(user_id)
    if status == -2:
        return False
    if status == -1:
        await send_colored_message(chat_id=message.chat.id, text="⛔ **تم حظرك مؤقتاً لمدة 5 دقائق بسبب السبام.**")
        return False
    return True

# ================= HUMAN ACTIONS & EMOJI REACTIONS =================
async def simulate_human_action(chat_id: int, duration: float = None):
    try:
        chosen_action = random.choice(HUMAN_ACTIONS)
        await bot.send_chat_action(chat_id=chat_id, action=chosen_action)
        wait_time = duration if duration else random.uniform(1.0, 1.8)
        await asyncio.sleep(wait_time)
    except Exception as e:
        logger.debug(f"Chat action error: {e}")

async def add_random_reaction(message: Message):
    if not message or not message.chat:
        return
    try:
        emoji = random.choice(REACTION_EMOJIS)
        await bot.react(chat_id=message.chat.id, message_id=message.id, emoji=emoji)
    except Exception as e:
        logger.debug(f"Reaction Handled/Skipped: {e}")

# ================= SMM API CALLS =================
async def order_smm_services(target_link: str, quantity: int = 10, retries: int = 3):
    if not SMM_API_KEY or not SMM_API_URL:
        log_event("API_ERROR", "SMM API config missing")
        increment_metric("api_failed")
        return False, "إعدادات الـ API غير مكتملة"

    payload = {'key': SMM_API_KEY, 'action': 'add', 'service': SMM_SERVICE_ID, 'link': target_link, 'quantity': str(quantity)}
    headers = {"User-Agent": "Mozilla/5.0"}

    for attempt in range(1, retries + 1):
        try:
            async with ClientSession(headers=headers) as session:
                async with session.post(SMM_API_URL, data=payload, timeout=10) as resp:
                    data = await resp.json(content_type=None)
                    if isinstance(data, dict) and "order" in data:
                        log_event("API_SUCCESS", f"Order ID {data['order']} for link {target_link}")
                        increment_metric("api_success")
                        return True, data["order"]
                    else:
                        error_msg = data.get("error", str(data)) if isinstance(data, dict) else str(data)
                        if attempt == retries:
                            log_event("API_FAILED", f"Link: {target_link} | Error: {error_msg}")
                            increment_metric("api_failed")
                            return False, error_msg
        except Exception as e:
            if attempt == retries:
                log_event("API_EXCEPTION", f"Link: {target_link} | Exception: {e}")
                increment_metric("api_failed")
                return False, str(e)
        await asyncio.sleep(2 * attempt)

# ================= SCHEDULER TASK =================
async def schedule_12h_notification(user_id: int, delay_seconds: int = 43200):
    await asyncio.sleep(delay_seconds)
    msg_text = "🔔 **انقضت 12 ساعة!**\n\n✨ حان وقت التبادل الجديد! أرسل رابط قناتك مجدداً للحصول على أعضاء 🚀."
    await safe_send(user_id, msg_text)
    log_event("SCHEDULED_NOTIF", f"12h Notification sent to user {user_id}")

async def safe_send(chat_id, text, **kwargs):
    try:
        await simulate_human_action(chat_id)
        return await bot.send_message(chat_id, text, **kwargs)
    except FloodWait as e:
        await asyncio.sleep(e.value)
        return await safe_send(chat_id, text, **kwargs)
    except Exception as e:
        logger.error(f"Safe send error for {chat_id}: {e}")
        return None

# ================= USERBOT JOINING =================
async def join_channel(channel: str):
    channel = channel.strip()
    if "t.me/" in channel and not ("/+" in channel or "joinchat" in channel):
        channel = channel.split("t.me/")[-1].replace("@", "").split("/")[0]

    try:
        chat = await userbot.join_chat(channel)
        log_event("USERBOT_JOIN", f"Successfully joined {channel}")
        return True, chat
    except UserAlreadyParticipant:
        chat = await userbot.get_chat(channel)
        return True, chat
    except (UsernameInvalid, UsernameNotOccupied):
        log_event("USERBOT_JOIN_FAILED", f"Invalid channel: {channel}")
        return False, "💔 رابط القناة غير صالح أو غير موجود."
    except FloodWait as e:
        await asyncio.sleep(e.value)
        return await join_channel(channel)
    except Exception as e:
        log_event("USERBOT_JOIN_EXCEPTION", f"Channel {channel}: {e}")
        return False, f"❌ تعذر الانضمام: {str(e)}"

# ================= ADMIN PANEL KEYBOARD =================
def get_admin_main_keyboard():
    return {
        "inline_keyboard": [
            [
                {"text": "📊 الإحصائيات المتقدمة", "callback_data": "admin_stats", "style": "primary"},
                {"text": "⚙️ إعدادات البوت", "callback_data": "admin_settings", "style": "primary"}
            ],
            [
                {"text": "👥 إدارة المستخدمين", "callback_data": "admin_users_menu", "style": "primary"},
                {"text": "📢 القنوات والتبادل", "callback_data": "admin_channels_menu", "style": "primary"}
            ],
            [
                {"text": "📡 نظام البث الاحترافي", "callback_data": "admin_broadcast_menu", "style": "success"},
                {"text": "✏️ تعديل الترحيب", "callback_data": "admin_edit_start_menu", "style": "success"}
            ],
            [
                {"text": "💾 النسخ الاحتياطي", "callback_data": "admin_backup", "style": "success"},
                {"text": "📜 سجلات النظام", "callback_data": "admin_logs", "style": "danger"}
            ],
            [
                {"text": "❌ إغلاق اللوحة", "callback_data": "admin_close", "style": "danger"}
            ]
        ]
    }

@bot.on_message(filters.private & filters.command("admin"))
async def admin_panel_cmd(client: Client, message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    await add_random_reaction(message)
    await simulate_human_action(message.chat.id)
    await send_colored_message(
        chat_id=message.chat.id,
        text="🛠️ **مرحباً بك في لوحة تحكم المالك المتقدمة**\n\nاختر القسم الذي تريد إدارته من القائمة أدناه:",
        reply_markup=get_admin_main_keyboard()
    )

@bot.on_callback_query(filters.regex("^admin_"))
async def admin_callbacks(client: Client, query: CallbackQuery):
    if query.from_user.id != ADMIN_ID:
        return await query.answer("❌ لا تملك صلاحية الوصول.", show_alert=True)

    data = query.data

    if data == "admin_stats":
        u_count, c_count = get_stats()
        total_display_users = u_count + FAKE_USERS_OFFSET
        api_succ = get_metric("api_success")
        api_fail = get_metric("api_failed")
        ex_count = get_metric("exchanges")

        stats_text = (
            f"📊 **إحصائيات البوت المتقدمة والشاملة:**\n\n"
            f"👤 **المستخدمين الحقيقيين:** `{u_count}`\n"
            f"🌐 **إجمالي المشتركين (مع الوهمي):** `{total_display_users}`\n"
            f"🔄 **إجمالي عمليات التبادل:** `{ex_count}`\n"
            f"📢 **القنوات المتبادلة حالياً:** `{c_count}`\n\n"
            f"🚀 **طلبات الـ API الناجحة:** `{api_succ}`\n"
            f"❌ **طلبات الـ API الفاشلة:** `{api_fail}`"
        )
        buttons = {"inline_keyboard": [[{"text": "🔙 العودة للوحة الرئيسية", "callback_data": "admin_home", "style": "primary"}]]}
        await query.answer()
        await send_colored_message(query.message.chat.id, stats_text, reply_markup=buttons)

    elif data == "admin_settings":
        spam_status = get_setting("anti_spam", "true")
        ex_status = get_setting("exchange_enabled", "true")
        settings_text = (
            "⚙️ **لوحة التحكم في إعدادات النظام الداخلية:**\n\n"
            f"🛡️ **مكافحة السبام:** `{'مفعل ✅' if spam_status == 'true' else 'معطل ❌'}`\n"
            f"🔄 **نظام التبادل:** `{'مفعل ✅' if ex_status == 'true' else 'معطل ❌'}`\n"
        )
        buttons = {
            "inline_keyboard": [
                [{"text": "تغيير مكافحة السبام", "callback_data": "toggle_setting_anti_spam", "style": "primary"}],
                [{"text": "تغيير وضع التبادل", "callback_data": "toggle_setting_exchange_enabled", "style": "primary"}],
                [{"text": "🔙 العودة", "callback_data": "admin_home", "style": "danger"}]
            ]
        }
        await query.answer()
        await send_colored_message(query.message.chat.id, settings_text, reply_markup=buttons)

    elif data.startswith("toggle_setting_"):
        setting_key = data.replace("toggle_setting_", "")
        curr_val = get_setting(setting_key, "true")
        new_val = "false" if curr_val == "true" else "true"
        set_setting(setting_key, new_val)
        await query.answer("✅ تم تحديث الإعداد بنجاح!", show_alert=True)
        return await admin_callbacks(client, query)

    elif data == "admin_edit_start_menu":
        await query.answer()
        buttons = {
            "inline_keyboard": [
                [{"text": "✏️ تعديل الترحيب العربي", "callback_data": "admin_set_start_ar", "style": "primary"}],
                [{"text": "✏️ Edit English Welcome", "callback_data": "admin_set_start_en", "style": "primary"}],
                [{"text": "🔄 إعادة الافتراضي", "callback_data": "admin_reset_start", "style": "danger"}],
                [{"text": "🔙 العودة", "callback_data": "admin_home", "style": "primary"}]
            ]
        }
        await send_colored_message(query.message.chat.id, "⚙️ **قسم تعديل رسالة /start الترحيبية:**", reply_markup=buttons)

    elif data in ["admin_set_start_ar", "admin_set_start_en"]:
        lang = "ar" if data == "admin_set_start_ar" else "en"
        ADMIN_STATES[ADMIN_ID] = f"WAITING_FOR_START_{lang.upper()}"
        await query.answer()
        await send_colored_message(query.message.chat.id, f"أرسل النص الجديد للرسالة الترحيبية باللغة ({lang.upper()}):\nأرسل /cancel للإلغاء.")

    elif data == "admin_reset_start":
        set_setting("custom_start_ar", "")
        set_setting("custom_start_en", "")
        await query.answer("✅ تم إعادة الرسائل الترحيبية للوضع الافتراضي!", show_alert=True)

    elif data == "admin_backup":
        check_db_health()
        with db.cursor() as cursor:
            cursor.execute("SELECT user_id, username, full_name, join_date FROM users;")
            all_users_db = cursor.fetchall()
            cursor.execute("SELECT user_id, channel, last_order_time FROM channels;")
            all_channels_db = cursor.fetchall()

        backup_data = {
            "timestamp": str(datetime.now()),
            "users": [dict(u) for u in all_users_db],
            "channels": [dict(c) for c in all_channels_db]
        }
        backup_filename = f"backup_{int(time.time())}.json"
        with open(backup_filename, "w", encoding="utf-8") as f:
            json.dump(backup_data, f, ensure_ascii=False, indent=2, default=str)

        await query.answer("💾 تم إنتاج النسخة الاحتياطية")
        await bot.send_document(ADMIN_ID, backup_filename, caption="📦 **نسخة احتياطية كاملة لقاعدة البيانات**")
        os.remove(backup_filename)

    elif data == "admin_logs":
        check_db_health()
        with db.cursor() as cursor:
            cursor.execute("SELECT event_type, details, created_at FROM system_logs ORDER BY id DESC LIMIT 10;")
            logs_rows = cursor.fetchall()
        logs_text = "📜 **آخر 10 أحداث مسجلة في النظام:**\n\n"
        for l in logs_rows:
            logs_text += f"🔹 [{l['created_at'].strftime('%H:%M:%S')}] **{l['event_type']}**: {l['details']}\n"
        buttons = {"inline_keyboard": [[{"text": "🔙 العودة", "callback_data": "admin_home", "style": "primary"}]]}
        await query.answer()
        await send_colored_message(query.message.chat.id, logs_text, reply_markup=buttons)

    elif data == "admin_broadcast_menu":
        ADMIN_STATES[ADMIN_ID] = "WAITING_FOR_BROADCAST"
        await query.answer()
        buttons = {"inline_keyboard": [[{"text": "إلغاء الإذاعة ❌", "callback_data": "admin_home", "style": "danger"}]]}
        await send_colored_message(
            query.message.chat.id,
            "📢 **نظام البث الاحترافي:**\n\nأرسل الآن (نص، صورة، فيديو، أو ملف) ليتم بثه لجميع المستخدمين، أو أرسل /cancel للإلغاء.",
            reply_markup=buttons
        )

    elif data == "admin_users_menu":
        await query.answer()
        buttons = {"inline_keyboard": [[{"text": "🔙 العودة للوحة", "callback_data": "admin_home", "style": "primary"}]]}
        await send_colored_message(
            query.message.chat.id,
            "👥 **إدارة المستخدمين:**\n\n"
            "▫️ لحظر مستخدم: أرسل كلمة `حظر` بالرد على رسالته أو اكتب `حظر ID`\n"
            "▫️ لفك الحظر: أرسل كلمة `إلغاء الحظر` بالرد على رسالته أو اكتب `إلغاء الحظر ID`\n"
            "▫️ للبحث عن بيانات مستخدم: `/user USER_ID`",
            reply_markup=buttons
        )

    elif data == "admin_channels_menu":
        await query.answer()
        buttons = {"inline_keyboard": [[{"text": "🔙 العودة للوحة", "callback_data": "admin_home", "style": "primary"}]]}
        await send_colored_message(
            query.message.chat.id,
            "📢 **إدارة القنوات والتبادل:**\n\n"
            "▫️ البحث عن قناة مستخدم: `/getchannel USER_ID`\n"
            "▫️ حذف قناة مستخدم: `/delchannel USER_ID`",
            reply_markup=buttons
        )

    elif data == "admin_home":
        ADMIN_STATES.pop(ADMIN_ID, None)
        await query.answer()
        await send_colored_message(
            query.message.chat.id,
            "🛠️ **مرحباً بك في لوحة تحكم المالك المتقدمة**\n\nاختر القسم الذي تريد إدارته من القائمة أدناه:",
            reply_markup=get_admin_main_keyboard()
        )

    elif data == "admin_close":
        ADMIN_STATES.pop(ADMIN_ID, None)
        await query.answer("تم الإغلاق")
        await query.message.delete()

# ================= USER & CHANNEL MANAGEMENT COMMANDS =================
@bot.on_message(filters.private & filters.command("user"))
async def get_user_info_cmd(client: Client, message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        target_id = int(message.text.split()[1])
        check_db_health()
        with db.cursor() as cursor:
            cursor.execute("SELECT * FROM users WHERE user_id=%s", (target_id,))
            user_data = cursor.fetchone()

        if not user_data:
            return await send_colored_message(message.chat.id, "❌ لم يتم العثور على هذا المستخدم في قاعدة البيانات.")

        ch = get_channel(target_id)
        info = (
            f"👤 **بيانات المستخدم التفصيلية:**\n\n"
            f"🆔 **الآيدي:** `{user_data['user_id']}`\n"
            f"📛 **الاسم:** {user_data['full_name']}\n"
            f"🌐 **اليوزر:** @{user_data['username'] if user_data['username'] else 'لا يوجد'}\n"
            f"🚫 **محظور:** {'نعم' if user_data['is_banned'] else 'لا'}\n"
            f"🔄 **عدد مرات الاستخدام:** `{user_data['usage_count']}`\n"
            f"📅 **تاريخ الانضمام:** `{user_data['join_date']}`\n"
            f"⏰ **آخر نشاط:** `{user_data['last_active']}`\n"
            f"📢 **القناة المرتبطة:** {ch if ch else 'لا توجد'}"
        )
        await send_colored_message(message.chat.id, info)
    except Exception:
        await send_colored_message(message.chat.id, "⚠️ صيغة غير صحيحة. الاستخدام: `/user 123456789`")

@bot.on_message(filters.private & filters.command("getchannel"))
async def get_channel_cmd(client: Client, message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        target_id = int(message.text.split()[1])
        ch_data = get_channel_data(target_id)
        if ch_data:
            await send_colored_message(
                message.chat.id,
                f"📢 **تفاصيل القناة:**\n\n"
                f"👤 **صاحب القناة:** `{target_id}`\n"
                f"🔗 **رابط القناة:** {ch_data['channel']}\n"
                f"⏰ **آخر طلب تبادل:** `{ch_data['last_order_time']}`"
            )
        else:
            await send_colored_message(message.chat.id, "❌ لا توجد قناة مسجلة لهذا المستخدم.")
    except Exception:
        await send_colored_message(message.chat.id, "⚠️ الصيغة: `/getchannel 123456789`")

@bot.on_message(filters.private & filters.command("delchannel"))
async def del_channel_cmd(client: Client, message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        target_id = int(message.text.split()[1])
        remove_channel(target_id)
        await send_colored_message(message.chat.id, f"✅ تم حذف القناة المرتبطة بالمستخدم `{target_id}` بنجاح.")
    except Exception:
        await send_colored_message(message.chat.id, "⚠️ الصيغة: `/delchannel 123456789`")

@bot.on_message(filters.private & filters.regex("^(حظر|إلغاء الحظر)"))
async def handle_ban_unban_ar(client: Client, message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    await add_random_reaction(message)
    await simulate_human_action(message.chat.id)

    text = message.text.strip()
    is_ban = text.startswith("حظر")
    target_id = None

    if message.reply_to_message and message.reply_to_message.forward_from:
        target_id = message.reply_to_message.forward_from.id
    else:
        parts = text.split()
        if len(parts) > 1 and parts[1].isdigit():
            target_id = int(parts[1])

    if not target_id:
        return await send_colored_message(message.chat.id, "⚠️ يرجى استخدام الأمر بالرد على رسالة المستخدم أو كـ: `حظر 123456789`")

    set_ban_status(target_id, is_ban)
    status_msg = "حظر" if is_ban else "فك حظر"
    await send_colored_message(message.chat.id, f"✅ تم {status_msg} المستخدم `{target_id}` بنجاح.")

@bot.on_message(filters.private & filters.command("cancel"))
async def cancel_admin_state(client: Client, message: Message):
    if message.from_user.id == ADMIN_ID and ADMIN_ID in ADMIN_STATES:
        await add_random_reaction(message)
        await simulate_human_action(message.chat.id)
        ADMIN_STATES.pop(ADMIN_ID, None)
        await send_colored_message(message.chat.id, "✅ تم إلغاء العملية والعودة للوضع الطبيعي.")

# ================= LANGUAGE COMMAND & SWITCH =================
@bot.on_message(filters.private & filters.command("lan"))
async def language_command(client: Client, message: Message):
    await add_random_reaction(message)
    await simulate_human_action(message.chat.id)
    lang_keyboard = {
        "inline_keyboard": [
            [
                {"text": "🇸🇦 العربية", "callback_data": "set_lang_ar", "style": "primary"},
                {"text": "🇺🇸 English", "callback_data": "set_lang_en", "style": "primary"}
            ]
        ]
    }
    user_id = message.from_user.id
    await send_colored_message(message.chat.id, get_text(user_id, "choose_lang"), reply_markup=lang_keyboard)

@bot.on_callback_query(filters.regex("^set_lang_"))
async def set_language_callback(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    lang = query.data.split("_")[-1]
    set_user_language(user_id, lang)
    msg = LANG_EN["lang_changed"] if lang == "en" else LANG_AR["lang_changed"]
    await query.answer(msg, show_alert=True)
    await send_welcome_message(query.message.chat.id, user_id)

# ================= WELCOME MESSAGE SENDER =================
async def send_welcome_message(chat_id: int, user_id: int):
    lang = get_user_language(user_id)
    start_buttons = {
        "inline_keyboard": [
            [
                {"text": get_text(user_id, "bio_btn"), "callback_data": "show_rules_and_features", "style": "primary"},
                {"text": get_text(user_id, "lang_btn"), "callback_data": "open_language_menu", "style": "primary"}
            ]
        ]
    }
    await send_colored_message(
        chat_id=chat_id,
        text=get_text(user_id, "start_text"),
        reply_markup=start_buttons
    )

# ================= START COMMAND =================
@bot.on_message(filters.private & filters.command("start"))
async def start_handler(client: Client, message: Message):
    user_id = message.from_user.id
    await add_random_reaction(message)

    if is_banned(user_id) or not await anti_spam(message):
        return

    if not await check_forced_subscribe(client, message):
        return

    username = message.from_user.username or ""
    full_name = message.from_user.first_name or ""
    if message.from_user.last_name:
        full_name += f" {message.from_user.last_name}"

    is_new = add_or_update_user(user_id, username, full_name)
    
    if is_new and user_id != ADMIN_ID:
        log_event("NEW_USER", f"User {user_id} (@{username}) joined.")
        real_users_count, _ = get_stats()
        total_users_count = real_users_count + FAKE_USERS_OFFSET
        user_mention = message.from_user.mention
        
        new_user_text = (
            f"❤️‍🔥👤 **عضو جديد انضم للبوت!**\n\n"
            f"▫️ **الاسم:** {user_mention}\n"
            f"▫️ **الآيدي:** `{user_id}`\n"
            f"▫️ **اليوزر:** @{username if username else 'بدون يوزر'}\n"
            f"▫️🔥 **العدد الكلي:** `{total_users_count}`"
        )
        await safe_send(ADMIN_ID, new_user_text)

    await simulate_human_action(message.chat.id)
    await send_welcome_message(message.chat.id, user_id)
    await send_random_zikr(client, message.chat.id, user_id)

# ================= FORWARD & REPLY SYSTEM =================
@bot.on_message(filters.private & filters.reply)
async def admin_reply_to_user_handler(client: Client, message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    await add_random_reaction(message)

    reply_to = message.reply_to_message
    if reply_to and reply_to.forward_from:
        target_user_id = reply_to.forward_from.id
        try:
            await simulate_human_action(target_user_id)
            await message.copy(chat_id=target_user_id)
            await send_colored_message(message.chat.id, "✅ تم إرسال ردك للمستخدم بنجاح.")
        except Exception as e:
            await send_colored_message(message.chat.id, f"❌ تعذر إرسال الرد للمستخدم: {e}")
    else:
        await send_colored_message(message.chat.id, "⚠️ يرجى الرد على رسالة موجهة مباشرة من مستخدم.")

# ================= WORKER & QUEUE FOR EXCHANGE PROCESS =================
async def process_exchange_queue():
    while True:
        task = await exchange_queue.get()
        client, message, text = task
        try:
            await execute_exchange_logic(client, message, text)
        except Exception as e:
            logger.error(f"Error executing queue task: {e}\n{traceback.format_exc()}")
            log_event("QUEUE_ERROR", str(e))
        finally:
            exchange_queue.task_done()

async def execute_exchange_logic(client: Client, message: Message, text: str):
    user_id = message.from_user.id
    await simulate_human_action(message.chat.id)
    wait_msg = await bot.send_message(message.chat.id, "⏳ *جارٍ الانضمام لقناتك وتأكيد التبادل*...")
    
    ok, result = await join_channel(text)

    if not ok:
        await simulate_human_action(message.chat.id)
        err_msg = (
            f"❌ **فشل عملية الانضمام!**\n\n"
            f"**السبب:** {result}\n\n"
            f"💡 **حلول مقترحة:**\n"
            f"1️⃣ تأكد أن القناة عامة وليست خاصة.\n"
            f"2️⃣ تأكد من صحة معرف القناة وتأكد من أن البوت ليس محظوراً بها."
        )
        return await wait_msg.edit_text(err_msg)

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
        update_channel_order(user_id, formatted_channel)
        asyncio.create_task(order_smm_services(formatted_channel, quantity=10))
        asyncio.create_task(schedule_12h_notification(user_id, delay_seconds=43200))
    else:
        check_db_health()
        with db.cursor() as cursor:
            cursor.execute("UPDATE channels SET channel=%s WHERE user_id=%s", (formatted_channel, user_id))

    increment_metric("exchanges")
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")

    userbot_me = await userbot.get_me()
    userbot_link = f"https://t.me/{userbot_me.username}" if userbot_me.username else f"tg://user?id={userbot_me.id}"
    
    exchange_buttons = {
        "inline_keyboard": [
            [{"text": get_text(user_id, "userbot_btn"), "url": userbot_link, "style": "primary"}],
            [{"text": get_text(user_id, "your_channel_btn"), "url": formatted_channel, "style": "success"}]
        ]
    }

    await simulate_human_action(message.chat.id)
    await wait_msg.delete()

    succ_text = get_text(user_id, "exchange_success").format(title=title, now_str=now_str)

    await send_colored_message(
        chat_id=message.chat.id,
        text=succ_text,
        reply_markup=exchange_buttons
    )

    admin_text = (
        f"🔔 **عملية تبادل جديدة**\n\n"
        f"👤 **المستخدم:** {message.from_user.mention}\n"
        f"🆔 **الآيدي:** `{user_id}`\n"
        f"📢 **القناة:** {text}\n"
        f"🌐 **إرسال API:** {'نعم (تم)' if should_send_api else 'مؤجل (أقل من 12 ساعة)'}"
    )
    await safe_send(ADMIN_ID, admin_text)

# ================= FORCED SUBSCRIBE CHECK =================
async def check_forced_subscribe(client: Client, message: Message):
    if not message.from_user or message.from_user.id == ADMIN_ID:
        return True

    is_enabled = get_setting("forced_sub_enabled", "true")
    channel = get_setting("forced_sub_channel", "@KKEK2")

    if is_enabled == "false" or not channel:
        return True

    try:
        member = await client.get_chat_member(channel, message.from_user.id)
        if member.status in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.MEMBER]:
            return True
    except Exception:
        pass

    clean_channel = channel.replace("@", "").replace("https://t.me/", "").replace("http://t.me/", "")
    keyboard = {
        "inline_keyboard": [
            [{"text": "📢 اشتـرك بالقناه", "url": f"https://t.me/{clean_channel}", "style": "primary"}],
            [{"text": "🔄 تحقق من اشتراكك", "callback_data": "check_sub", "style": "success"}]
        ]
    }

    await send_colored_message(
        chat_id=message.chat.id,
        text=f"⚠️ **عذراً عزيزي، يجب عليك الاشتراك في قناة البوت أولاً لاستخدام الخدمات:**\n\n@{clean_channel}\n\nاشترك ثم اضغط على زر التحقق أسفله 👇",
        reply_markup=keyboard
    )
    return False

# ================= CALLBACK HANDLERS FOR USER MENU =================
@bot.on_callback_query(filters.regex("^(show_rules_and_features|back_to_main|open_language_menu)$"))
async def user_menu_callbacks(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    data = query.data

    if data == "show_rules_and_features":
        rules_buttons = {
            "inline_keyboard": [
                [{"text": get_text(user_id, "dev_btn"), "url": "https://t.me/E2E12", "style": "primary"}],
                [{"text": get_text(user_id, "back_btn"), "callback_data": "back_to_main", "style": "primary"}]
            ]
        }
        await query.answer()
        await send_colored_message(query.message.chat.id, get_text(user_id, "rules_text"), reply_markup=rules_buttons)

    elif data == "open_language_menu":
        await query.answer()
        lang_keyboard = {
            "inline_keyboard": [
                [
                    {"text": "🇸🇦 العربية", "callback_data": "set_lang_ar", "style": "primary"},
                    {"text": "🇺🇸 English", "callback_data": "set_lang_en", "style": "primary"}
                ]
            ]
        }
        await send_colored_message(query.message.chat.id, get_text(user_id, "choose_lang"), reply_markup=lang_keyboard)

    elif data == "back_to_main":
        await query.answer()
        await send_welcome_message(query.message.chat.id, user_id)

@bot.on_callback_query(filters.regex("^check_sub$"))
async def on_check_sub(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    channel = get_setting("forced_sub_channel", "@KKEK2")

    try:
        member = await client.get_chat_member(channel, user_id)
        if member.status in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.MEMBER]:
            await callback_query.answer("✅ شكراً لك! تم التأكد من اشتراكك، يمكنك الآن استخدام البوت.", show_alert=True)
            await callback_query.message.delete()
            return
    except Exception:
        pass

    await callback_query.answer("❌ أنت غير مشترك في القناة بعد! يرجى الاشتراك أولاً.", show_alert=True)

@bot.on_message(filters.command("setchannel") & filters.private)
async def set_forced_channel(client: Client, message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        return await message.reply_text("⚠️ **يرجى إرسال المعرف مع الأمر، مثال:**\n`/setchannel @KKEK2`")
    new_channel = args[1].strip()
    set_setting("forced_sub_channel", new_channel)
    await message.reply_text(f"✅ **تم تحديث قناة الاشتراك الإجباري بنجاح إلى:** {new_channel}")

@bot.on_message(filters.command("togglesub") & filters.private)
async def toggle_forced_sub(client: Client, message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    current = get_setting("forced_sub_enabled", "true")
    new_status = "false" if current == "true" else "true"
    set_setting("forced_sub_enabled", new_status)
    status_text = "🟢 مفعّل" if new_status == "true" else "🔴 معطل"
    await message.reply_text(f"⚙️ **تم تغيير حالة الاشتراك الإجباري إلى:** {status_text}")

# ================= MAIN ROUTER FOR MESSAGES & BROADCAST =================
@bot.on_message(filters.private)
async def main_message_router(client: Client, message: Message):
    if not message or not message.from_user or message.from_user.is_bot:
        return

    user_id = message.from_user.id
    await add_random_reaction(message)

    if user_id == ADMIN_ID and user_id in ADMIN_STATES:
        state = ADMIN_STATES[user_id]

        if state == "WAITING_FOR_START_AR":
            ADMIN_STATES.pop(ADMIN_ID, None)
            set_setting("custom_start_ar", message.text.strip())
            return await send_colored_message(message.chat.id, "✅ تم حفظ الرسالة الترحيبية العربية بنجاح!")

        elif state == "WAITING_FOR_START_EN":
            ADMIN_STATES.pop(ADMIN_ID, None)
            set_setting("custom_start_en", message.text.strip())
            return await send_colored_message(message.chat.id, "✅ English welcome message saved successfully!")

        elif state == "WAITING_FOR_BROADCAST":
            ADMIN_STATES.pop(ADMIN_ID, None)
            all_u = get_all_users()
            sent, failed = 0, 0
            await simulate_human_action(message.chat.id)
            await send_colored_message(message.chat.id, f"⏳ جارٍ الإذاعة لـ {len(all_u)} مستخدم...")

            for u in all_u:
                try:
                    await message.copy(int(u))
                    sent += 1
                    await asyncio.sleep(0.04)
                except Exception:
                    failed += 1

            log_event("BROADCAST_COMPLETED", f"Sent: {sent}, Failed: {failed}")
            return await send_colored_message(
                message.chat.id,
                f"🎉 **تمت الإذاعة بنجاح!**\n\n✅ المستلمون: `{sent}`\n❌ الفاشلون: `{failed}`"
            )

    if is_banned(user_id) or not await anti_spam(message):
        return

    if not await check_forced_subscribe(client, message):
        return

    text = message.text.strip() if message.text else ""

    if text and any(text.startswith(prefix) for prefix in ["@", "https://t.me/", "http://t.me/", "t.me/"]):
        if get_setting("exchange_enabled", "true") == "false":
            return await send_colored_message(message.chat.id, get_text(user_id, "exchange_disabled"))

        await exchange_queue.put((client, message, text))
        await send_random_zikr(client, message.chat.id, user_id)
        return

    if user_id != ADMIN_ID:
        try:
            await message.forward(ADMIN_ID)
            await simulate_human_action(message.chat.id)
            await send_random_zikr(client, message.chat.id, user_id)
        except Exception as e:
            logger.error(f"Forward Error: {e}")

# ================= BACKGROUND TASKS =================
async def auto_cleanup_task():
    while True:
        await asyncio.sleep(86400)
        try:
            check_db_health()
            with db.cursor() as cursor:
                cursor.execute("DELETE FROM system_logs WHERE created_at < NOW() - INTERVAL '7 days';")
                cursor.execute("DELETE FROM spam WHERE last_message < %s;", (int(time.time()) - 86400,))
            log_event("AUTO_CLEANUP", "Old logs and spam data cleaned up successfully.")
        except Exception as e:
            logger.error(f"Auto cleanup error: {e}")

async def system_monitor_task():
    while True:
        await asyncio.sleep(3600)
        try:
            check_db_health()
            if not userbot.is_connected:
                await safe_send(ADMIN_ID, "🚨 **تنبيه نظام المراقبة:** الـ Userbot منفصل حالياً!")
        except Exception as e:
            logger.error(f"Monitoring Task Error: {e}")

# ================= WEB SERVER =================
async def health(request):
    return web.Response(text="Bot is running smoothly with all core features.")

async def start_web():
    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_get("/health", health)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", "10000"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"Web Server Started : {port}")

# ================= MAIN RUNNER =================
async def safe_start_client(client: Client, name: str):
    while True:
        try:
            await client.start()
            logger.info(f"{name} Started Successfully.")
            break
        except FloodWait as e:
            logger.warning(f"⚠️ Telegram FloodWait for {name}: Must wait {e.value} seconds.")
            await asyncio.sleep(e.value + 2)
        except Exception as e:
            logger.error(f"❌ Error starting {name}: {e}")
            raise e

async def safe_stop_client(client: Client, name: str):
    if getattr(client, "is_connected", False):
        try:
            await client.stop()
            logger.info(f"{name} Stopped.")
        except Exception as e:
            logger.warning(f"Error stopping {name}: {e}")

async def main():
    await start_web()
    await safe_start_client(userbot, "Userbot")
    await safe_start_client(bot, "Bot")

    asyncio.create_task(process_exchange_queue())
    asyncio.create_task(auto_cleanup_task())
    asyncio.create_task(system_monitor_task())
    asyncio.create_task(update_profile_every_minute(userbot))

    log_event("SYSTEM_START", "All system modules, tasks, and clients loaded successfully.")
    logger.info("🚀 All Advanced Features & Core Services Online.")
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
