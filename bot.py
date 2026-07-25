import asyncio
import logging
import sqlite3
import os
from pyrogram import Client, filters
from pyrogram.enums import ChatAction
from pyrogram.types import (
    ReplyKeyboardMarkup, 
    KeyboardButton, 
    InlineKeyboardMarkup, 
    InlineKeyboardButton, 
    Message, 
    CallbackQuery
)

# ---------------- CONFIGURATION & ENV VARIABLES ----------------
API_ID = int(os.environ.get("API_ID", "1234567"))
API_HASH = os.environ.get("API_HASH", "YOUR_API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN")
USERBOT_SESSION = os.environ.get("USERBOT_SESSION", "YOUR_STRING_SESSION")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "123456789"))

logging.basicConfig(level=logging.INFO)

# ---------------- DATABASE SETUP ----------------
conn = sqlite3.connect("bot_data.db", check_same_thread=False)
cursor = conn.cursor()

# الجدول الأول: الإعدادات العامة (القناة الرئيسية، العداد الوهمي)
cursor.execute("""
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
)
""")

# الجدول الثاني: المستخدمين المسجلين
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    full_name TEXT,
    is_banned INTEGER DEFAULT 0
)
""")

# الجدول الثالث: القنوات المضافة
cursor.execute("""
CREATE TABLE IF NOT EXISTS joined_channels (
    user_id INTEGER,
    channel_url TEXT PRIMARY KEY
)
""")
conn.commit()

# الإعدادات الافتراضية
cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('main_channel', 'https://t.me/YourDefaultChannel')")
cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('fake_offset', '37')")
conn.commit()

# ---------------- CLIENTS INITIALIZATION ----------------
bot = Client("my_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
userbot = Client("my_userbot", api_id=API_ID, api_hash=API_HASH, session_string=USERBOT_SESSION)

# حالات الأدمن المؤقتة للإدخال
admin_state = {}

# ---------------- HELPER FUNCTIONS ----------------
def get_setting(key: str) -> str:
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    return row[0] if row else ""

def set_setting(key: str, value: str):
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()

def add_user(user_id: int, username: str, full_name: str) -> bool:
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    if cursor.fetchone() is None:
        cursor.execute("INSERT INTO users (user_id, username, full_name) VALUES (?, ?, ?)", (user_id, username, full_name))
        conn.commit()
        return True
    return False

def is_banned(user_id: int) -> bool:
    cursor.execute("SELECT is_banned FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    return bool(row[0]) if row else False

def set_ban(user_id: int, ban_status: int):
    cursor.execute("UPDATE users SET is_banned = ? WHERE user_id = ?", (ban_status, user_id))
    conn.commit()

def get_total_users_count() -> int:
    cursor.execute("SELECT COUNT(*) FROM users")
    real_count = cursor.fetchone()[0]
    fake_offset = int(get_setting("fake_offset") or 0)
    return real_count + fake_offset

def save_user_channel(user_id: int, channel: str):
    cursor.execute("INSERT OR REPLACE INTO joined_channels (user_id, channel_url) VALUES (?, ?)", (user_id, channel))
    conn.commit()

def remove_user_channel(user_id: int):
    cursor.execute("DELETE FROM joined_channels WHERE user_id = ?", (user_id,))
    conn.commit()

def get_user_channel(user_id: int):
    cursor.execute("SELECT channel_url FROM joined_channels WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    return row[0] if row else None

# ---------------- KEYBOARDS ----------------
main_keyboard = ReplyKeyboardMarkup(
    [
        [KeyboardButton("🎁 الخدمات المجانية")],
        [KeyboardButton("🛒 شراء خدمات")],
        [KeyboardButton("💰 رصيد المحاولات"), KeyboardButton("📋 سجل الطلبات")],
        [KeyboardButton("👥 دعوة صديق")]
    ],
    resize_keyboard=True
)

def get_admin_inline_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 إرسال إذاعة", callback_data="admin_broadcast"), InlineKeyboardButton("✏️ تغيير القناة الرئيسية", callback_data="admin_change_main")],
        [InlineKeyboardButton("🔢 تعديل العداد الوهمي", callback_data="admin_change_offset"), InlineKeyboardButton("📊 الإحصائيات", callback_data="admin_stats")],
        [InlineKeyboardButton("🚫 حظر / فك حظر", callback_data="admin_ban_user")]
    ])

# ---------------- HANDLERS ----------------

# 1. /start Command
@bot.on_message(filters.command("start") & filters.private)
async def start_handler(client: Client, message: Message):
    if is_banned(message.from_user.id):
        return await message.reply_text("❌ أنت محظور من استخدام البوت.")

    await message.react("✨")
    
    # محاكاة جارٍ الكتابة
    await client.send_chat_action(message.chat.id, ChatAction.TYPING)
    await asyncio.sleep(1.5)

    user_id = message.from_user.id
    username = message.from_user.username or "لا يوجد"
    full_name = message.from_user.first_name + (f" {message.from_user.last_name}" if message.from_user.last_name else "")
    
    # تسجيل العضو الجديد وإرسال إشعار للمالك
    is_new = add_user(user_id, username, full_name)
    if is_new:
        total_count = get_total_users_count()
        notify_msg = (
            f"👾 **شخص جديد دخل البوت**\n\n"
            f"👤 **معلومات العضو الجديد:**\n"
            f"• **الاسم:** {full_name}\n"
            f"• **المعرف:** @{username}\n"
            f"• **الآيدي:** `{user_id}`\n\n"
            f"📊 **إجمالي المستخدمين:** {total_count}"
        )
        try:
            await client.send_message(ADMIN_ID, notify_msg)
        except Exception:
            pass

    main_ch = get_setting("main_channel")
    welcome_text = (
        f"أهلاً بك يا {message.from_user.first_name} 👋\n\n"
        f"📢 القناة المطلوب الاشتراك بها أولاً:\n{main_ch}\n\n"
        f"أرسل رابط أو معرف قناتك الآن ليتم الاشتراك فيها تلقائياً! 🚀"
    )
    
    await message.reply_text(welcome_text, reply_markup=main_keyboard, disable_web_page_preview=True)

# 2. /admin Command
@bot.on_message(filters.command("admin") & filters.private)
async def admin_cmd(client: Client, message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    await client.send_chat_action(message.chat.id, ChatAction.TYPING)
    await asyncio.sleep(1)
    
    await message.reply_text("⚙️ **أهلاً بك في لوحة تحكم المالك:**", reply_markup=get_admin_inline_kb())

# 3. Handle Keyboard Buttons & Text Responses
@bot.on_message(filters.private & filters.text & ~filters.command(["start", "admin"]))
async def text_handler(client: Client, message: Message):
    if is_banned(message.from_user.id):
        return

    user_id = message.from_user.id
    text = message.text.strip()

    # معالجة إدخالات لوحة الأدمن
    if user_id == ADMIN_ID and user_id in admin_state:
        state = admin_state.pop(user_id)
        
        if state == "awaiting_main_channel":
            set_setting("main_channel", text)
            await message.reply_text(f"✅ تم تحديث القناة الرئيسية إلى:\n{text}")
            return
            
        elif state == "awaiting_fake_offset":
            if text.isdigit():
                set_setting("fake_offset", text)
                await message.reply_text(f"✅ تم تعديل العداد الوهمي إلى: {text}")
            else:
                await message.reply_text("⚠️ يرجى إدخال رقم صحيح فقط.")
            return

        elif state == "awaiting_broadcast":
            cursor.execute("SELECT user_id FROM users WHERE is_banned = 0")
            all_users = cursor.fetchall()
            success, failed = 0, 0
            
            await message.reply_text("⏳ جاري إرسال الإذاعة...")
            for row in all_users:
                u_id = row[0]
                try:
                    await message.copy(u_id)
                    success += 1
                    await asyncio.sleep(0.05)
                except Exception:
                    failed += 1
            
            await message.reply_text(
                f"✅ **تم الانتهاء من الإذاعة!**\n\n"
                f"🟢 الناجحين: {success}\n"
                f"🔴 الفاشلين: {failed}"
            )
            return

        elif state == "awaiting_ban":
            try:
                target_id = int(text)
                set_ban(target_id, 1)
                await message.reply_text(f"✅ تم حظر المستخدم `{target_id}` بنجاح.")
            except ValueError:
                await message.reply_text("⚠️ آيدي غير صالح.")
            return

    # الأزرار الرئيسية
    if text == "🎁 الخدمات المجانية":
        await message.react("🎁")
        await client.send_chat_action(message.chat.id, ChatAction.TYPING)
        await asyncio.sleep(1)
        return await message.reply_text("أرسل رابط أو يوزر قناتك لتشترك بها خدماتنا المجانية!")

    elif text == "🛒 شراء خدمات":
        await message.react("🛒")
        await client.send_chat_action(message.chat.id, ChatAction.TYPING)
        await asyncio.sleep(1)
        return await message.reply_text("لشراء الخدمات التواصل مع الدعم الفني.")

    elif text == "💰 رصيد المحاولات":
        await client.send_chat_action(message.chat.id, ChatAction.TYPING)
        await asyncio.sleep(1)
        return await message.reply_text("💰 رصيدك الحالي: 5 محاولات جديدة.")

    elif text == "📋 سجل الطلبات":
        await client.send_chat_action(message.chat.id, ChatAction.TYPING)
        await asyncio.sleep(1)
        return await message.reply_text("📋 لا توجد طلبات معلقة حالياً.")

    elif text == "👥 دعوة صديق":
        await client.send_chat_action(message.chat.id, ChatAction.TYPING)
        await asyncio.sleep(1)
        return await message.reply_text(f"🔗 رابط الدعوة الخاص بك:\n`https://t.me/{(await client.get_me()).username}?start={user_id}`")

    # معالجة إضافة القنوات (الاشتراك التلقائي عبر الـ Userbot)
    if "t.me/" in text or text.startswith("@"):
        await message.react("⏳")
        await client.send_chat_action(message.chat.id, ChatAction.TYPING)
        
        try:
            # الحساب الشخصي ينضم للقناة
            chat = await userbot.join_chat(text)
            save_user_channel(user_id, text)
            
            await message.react("🎉")
            await message.reply_text(
                f"✅ **تم الاشتراك في قناتك بنجاح!**\n\n"
                f"📌 **اسم القناة:** `{chat.title}`\n"
                f"🤝 تم الانضمام بواسطة حسابنا المخصص."
            )
            
            # إشعار للمالك
            admin_log = (
                f"📥 **تم إضافة قناة جديدة!**\n\n"
                f"👤 **المستخدم:** {message.from_user.mention} (`{user_id}`)\n"
                f"📢 **القناة:** {chat.title} ({text})\n"
                f"🤝 **الحالة:** تم الانضمام بنجاح."
            )
            await client.send_message(ADMIN_ID, admin_log)

        except Exception as e:
            await message.react("❌")
            await message.reply_text(f"❌ **عذراً، تعذر الانضمام للقناة:**\n`{str(e)}`")

# 4. Callback Query Handler (لوحة الأدمن)
@bot.on_callback_query()
async def callback_handler(client: Client, query: CallbackQuery):
    if query.from_user.id != ADMIN_ID:
        return await query.answer("⚠️ غير مصرح لك.", show_alert=True)
        
    data = query.data
    user_id = query.from_user.id

    if data == "admin_stats":
        cursor.execute("SELECT COUNT(*) FROM users")
        real_users = cursor.fetchone()[0]
        fake_offset = int(get_setting("fake_offset") or 0)
        cursor.execute("SELECT COUNT(*) FROM joined_channels")
        channels_count = cursor.fetchone()[0]

        stats_text = (
            f"📊 **الإحصائيات المباشرة:**\n\n"
            f"• المستخدمين الحقيقيين: {real_users}\n"
            f"• العداد الوهمي المضاف: {fake_offset}\n"
            f"• **المجموع الكلي:** {real_users + fake_offset}\n"
            f"• القنوات المشترك بها: {channels_count}"
        )
        await query.answer()
        await query.message.edit_text(stats_text, reply_markup=get_admin_inline_kb())

    elif data == "admin_change_main":
        admin_state[user_id] = "awaiting_main_channel"
        await query.answer()
        await query.message.reply_text("✏️ أرسل الآن رابط القناة الرئيسية الجديد:")

    elif data == "admin_change_offset":
        admin_state[user_id] = "awaiting_fake_offset"
        await query.answer()
        await query.message.reply_text("🔢 أرسل الآن رقم العداد الوهمي الجديد (مثال: 50):")

    elif data == "admin_broadcast":
        admin_state[user_id] = "awaiting_broadcast"
        await query.answer()
        await query.message.reply_text("📢 أرسل الآن الرسالة (نص، صورة، أو توجيه) لإرسالها للجميع:")

    elif data == "admin_ban_user":
        admin_state[user_id] = "awaiting_ban"
        await query.answer()
        await query.message.reply_text("🚫 أرسل آيدي (ID) المستخدم المراد حظره:")

# 5. متابعة خروج المستخدم ومغادرة القناة التلقائية
@bot.on_chat_member_updated()
async def member_update_handler(client: Client, update):
    main_ch = get_setting("main_channel")
    # إذا كانت القناة هي القناة الرئيسية وتم رصد مغادرة
    if update.chat and main_ch in (update.chat.username or ""):
        if update.old_chat_member and update.new_chat_member.status.value == "left":
            user = update.old_chat_member.user
            user_id = user.id
            
            user_ch = get_user_channel(user_id)
            if user_ch:
                try:
                    # يغادر الـ Userbot من قناة المستخدم
                    await userbot.leave_chat(user_ch)
                    remove_user_channel(user_id)
                except Exception:
                    pass

                # تنبيه للمستخدم
                try:
                    await client.send_message(
                        user_id, 
                        f"⚠️ **تنبيه:** لاحظنا مغادرتك لقناتنا الرئيسية، وبناءً عليه قام حسابنا بالمغادرة من قناتك (`{user_ch}`)."
                    )
                except Exception:
                    pass

                # تنبيه للمالك
                admin_alert = (
                    f"🚨 **تنبيه مغادرة!**\n\n"
                    f"👤 **المستخدم:** {user.mention} (`{user_id}`)\n"
                    f"📢 **قد غادر القناة الرئيسية.**\n"
                    f"⚙️ **الإجراء:** تم المغادرة من قناته ({user_ch}) وإشعاره."
                )
                try:
                    await client.send_message(ADMIN_ID, admin_alert)
                except Exception:
                    pass

# ---------------- RUN BOT ----------------
from aiohttp import web

# سيرفر ويب خفيف للرد على Render Health Check
async def handle_ping(request):
    return web.Response(text="Bot is Alive and Running!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    app.router.add_get("/health", handle_ping)
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    # Render يمرر المنفذ تلقائياً في متغير PORT
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"🌐 Web Server running on port {port}")

# ---------------- RUN BOT & WEB SERVICE ----------------
async def main():
    # تشغيل سيرفر الويب أولاً لإرضاء Render
    await start_web_server()
    
    # تشغيل البوت والـ Userbot
    await userbot.start()
    await bot.start()
    print("🚀 Bot and Userbot are online!")
    
    await asyncio.Event().wait()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
