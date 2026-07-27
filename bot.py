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
    UserIsBlocked,
    InputUserDeactivated,
    PeerIdInvalid,
    UsernameInvalid,
    UsernameNotOccupied,
    UserAlreadyParticipant
)

from pyrogram.types import (
    Message,
    CallbackQuery,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
BOT_TOKEN = os.environ["BOT_TOKEN"]
USERBOT_SESSION = os.environ["USERBOT_SESSION"]
DATABASE_URL = os.environ["DATABASE_URL"]
ADMIN_ID = int(os.environ["ADMIN_ID"])

bot = Client(
    "Bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

userbot = Client(
    "Userbot",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=USERBOT_SESSION
)

db = psycopg2.connect(
    DATABASE_URL,
    sslmode="require",
    cursor_factory=RealDictCursor
)

db.autocommit = True

cursor = db.cursor()

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
user_id BIGINT,
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
CREATE TABLE IF NOT EXISTS broadcasts(
id SERIAL PRIMARY KEY,
text TEXT,
created_at TIMESTAMP DEFAULT NOW()
)
""")

cursor.execute("""
INSERT INTO settings(key,value)
VALUES('main_channel','https://t.me/YourChannel')
ON CONFLICT(key)
DO NOTHING
""")

cursor.execute("""
INSERT INTO settings(key,value)
VALUES('fake_offset','0')
ON CONFLICT(key)
DO NOTHING
""")

admin_state = {}
spam_cache = {}

# ================= DATABASE FUNCTIONS =================

def get_setting(key: str):
    cursor.execute(
        "SELECT value FROM settings WHERE key=%s",
        (key,)
    )
    row = cursor.fetchone()
    if row:
        return row["value"]
    return None


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


def add_user(user_id: int, username: str, full_name: str):
    cursor.execute(
        "SELECT user_id FROM users WHERE user_id=%s",
        (user_id,)
    )

    if cursor.fetchone():
        return False

    cursor.execute(
        """
        INSERT INTO users
        (
            user_id,
            username,
            full_name
        )
        VALUES
        (
            %s,
            %s,
            %s
        )
        """,
        (
            user_id,
            username,
            full_name
        )
    )

    return True


def update_user(user_id: int, username: str, full_name: str):
    cursor.execute(
        """
        UPDATE users
        SET
        username=%s,
        full_name=%s
        WHERE user_id=%s
        """,
        (
            username,
            full_name,
            user_id
        )
    )


def user_exists(user_id: int):
    cursor.execute(
        "SELECT user_id FROM users WHERE user_id=%s",
        (user_id,)
    )

    return cursor.fetchone() is not None


def get_user(user_id: int):
    cursor.execute(
        "SELECT * FROM users WHERE user_id=%s",
        (user_id,)
    )

    return cursor.fetchone()


def get_all_users():
    cursor.execute(
        """
        SELECT *
        FROM users
        ORDER BY join_date ASC
        """
    )

    return cursor.fetchall()


def get_all_user_ids():
    cursor.execute(
        """
        SELECT user_id
        FROM users
        WHERE is_banned=FALSE
        """
    )

    rows = cursor.fetchall()

    return [x["user_id"] for x in rows]


def total_users():
    cursor.execute(
        "SELECT COUNT(*) AS c FROM users"
    )

    row = cursor.fetchone()

    return row["c"]


def fake_counter():
    value = get_setting("fake_offset")

    if value is None:
        return 0

    return int(value)


def total_counter():
    return total_users() + fake_counter()


def ban_user(user_id: int):
    cursor.execute(
        """
        UPDATE users
        SET is_banned=TRUE
        WHERE user_id=%s
        """,
        (user_id,)
    )


def unban_user(user_id: int):
    cursor.execute(
        """
        UPDATE users
        SET is_banned=FALSE
        WHERE user_id=%s
        """,
        (user_id,)
    )


def is_banned(user_id: int):
    cursor.execute(
        """
        SELECT is_banned
        FROM users
        WHERE user_id=%s
        """,
        (user_id,)
    )

    row = cursor.fetchone()

    if row is None:
        return False

    return row["is_banned"]


def save_channel(user_id: int, channel: str):
    cursor.execute(
        """
        DELETE FROM channels
        WHERE user_id=%s
        """,
        (user_id,)
    )

    cursor.execute(
        """
        INSERT INTO channels
        (
            user_id,
            channel
        )
        VALUES
        (
            %s,
            %s
        )
        """,
        (
            user_id,
            channel
        )
    )


def remove_channel(user_id: int):
    cursor.execute(
        """
        DELETE FROM channels
        WHERE user_id=%s
        """,
        (user_id,)
    )


def get_channel(user_id: int):
    cursor.execute(
        """
        SELECT channel
        FROM channels
        WHERE user_id=%s
        """,
        (user_id,)
    )

    row = cursor.fetchone()

    if row:
        return row["channel"]

    return None


def total_channels():
    cursor.execute(
        """
        SELECT COUNT(*) AS c
        FROM channels
        """
    )

    row = cursor.fetchone()

    return row["c"]


def log_broadcast(text: str):
    cursor.execute(
        """
        INSERT INTO broadcasts(text)
        VALUES(%s)
        """,
        (text,)
    )


def update_spam(user_id: int):
    now = int(time.time())

    cursor.execute(
        """
        SELECT *
        FROM spam
        WHERE user_id=%s
        """,
        (user_id,)
    )

    row = cursor.fetchone()

    if row is None:

        cursor.execute(
            """
            INSERT INTO spam
            (
                user_id,
                messages,
                last_message
            )
            VALUES
            (
                %s,
                1,
                %s
            )
            """,
            (
                user_id,
                now
            )
        )

        return 1

    if now - row["last_message"] > 10:

        cursor.execute(
            """
            UPDATE spam
            SET
            messages=1,
            last_message=%s
            WHERE user_id=%s
            """,
            (
                now,
                user_id
            )
        )

        return 1

    count = row["messages"] + 1

    cursor.execute(
        """
        UPDATE spam
        SET
        messages=%s,
        last_message=%s
        WHERE user_id=%s
        """,
        (
            count,
            now,
            user_id
        )
    )

    return count

# ================= ANTI SPAM =================

SPAM_LIMIT = 6
SPAM_WINDOW = 10

async def anti_spam(message: Message):

    user_id = message.from_user.id

    count = update_spam(user_id)

    if count >= SPAM_LIMIT:

        try:
            await message.reply_text(
                "⚠️ يرجى التوقف عن إرسال الرسائل بسرعة والمحاولة بعد قليل."
            )
        except Exception:
            pass

        return False

    return True


# ================= KEYBOARDS =================

main_keyboard = ReplyKeyboardMarkup(
    [
        [
            KeyboardButton("🎁 الخدمات المجانية")
        ],
        [
            KeyboardButton("🛒 شراء خدمات")
        ],
        [
            KeyboardButton("💰 رصيد المحاولات"),
            KeyboardButton("📋 سجل الطلبات")
        ],
        [
            KeyboardButton("👥 دعوة صديق")
        ]
    ],
    resize_keyboard=True
)


def admin_keyboard():

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "📢 الإذاعة",
                    callback_data="broadcast"
                ),
                InlineKeyboardButton(
                    "📊 الإحصائيات",
                    callback_data="stats"
                )
            ],
            [
                InlineKeyboardButton(
                    "🚫 حظر",
                    callback_data="ban"
                ),
                InlineKeyboardButton(
                    "✅ فك الحظر",
                    callback_data="unban"
                )
            ],
            [
                InlineKeyboardButton(
                    "📢 تغيير القناة",
                    callback_data="main_channel"
                ),
                InlineKeyboardButton(
                    "🔢 العداد الوهمي",
                    callback_data="fake_counter"
                )
            ]
        ]
    )


# ================= HELPERS =================

async def safe_send(chat_id, text, **kwargs):

    try:

        return await bot.send_message(
            chat_id,
            text,
            **kwargs
        )

    except FloodWait as e:

        await asyncio.sleep(e.value)

        return await safe_send(
            chat_id,
            text,
            **kwargs
        )

    except (
        UserIsBlocked,
        InputUserDeactivated,
        PeerIdInvalid
    ):

        return None

    except Exception as e:

        logging.exception(e)

        return None


async def safe_copy(chat_id, from_chat_id, message_id):

    try:

        return await bot.copy_message(
            chat_id,
            from_chat_id,
            message_id
        )

    except FloodWait as e:

        await asyncio.sleep(e.value)

        return await safe_copy(
            chat_id,
            from_chat_id,
            message_id
        )

    except (
        UserIsBlocked,
        InputUserDeactivated,
        PeerIdInvalid
    ):

        return None

    except Exception as e:

        logging.exception(e)

        return None


async def join_channel(channel):

    try:

        chat = await userbot.join_chat(channel)

        return True, chat

    except UserAlreadyParticipant:

        chat = await userbot.get_chat(channel)

        return True, chat

    except (
        UsernameInvalid,
        UsernameNotOccupied
    ):

        return False, "💔الرابط غير صالح."

    except FloodWait as e:

        await asyncio.sleep(e.value)

        return await join_channel(channel)

    except Exception as e:

        return False, str(e)


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

    if not channel:

        # ================= START =================

@bot.on_message(filters.private & filters.command("start"))
async def start_handler(client: Client, message: Message):

    user_id = message.from_user.id

    if is_banned(user_id):

        return await message.reply_text(
            "🚫 تم حظرك من استخدام البوت."
        )

    if not await anti_spam(message):
        return

    username = message.from_user.username or ""

    full_name = message.from_user.first_name

    if message.from_user.last_name:
        full_name += f" {message.from_user.last_name}"

    if not user_exists(user_id):

        add_user(
            user_id,
            username,
            full_name
        )

        try:

            await safe_send(
                ADMIN_ID,
                f"""
👤 مستخدم جديد

الاسم :
{full_name}

المعرف :
@{username}

الآيدي :
{user_id}

إجمالي المستخدمين :
{total_counter()}
"""
            )

        except Exception:
            pass

    else:

        update_user(
            user_id,
            username,
            full_name
        )

    if not await is_subscribed(user_id):

        channel = get_setting("main_channel")

        kb = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "📢 الاشتراك",
                        url=channel
                    )
                ],
                [
                    InlineKeyboardButton(
                        "✅ تحقق",
                        callback_data="check_join"
                    )
                ]
            ]
        )

        return await message.reply_text(
            "يجب الاشتراك في القناة أولاً.",
            reply_markup=kb,
            disable_web_page_preview=True
        )

    await client.send_chat_action(
        message.chat.id,
        ChatAction.TYPING
    )

    await asyncio.sleep(1)

    await message.reply_text(
        f"""أهلاً بك {message.from_user.first_name} 🌹

يمكنك الآن استخدام جميع خدمات البوت.

اختر الخدمة المطلوبة من القائمة.""",
        reply_markup=main_keyboard
    )


@bot.on_callback_query(filters.regex("^check_join$"))
async def check_join_callback(
    client: Client,
    query: CallbackQuery
):

    if await is_subscribed(query.from_user.id):

        await query.answer(
            "تم التحقق بنجاح ✅",
            show_alert=True
        )

        await query.message.edit_text(
            "✅ تم التحقق من الاشتراك.\n\nأرسل /start للمتابعة."
        )

    else:

        await query.answer(
            "لم تشترك بعد.",
            show_alert=True
        )

        # ================= ADMIN =================

@bot.on_message(filters.private & filters.command("admin"))
async def admin_panel(client: Client, message: Message):

    if message.from_user.id != ADMIN_ID:
        return

    await client.send_chat_action(
        message.chat.id,
        ChatAction.TYPING
    )

    await asyncio.sleep(1)

    await message.reply_text(
        "⚙️ لوحة تحكم الأدمن",
        reply_markup=admin_keyboard()
    )


@bot.on_callback_query(filters.regex("^stats$"))
async def stats_callback(
    client: Client,
    query: CallbackQuery
):

    if query.from_user.id != ADMIN_ID:
        return await query.answer(
            "غير مصرح.",
            show_alert=True
        )

    text = f"""
📊 الإحصائيات

👤 المستخدمون :
{total_users()}

➕ العداد الوهمي :
{fake_counter()}

📈 الإجمالي :
{total_counter()}

📢 القنوات :
{total_channels()}
"""

    await query.answer()

    await query.message.edit_text(
        text,
        reply_markup=admin_keyboard()
    )


@bot.on_callback_query(filters.regex("^broadcast$"))
async def broadcast_callback(
    client: Client,
    query: CallbackQuery
):

    if query.from_user.id != ADMIN_ID:
        return

    admin_state[ADMIN_ID] = "broadcast"

    await query.answer()

    await query.message.reply_text(
        "📢 أرسل الرسالة المراد إذاعتها."
    )


@bot.on_callback_query(filters.regex("^ban$"))
async def ban_callback(
    client: Client,
    query: CallbackQuery
):

    if query.from_user.id != ADMIN_ID:
        return

    admin_state[ADMIN_ID] = "ban"

    await query.answer()

    await query.message.reply_text(
        "أرسل ID المستخدم لحظره."
    )


@bot.on_callback_query(filters.regex("^unban$"))
async def unban_callback(
    client: Client,
    query: CallbackQuery
):

    if query.from_user.id != ADMIN_ID:
        return

    admin_state[ADMIN_ID] = "unban"

    await query.answer()

    await query.message.reply_text(
        "أرسل ID المستخدم لفك الحظر."
    )


@bot.on_callback_query(filters.regex("^main_channel$"))
async def channel_callback(
    client: Client,
    query: CallbackQuery
):

    if query.from_user.id != ADMIN_ID:
        return

    admin_state[ADMIN_ID] = "main_channel"

    await query.answer()

    await query.message.reply_text(
        "أرسل رابط القناة الرئيسية الجديد."
    )


@bot.on_callback_query(filters.regex("^fake_counter$"))
async def fake_counter_callback(
    client: Client,
    query: CallbackQuery
):

    if query.from_user.id != ADMIN_ID:
        return

    admin_state[ADMIN_ID] = "fake_counter"

    await query.answer()

    await query.message.reply_text(
        "أرسل قيمة العداد الوهمي."
    )

    

        return True

    username = channel.replace(
        "https://t.me/",
        ""
    ).replace(
        "@",
        ""
    )

    try:

        member = await bot.get_chat_member(
            username,
            user_id
        )

        if member.status in (
            ChatMemberStatus.MEMBER,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER
        ):
            return True

    except Exception:
        pass

    return False
# ================= ADMIN STATES =================

@bot.on_message(filters.private & ~filters.command(["start", "admin"]))
async def admin_states_handler(client: Client, message: Message):

    user_id = message.from_user.id

    if user_id != ADMIN_ID:
        return

    if user_id not in admin_state:
        return

    state = admin_state.pop(user_id)

    # ================= BROADCAST =================

    if state == "broadcast":

        users = get_all_user_ids()

        success = 0
        failed = 0

        wait = await message.reply_text(
            "⏳ جاري إرسال الإذاعة..."
        )

        log_broadcast(
            message.text or "[MEDIA]"
        )

        for target in users:

            try:

                await safe_copy(
                    target,
                    message.chat.id,
                    message.id
                )

                success += 1

                await asyncio.sleep(0.05)

            except Exception:

                failed += 1

        await wait.edit_text(
            f"""
✅ انتهت الإذاعة

🟢 نجح الإرسال:
{success}

🔴 فشل الإرسال:
{failed}
"""
        )

        return

    # ================= BAN =================

    if state == "ban":

        try:

            target = int(message.text)

        except Exception:

            return await message.reply_text(
                "ID غير صحيح."
            )

        if not user_exists(target):

            return await message.reply_text(
                "المستخدم غير موجود."
            )

        ban_user(target)

        await message.reply_text(
            "✅ تم الحظر."
        )

        await safe_send(
            target,
            "🚫 تم حظرك من استخدام البوت."
        )

        return

    # ================= UNBAN =================

    if state == "unban":

        try:

            target = int(message.text)

        except Exception:

            return await message.reply_text(
                "ID غير صحيح."
            )

        if not user_exists(target):

            return await message.reply_text(
                "المستخدم غير موجود."
            )

        unban_user(target)

        await message.reply_text(
            "✅ تم فك الحظر."
        )

        await safe_send(
            target,
            "✅ تم فك الحظر ويمكنك استخدام البوت مرة أخرى."
        )

        return

    # ================= MAIN CHANNEL =================

    if state == "main_channel":

        channel = message.text.strip()

        set_setting(
            "main_channel",
            channel
        )

        await message.reply_text(
            f"✅ تم تغيير القناة الرئيسية إلى:\n{channel}"
        )

        return

    # ================= FAKE COUNTER =================

    if state == "fake_counter":

        if not message.text.isdigit():

            return await message.reply_text(
                "أرسل رقماً فقط."
            )

        set_setting(
            "fake_offset",
            message.text
        )

        await message.reply_text(
            f"✅ تم تحديث العداد الوهمي إلى {message.text}"
        )

        return
# ================= USER HANDLER =================

@bot.on_message(
    filters.private &
    filters.text &
    ~filters.command(["start", "admin"])
)
async def user_handler(client: Client, message: Message):

    user_id = message.from_user.id

    if user_id == ADMIN_ID and user_id in admin_state:
        return

    if is_banned(user_id):
        return

    if not await anti_spam(message):
        return

    if not await is_subscribed(user_id):

        channel = get_setting("main_channel")

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "📢 الاشتراك",
                        url=channel
                    )
                ],
                [
                    InlineKeyboardButton(
                        "✅ تحقق",
                        callback_data="check_join"
                    )
                ]
            ]
        )

        return await message.reply_text(
            "يجب الاشتراك أولاً.",
            reply_markup=keyboard
        )

    text = message.text.strip()

    # ================= الخدمات المجانية =================

    if text == "🎁 الخدمات المجانية":

        return await message.reply_text(
            "أرسل رابط القناة أو معرفها (@username)."
        )

    # ================= شراء خدمات =================

    if text == "🛒 شراء خدمات":

        return await message.reply_text(
            "راسل الدعم الفني لشراء الخدمات."
        )

    # ================= الرصيد =================

    if text == "💰 رصيد المحاولات":

        return await message.reply_text(
            "رصيدك الحالي : 5 محاولات."
        )

    # ================= السجل =================

    if text == "📋 سجل الطلبات":

        return await message.reply_text(
            "لا يوجد أي طلب حالياً."
        )

    # ================= الدعوة =================

    if text == "👥 دعوة صديق":

        me = await bot.get_me()

        return await message.reply_text(
            f"https://t.me/{me.username}?start={user_id}"
        )

    # ================= رابط قناة =================

    if (
        text.startswith("@")
        or
        text.startswith("https://t.me/")
        or
        text.startswith("http://t.me/")
        or
        text.startswith("t.me/")
    ):

        wait = await message.reply_text(
            "⏳ جارٍ الانضمام..."
        )

        ok, result = await join_channel(text)

        if not ok:

            return await wait.edit_text(
                f"❌ فشل الانضمام.\n\n{result}"
            )

        save_channel(
            user_id,
            text
        )

        try:

            title = result.title

        except Exception:

            title = text

        await wait.edit_text(
            f"""✅ تم الانضمام بنجاح.

📢 القناة :
{title}
"""
        )

        await safe_send(
            ADMIN_ID,
            f"""📥 قناة جديدة

👤 المستخدم :
{message.from_user.mention}

🆔 :
{user_id}

📢 :
{text}

✅ تم الانضمام بواسطة Userbot.
"""
        )

        return

    await message.reply_text(
        "الرجاء اختيار أحد الخيارات أو إرسال رابط قناة."
    )

# ================= MEMBER UPDATE =================

@bot.on_chat_member_updated()
async def member_update_handler(client, update):

    try:

        main_channel = get_setting("main_channel")

        if not main_channel:
            return

        username = (
            main_channel
            .replace("https://t.me/", "")
            .replace("http://t.me/", "")
            .replace("@", "")
            .strip()
        )

        if not update.chat:
            return

        if (update.chat.username or "").lower() != username.lower():
            return

        if not update.old_chat_member:
            return

        if not update.new_chat_member:
            return

        old_status = update.old_chat_member.status
        new_status = update.new_chat_member.status

        if old_status == ChatMemberStatus.LEFT:
            return

        if new_status != ChatMemberStatus.LEFT:
            return

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

            try:

                await safe_send(
                    user_id,
                    f"""⚠️ لقد غادرت القناة الرئيسية.

لذلك غادر الـ Userbot قناتك تلقائياً:

{channel}
"""
                )

            except Exception:
                pass

            try:

                await safe_send(
                    ADMIN_ID,
                    f"""🚨 مغادرة القناة الرئيسية

👤 المستخدم:
{user.mention}

🆔:
{user_id}

📢 القناة:

{channel}

✅ تمت المغادرة بواسطة الـ Userbot.
"""
                )

            except Exception:
                pass

    except Exception as e:

        logging.exception(e)
        # ================= WEB SERVER =================

async def health(request):
    return web.Response(
        text="Bot is running."
    )


async def start_web():

    app = web.Application()

    app.router.add_get("/", health)
    app.router.add_get("/health", health)

    runner = web.AppRunner(app)

    await runner.setup()

    port = int(
        os.getenv(
            "PORT",
            "10000"
        )
    )

    site = web.TCPSite(
        runner,
        "0.0.0.0",
        port
    )

    await site.start()

    logging.info(
        f"Web Server Started : {port}"
    )


# ================= START CLIENTS =================

async def start_clients():

    while True:

        try:

            await userbot.start()

            logging.info(
                "Userbot Started."
            )

            break

        except FloodWait as e:

            logging.warning(
                f"FloodWait {e.value}"
            )

            await asyncio.sleep(
                e.value
            )

        except Exception as e:

            logging.exception(e)

            await asyncio.sleep(5)

    while True:

        try:

            await bot.start()

            logging.info(
                "Bot Started."
            )

            break

        except FloodWait as e:

            logging.warning(
                f"FloodWait {e.value}"
            )

            await asyncio.sleep(
                e.value
            )

        except Exception as e:

            logging.exception(e)

            await asyncio.sleep(5)


# ================= STOP CLIENTS =================

async def stop_clients():

    try:
        await bot.stop()
    except Exception:
        pass

    try:
        await userbot.stop()
    except Exception:
        pass


# ================= MAIN =================

async def main():

    await start_web()

    await start_clients()

    logging.info(
        "Project Started Successfully."
    )

    await idle()

    await stop_clients()


if __name__ == "__main__":

    asyncio.run(
        main()
    )

