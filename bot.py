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
    PeerIdInvalid
)

from pyrogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)

# ================= 1 & 21. LOGGING & CODE ORGANIZATION SETUP =================
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

# 13. QUEUE SYSTEM FOR REQUESTS
exchange_queue = asyncio.Queue()

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

# ================= 20. COLORED BUTTONS & BOT API DIRECT HELPER =================
async def send_colored_message(chat_id: int, text: str, reply_markup: dict = None, parse_mode: str = "Markdown"):
    """إرسال رسائل ودعم الأزرار الملونة بخصائص Bot API 7.4+ مباشرة"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)

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

def create_styled_button(text: str, url: str = None, callback_data: str = None):
    """دالة احتياطية لإنشاء أزرار Pyrogram القياسية عند الحاجة"""
    if url:
        return InlineKeyboardButton(text=text, url=url)
    return InlineKeyboardButton(text=text, callback_data=callback_data)

# ================= 16. DATABASE CONNECTION & AUTO-RECONNECT =================
def get_db_connection():
    """الاتصال بقاعدة البيانات مع حماية وإعادة محاولة تلقائية"""
    while True:
        try:
            conn = psycopg2.connect(
                DATABASE_URL,
                sslmode="require",
                cursor_factory=RealDictCursor
            )
            conn.autocommit = True
            return conn
        except Exception as e:
            logger.error(f"Database connection error: {e}. Retrying in 3 seconds...")
            time.sleep(3)

db = get_db_connection()
cursor = db.cursor()

def check_db_health():
    """16 & 19. التأكد من سلامة قاعدة البيانات وإعادة الاتصال عند انقطاعها"""
    global db, cursor
    try:
        cursor.execute("SELECT 1;")
    except Exception:
        logger.warning("Database connection lost. Reconnecting...")
        db = get_db_connection()
        cursor = db.cursor()

# ================= DATABASE TABLES INITIALIZATION =================
# ================= DATABASE TABLES INITIALIZATION =================
check_db_health()

# ⚠️ اختياري: إذا كنت تريد مسح الجداول القديمة وإعادة إنشائها من الصفر افتح التعليق عن السطرين القادمين:
# cursor.execute("DROP TABLE IF EXISTS spam CASCADE;")
# cursor.execute("DROP TABLE IF EXISTS users CASCADE;")

# 1. جدول الإعدادات الداخلية
cursor.execute("""
CREATE TABLE IF NOT EXISTS settings(
    key TEXT PRIMARY KEY,
    value TEXT
)
""")

# 2. جدول المستخدمين المحدث
cursor.execute("""
CREATE TABLE IF NOT EXISTS users(
    user_id BIGINT PRIMARY KEY,
    username TEXT,
    full_name TEXT,
    is_banned BOOLEAN DEFAULT FALSE,
    join_date TIMESTAMP DEFAULT NOW(),
    last_active TIMESTAMP DEFAULT NOW(),
    usage_count INT DEFAULT 0
)
""")

# 3. جدول القنوات المحدث
cursor.execute("""
CREATE TABLE IF NOT EXISTS channels(
    id SERIAL PRIMARY KEY,
    user_id BIGINT UNIQUE,
    channel TEXT,
    last_order_time TIMESTAMP DEFAULT NOW() - INTERVAL '12 hours',
    joined_at TIMESTAMP DEFAULT NOW()
)
""")

# 4. جدول مكافحة السبام المحدث
cursor.execute("""
CREATE TABLE IF NOT EXISTS spam(
    user_id BIGINT PRIMARY KEY,
    messages INTEGER DEFAULT 0,
    last_message BIGINT DEFAULT 0,
    temp_ban_until TIMESTAMP DEFAULT NULL
)
""")

# 5. جدول سجلات النظام
cursor.execute("""
CREATE TABLE IF NOT EXISTS system_logs(
    id SERIAL PRIMARY KEY,
    event_type TEXT,
    details TEXT,
    created_at TIMESTAMP DEFAULT NOW()
)
""")

# 6. جدول الإحصائيات والمقاييس
cursor.execute("""
CREATE TABLE IF NOT EXISTS metrics(
    key TEXT PRIMARY KEY,
    value_count BIGINT DEFAULT 0
)
""")

# ================= AUTOMATIC SCHEMA MIGRATIONS =================
# حماية إضافية: إضافة الأعمدة الجديدة تلقائياً في حال وجود جداول قديمة مخزنة مسبقاً
try:
    cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_active TIMESTAMP DEFAULT NOW();")
    cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS usage_count INT DEFAULT 0;")
    cursor.execute("ALTER TABLE channels ADD COLUMN IF NOT EXISTS last_order_time TIMESTAMP DEFAULT NOW() - INTERVAL '12 hours';")
    cursor.execute("ALTER TABLE spam ADD COLUMN IF NOT EXISTS temp_ban_until TIMESTAMP DEFAULT NULL;")
except Exception as e:
    logger.warning(f"Migration check skipped/passed: {e}")


# ================= 1. LOGGING & METRICS SYSTEM =================
def log_event(event_type: str, details: str):
    check_db_health()
    try:
        cursor.execute(
            "INSERT INTO system_logs (event_type, details) VALUES (%s, %s)",
            (event_type, details)
        )
    except Exception as e:
        logger.error(f"Failed to log event to DB: {e}")

def increment_metric(key: str, amount: int = 1):
    check_db_health()
    try:
        cursor.execute("""
        INSERT INTO metrics (key, value_count) VALUES (%s, %s)
        ON CONFLICT (key) DO UPDATE SET value_count = metrics.value_count + EXCLUDED.value_count;
        """, (key, amount))
    except Exception as e:
        logger.error(f"Failed to increment metric {key}: {e}")

def get_metric(key: str) -> int:
    check_db_health()
    try:
        cursor.execute("SELECT value_count FROM metrics WHERE key=%s", (key,))
        row = cursor.fetchone()
        return row["value_count"] if row else 0
    except Exception:
        return 0

# ================= 2. INTERNAL SETTINGS MANAGER =================
def get_setting(key: str, default: str = "true"):
    check_db_health()
    cursor.execute("SELECT value FROM settings WHERE key=%s", (key,))
    row = cursor.fetchone()
    return row["value"] if row else default

def set_setting(key: str, value: str):
    check_db_health()
    cursor.execute(
        """
        INSERT INTO settings(key,value)
        VALUES(%s,%s)
        ON CONFLICT(key)
        DO UPDATE SET value=EXCLUDED.value
        """,
        (key, str(value))
    )
    log_event("SETTINGS_UPDATE", f"Setting '{key}' changed to '{value}'")

# ================= DATABASE FUNCTIONS =================
def add_or_update_user(user_id: int, username: str, full_name: str):
    check_db_health()
    cursor.execute("SELECT user_id FROM users WHERE user_id=%s", (user_id,))
    exists = cursor.fetchone()

    cursor.execute(
        """
        INSERT INTO users (user_id, username, full_name, last_active, usage_count)
        VALUES (%s, %s, %s, NOW(), 1)
        ON CONFLICT (user_id) 
        DO UPDATE SET 
            username=EXCLUDED.username, 
            full_name=EXCLUDED.full_name,
            last_active=NOW(),
            usage_count=users.usage_count + 1
        """,
        (user_id, username, full_name)
    )
    return exists is None

def is_banned(user_id: int):
    check_db_health()
    cursor.execute("SELECT is_banned FROM users WHERE user_id=%s", (user_id,))
    row = cursor.fetchone()
    return row["is_banned"] if row else False

def set_ban_status(user_id: int, banned: bool):
    check_db_health()
    cursor.execute(
        "UPDATE users SET is_banned=%s WHERE user_id=%s",
        (banned, user_id)
    )
    log_event("USER_BAN_TOGGLE", f"User {user_id} ban set to {banned}")

def get_channel_data(user_id: int):
    check_db_health()
    cursor.execute("SELECT channel, last_order_time FROM channels WHERE user_id=%s", (user_id,))
    return cursor.fetchone()

def update_channel_order(user_id: int, channel: str):
    check_db_health()
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
    check_db_health()
    cursor.execute("DELETE FROM channels WHERE user_id=%s", (user_id,))
    log_event("CHANNEL_REMOVE", f"Channel removed for user {user_id}")

def get_channel(user_id: int):
    check_db_health()
    cursor.execute("SELECT channel FROM channels WHERE user_id=%s", (user_id,))
    row = cursor.fetchone()
    return row["channel"] if row else None

def get_stats():
    check_db_health()
    cursor.execute("SELECT COUNT(*) as total_users FROM users;")
    users_count = cursor.fetchone()["total_users"]
    cursor.execute("SELECT COUNT(*) as total_channels FROM channels;")
    channels_count = cursor.fetchone()["total_channels"]
    return users_count, channels_count

def get_all_users():
    check_db_health()
    cursor.execute("SELECT user_id FROM users WHERE is_banned=FALSE;")
    return [row["user_id"] for row in cursor.fetchall()]

# ================= 12. ENHANCED ANTI SPAM SYSTEM =================
def update_spam(user_id: int):
    check_db_health()
    now_ts = int(time.time())
    now_dt = datetime.now()

    cursor.execute("SELECT messages, last_message, temp_ban_until FROM spam WHERE user_id=%s", (user_id,))
    row = cursor.fetchone()

    # إذا كان محظوراً مؤقتاً حالياً
    if row and row["temp_ban_until"] and row["temp_ban_until"] > now_dt:
        return -2  # رمز خاص: "محظور حالياً" (حتى لا نكرر إرسال الرسالة)

    # إذا لم يكن موجوداً
    if row is None:
        cursor.execute(
            "INSERT INTO spam (user_id, messages, last_message) VALUES (%s, 1, %s)",
            (user_id, now_ts)
        )
        return 1

    # إعادة إعادة العداد إذا مرت أكثر من 10 ثوانٍ على آخر رسالة
    if now_ts - row["last_message"] > 10:
        cursor.execute(
            "UPDATE spam SET messages=1, last_message=%s WHERE user_id=%s",
            (now_ts, user_id)
        )
        return 1

    count = row["messages"] + 1

    # إذا تجاوز الحد المسموح (8 رسائل في أقل من 10 ثوانٍ) -> تفعيل الحظر لأول مرة
    if count >= 8:
        ban_until = now_dt + timedelta(minutes=5)
        cursor.execute(
            "UPDATE spam SET messages=%s, last_message=%s, temp_ban_until=%s WHERE user_id=%s",
            (count, now_ts, ban_until, user_id)
        )
        log_event("SPAM_TEMP_BAN", f"User {user_id} temporarily banned for spam.")
        return -1  # رمز خاص: "تم حظره للتو" (لإرسال التنبيه مرة واحدة فقط)

    cursor.execute(
        "UPDATE spam SET messages=%s, last_message=%s WHERE user_id=%s",
        (count, now_ts, user_id)
    )
    return count


async def anti_spam(message: Message):
    if not message or not message.from_user:
        return True

    # 1. استثناء الأدمن تماماً من فحص السبام
    if message.from_user.id == ADMIN_ID:
        return True

    if get_setting("anti_spam", "true") == "false":
        return True

    user_id = message.from_user.id
    status = update_spam(user_id)

    # 2. إذا كان محظوراً بالفعل مسبقاً -> نتجاهل الرسالة تماماً ولا نرسل شيئاً لمنع التكرار
    if status == -2:
        return False

    # 3. إذا تم حظره في هذه اللحظة فقط -> نرسل التحذير مرة واحدة فقط
    if status == -1:
        await send_colored_message(
            chat_id=message.chat.id,
            text="⛔ **تم حظرك مؤقتاً لمدة 5 دقائق بسبب إرسال الرسائل بكثرة (Spam).**"
        )
        return False

    return True

# ================= HUMAN ACTIONS & EMOJI REACTIONS =================
async def simulate_human_action(chat_id: int, duration: float = None):
    try:
        chosen_action = random.choice(HUMAN_ACTIONS)
        await bot.send_chat_action(chat_id=chat_id, action=chosen_action)
        wait_time = duration if duration else random.uniform(1.0, 2.0)
        await asyncio.sleep(wait_time)
    except Exception as e:
        logger.debug(f"Chat action error: {e}")

async def add_random_reaction(chat_id: int, message_id: int):
    try:
        emoji = random.choice(REACTION_EMOJIS)
        async with ClientSession() as session:
            await session.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/setMessageReaction",
                data={
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "reaction": json.dumps([{"type": "emoji", "emoji": emoji}])
                }
            )
    except Exception as e:
        logger.exception(e)

# ================= 14. RETRY & ROBUST SMM API CALLS =================
async def order_smm_services(target_link: str, quantity: int = 10, retries: int = 3):
    if not SMM_API_KEY or not SMM_API_URL:
        logger.warning("SMM_API_KEY or SMM_API_URL is not configured.")
        log_event("API_ERROR", "SMM API configuration missing")
        increment_metric("api_failed")
        return False, "إعدادات الـ API غير مكتملة"

    payload = {
        'key': SMM_API_KEY,
        'action': 'add',
        'service': SMM_SERVICE_ID,
        'link': target_link,
        'quantity': str(quantity)
    }

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    for attempt in range(1, retries + 1):
        try:
            async with ClientSession(headers=headers) as session:
                async with session.post(SMM_API_URL, data=payload, timeout=10) as resp:
                    data = await resp.json(content_type=None)
                    logger.info(f"SMM API Response (Attempt {attempt}): {data}")
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
            logger.error(f"SMM API Error (Attempt {attempt}): {e}")
            if attempt == retries:
                log_event("API_EXCEPTION", f"Link: {target_link} | Exception: {e}")
                increment_metric("api_failed")
                return False, str(e)
        await asyncio.sleep(2 * attempt)

# ================= 4. SCHEDULER TASK & NOTIFICATIONS =================
async def schedule_12h_notification(user_id: int, delay_seconds: int = 43200):
    await asyncio.sleep(delay_seconds)
    msg_text = (
        "🔔 **انقضت 12 ساعة!**\n\n"
        "✨ حان وقت التبادل الجديد! يمكنك الآن إرسال رابط قناتك مجدداً للحصول على دفعة أعضاء جديدة لقناتك 🚀."
    )
    await safe_send(user_id, msg_text)
    log_event("SCHEDULED_NOTIF", f"12h Notification sent to user {user_id}")

# ================= HELPERS =================
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

# ================= 17. ENHANCED USERBOT JOINING =================
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
        log_event("USERBOT_JOIN_FAILED", f"Invalid channel username: {channel}")
        return False, "💔 رابط القناة غير صالح أو غير موجود."
    except FloodWait as e:
        logger.warning(f"Userbot FloodWait: {e.value}s while joining {channel}")
        await asyncio.sleep(e.value)
        return await join_channel(channel)
    except Exception as e:
        log_event("USERBOT_JOIN_EXCEPTION", f"Channel {channel}: {e}")
        return False, f"❌ تعذر الانضمام: {str(e)}"

async def leave_channel(channel):
    try:
        await userbot.leave_chat(channel)
        log_event("USERBOT_LEAVE", f"Left channel {channel}")
        return True
    except FloodWait as e:
        await asyncio.sleep(e.value)
        return await leave_channel(channel)
    except Exception:
        return False

# ================= 6 & 20. ADMIN PANEL & COLORED KEYBOARDS =================
def get_admin_main_keyboard():
    """لوحة تحكم احترافية مقسمة ومصممة بأزرار ملونة موحدة"""
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
                {"text": "💾 النسخ الاحتياطي", "callback_data": "admin_backup", "style": "success"}
            ],
            [
                {"text": "📜 سجلات النظام (Logs)", "callback_data": "admin_logs", "style": "danger"},
                {"text": "❌ إغلاق اللوحة", "callback_data": "admin_close", "style": "danger"}
            ]
        ]
    }

@bot.on_message(filters.private & filters.command("admin"))
async def admin_panel_cmd(client: Client, message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    await add_random_reaction(message.chat.id, message.id)
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

    # 5 & 6. ADVANCED STATS
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
            f"🚀 **طلب الـ API الناجحة:** `{api_succ}`\n"
            f"❌ **طلبات الـ API الفاشلة:** `{api_fail}`"
        )
        buttons = {"inline_keyboard": [[{"text": "🔙 العودة للوحة الرئيسية", "callback_data": "admin_home", "style": "primary"}]]}
        await query.answer()
        await send_colored_message(query.message.chat.id, stats_text, reply_markup=buttons)

    # 2. INTERNAL SETTINGS TOGGLE
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
                [{"text": f"تغيير مكافحة السبام", "callback_data": "toggle_setting_anti_spam", "style": "primary"}],
                [{"text": f"تغيير وضع التبادل", "callback_data": "toggle_setting_exchange_enabled", "style": "primary"}],
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
        # Refresh Settings View
        return await admin_callbacks(client, query)

    # 3. BACKUP SYSTEM
    elif data == "admin_backup":
        check_db_health()
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

    # 1. LOGS SYSTEM
    elif data == "admin_logs":
        check_db_health()
        cursor.execute("SELECT event_type, details, created_at FROM system_logs ORDER BY id DESC LIMIT 10;")
        logs_rows = cursor.fetchall()
        
        logs_text = "📜 **آخر 10 أحداث مسجلة في النظام:**\n\n"
        for l in logs_rows:
            logs_text += f"🔹 [{l['created_at'].strftime('%H:%M:%S')}] **{l['event_type']}**: {l['details']}\n"

        buttons = {"inline_keyboard": [[{"text": "🔙 العودة", "callback_data": "admin_home", "style": "primary"}]]}
        await query.answer()
        await send_colored_message(query.message.chat.id, logs_text, reply_markup=buttons)

    # 9. BROADCAST SYSTEM
    elif data == "admin_broadcast_menu":
        ADMIN_STATES[ADMIN_ID] = "WAITING_FOR_BROADCAST"
        await query.answer()
        buttons = {"inline_keyboard": [[{"text": "إلغاء الإذاعة ❌", "callback_data": "admin_home", "style": "danger"}]]}
        await send_colored_message(
            query.message.chat.id,
            "📢 **نظام البث الاحترافي:**\n\nأرسل الآن (نص، صورة، فيديو، أو ملف) ليتم بثه لجميع المستخدمين، أو أرسل /cancel للإلغاء.",
            reply_markup=buttons
        )

    # 8. USERS MANAGEMENT MENU
    elif data == "admin_users_menu":
        await query.answer()
        buttons = {"inline_keyboard": [[{"text": "🔙 العودة للوحة", "callback_data": "admin_home", "style": "primary"}]]}
        await send_colored_message(
            query.message.chat.id,
            "👥 **إدارة المستخدمين:**\n\n"
            "▫️ لحظر مستخدم: `/ban USER_ID`\n"
            "▫️ لفك الحظر: `/unban USER_ID`\n"
            "▫️ للبحث عن بيانات مستخدم: `/user USER_ID`",
            reply_markup=buttons
        )

    # 7. CHANNELS MANAGEMENT MENU
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

# ================= 8. ADMIN COMMANDS FOR USER & CHANNEL MANAGEMENT =================
@bot.on_message(filters.private & filters.command("user"))
async def get_user_info_cmd(client: Client, message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        target_id = int(message.text.split()[1])
        check_db_health()
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

@bot.on_message(filters.private & filters.command("ban"))
async def ban_user_cmd(client: Client, message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    await add_random_reaction(message.chat.id, message.id)
    await simulate_human_action(message.chat.id)
    try:
        target_id = int(message.text.split()[1])
        set_ban_status(target_id, True)
        await send_colored_message(message.chat.id, f"✅ تم حظر المستخدم `{target_id}` بنجاح.")
    except Exception:
        await send_colored_message(message.chat.id, "⚠️ استخدام خاطئ. الصيغة الصحيحة: `/ban 123456789`")

@bot.on_message(filters.private & filters.command("unban"))
async def unban_user_cmd(client: Client, message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    await add_random_reaction(message.chat.id, message.id)
    await simulate_human_action(message.chat.id)
    try:
        target_id = int(message.text.split()[1])
        set_ban_status(target_id, False)
        await send_colored_message(message.chat.id, f"✅ تم فك حظر المستخدم `{target_id}` بنجاح.")
    except Exception:
        await send_colored_message(message.chat.id, "⚠️ استخدام خاطئ. الصيغة الصحيحة: `/unban 123456789`")

@bot.on_message(filters.private & filters.command("cancel"))
async def cancel_admin_state(client: Client, message: Message):
    if message.from_user.id == ADMIN_ID and ADMIN_ID in ADMIN_STATES:
        await add_random_reaction(message.chat.id, message.id)
        await simulate_human_action(message.chat.id)
        ADMIN_STATES.pop(ADMIN_ID, None)
        await send_colored_message(message.chat.id, "✅ تم إلغاء العملية والعودة للوضع الطبيعي.")

# ================= START COMMAND & NEW USER NOTIFICATION =================
@bot.on_message(filters.private & filters.command("start"))
async def start_handler(client: Client, message: Message):
    user_id = message.from_user.id

    await add_random_reaction(message.chat.id, message.id)

    if is_banned(user_id) or not await anti_spam(message):
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
            f"👤 **عضو جديد انضم للبوت!**\n\n"
            f"▫️ **الاسم:** {user_mention}\n"
            f"▫️ **الآيدي:** `{user_id}`\n"
            f"▫️ **اليوزر:** @{username if username else 'بدون يوزر'}\n"
            f"▫️ **العدد الكلي:** `{total_users_count}`"
        )
        await safe_send(ADMIN_ID, new_user_text)

    await simulate_human_action(message.chat.id)

    start_buttons = {
        "inline_keyboard": [
            [{"text": "📢 قناة الدعم والتبادل", "url": f"https://t.me/qd3qd", "style": "primary"}]
        ]
    }

    await send_colored_message(
        chat_id=message.chat.id,
        text=f"أهلاً بك {message.from_user.first_name} 🌹\n\n"
             "✨ **أرسل الآن رابط قناتك بالشكل التالي ؛** لبدء التبادل التلقائي:\n"
             "▫️ `@KKEK2` \n"
             "▫️ `https://t.me/KKEK2`\n\n",
        reply_markup=start_buttons
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
            await send_colored_message(message.chat.id, "✅ تم إرسال ردك للمستخدم بنجاح.")
        except Exception as e:
            await send_colored_message(message.chat.id, f"❌ تعذر إرسال الرد للمستخدم: {e}")
    else:
        await send_colored_message(message.chat.id, "⚠️ يرجى الرد على رسالة موجهة مباشرة من مستخدم.")

# ================= 13. WORKER & QUEUE FOR EXCHANGE PROCESS =================
async def process_exchange_queue():
    """معالج الطوابير لتنفيذ طلبات التبادل بالتتابع دون كسر السيرفر"""
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
    wait_msg = await bot.send_message(message.chat.id, "⏳ جارٍ الانضمام لقناتك وتأكيد التبادل...")
    
    ok, result = await join_channel(text)

    if not ok:
        await simulate_human_action(message.chat.id)
        # 11. SMART ERROR HANDLER WITH SOLUTIONS
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
        cursor.execute("UPDATE channels SET channel=%s WHERE user_id=%s", (formatted_channel, user_id))

    increment_metric("exchanges")
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")

    userbot_me = await userbot.get_me()
    userbot_link = f"https://t.me/{userbot_me.username}" if userbot_me.username else f"tg://user?id={userbot_me.id}"
    
    exchange_buttons = {
        "inline_keyboard": [
            [{"text": "👤 (Userbot)", "url": userbot_link, "style": "primary"}],
            [{"text": "📢 قناتك الجميله", "url": formatted_channel, "style": "success"}]
        ]
    }

    await simulate_human_action(message.chat.id)
    await wait_msg.delete()

    await send_colored_message(
        chat_id=message.chat.id,
        text=f"🎉 **تم التبادل المباشر بنجاح!**\n\n"
             f"📌 **القناة:** {title}\n"
             f"⏰ **الوقت:** `{now_str}`\n"
             f"✅ انضم الحساب المساعد إلى قناتك فوراً وسيتم بدء دعم الأعضاء لقناتك.\n\n"
             f"👇 يمكنك معاينة التفاصيل أدناه:",
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

# ================= MAIN ROUTER FOR MESSAGES & CHANNELS =================
@bot.on_message(filters.private)
async def main_message_router(client: Client, message: Message):
    user_id = message.from_user.id

    await add_random_reaction(message.chat.id, message.id)

    # 9. PRO BROADCAST ENGINE
    if user_id == ADMIN_ID and user_id in ADMIN_STATES:
        state = ADMIN_STATES[user_id]

        if state == "WAITING_FOR_BROADCAST":
            ADMIN_STATES.pop(ADMIN_ID, None)
            all_u = get_all_users()
            sent, failed = 0, 0
            await simulate_human_action(message.chat.id)
            msg = await send_colored_message(message.chat.id, f"⏳ جارٍ الإذاعة لـ {len(all_u)} مستخدم...")
            
            for u in all_u:
                try:
                    await message.copy(u)
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

    text = message.text.strip() if message.text else ""

    # فحص رابط القناة وإضافته للطابور
    if text and any(text.startswith(prefix) for prefix in ["@", "https://t.me/", "http://t.me/", "t.me/"]):
        if get_setting("exchange_enabled", "true") == "false":
            return await send_colored_message(message.chat.id, "⚠️ نظام التبادل متوقف حالياً للصيانة.")

        await exchange_queue.put((client, message, text))
        return

    # توجيه الرسائل العادية للمالك
    if user_id != ADMIN_ID:
        try:
            await message.forward(ADMIN_ID)
            await simulate_human_action(message.chat.id)
            await send_colored_message(message.chat.id, "📨 تم توجيه رسالتك إلى مالك البوت، وسيقوم بالرد عليك في أقرب وقت.")
        except Exception as e:
            logger.error(f"Forward Error: {e}")

# ================= 15. AUTO CLEANUP TASK =================
async def auto_cleanup_task():
    """حذف البيانات والسجلات القديمة تلقائياً كل 24 ساعة"""
    while True:
        await asyncio.sleep(86400)
        try:
            check_db_health()
            cursor.execute("DELETE FROM system_logs WHERE created_at < NOW() - INTERVAL '7 days';")
            cursor.execute("DELETE FROM spam WHERE last_message < %s;", (int(time.time()) - 86400,))
            log_event("AUTO_CLEANUP", "Old logs and spam data cleaned up successfully.")
        except Exception as e:
            logger.error(f"Auto cleanup error: {e}")

# ================= 19. SYSTEM MONITORING TASK =================
async def system_monitor_task():
    """مراقبة النظام وإرسال تنبيه للمالك عند المشاكل"""
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
    return web.Response(text="Bot is running smoothly with 21 new features.")

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
    
    # 13, 15, 19. START BACKGROUND WORKERS
    asyncio.create_task(process_exchange_queue())
    asyncio.create_task(auto_cleanup_task())
    asyncio.create_task(system_monitor_task())

    log_event("SYSTEM_START", "All system modules, tasks, and clients loaded successfully.")
    logger.info("🚀 All 21 Advanced Features & Core Services Online.")
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
