import random
import os
from aiohttp import ClientSession
from pyrogram import Client, filters
from pyrogram.types import CallbackQuery

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

AZKAR_LIST = [
    "لا إله إلا أنت سبحانك إني كنت من الظالمين\n\nكـن مـن الـذ ا كـر يـن . .",
    "سبحان الله وبحمده، سبحان الله العظيم\n\nكـن مـن الـذ ا كـر يـن . .",
    "أستغفر الله العظيم وأتوب إليه\n\nكـن مـن الـذ ا كـر يـن . .",
    "لا حول ولا قوة إلا بالله العلي العظيم\n\nكـن مـن الـذ ا كـر يـن . .",
    "اللهم صلِّ وسلم على نبينا محمد\n\nكـن مـن الـذ ا كـر يـن . ."
]

# 1. جلب العداد العام لجميع المستخدمين
def get_global_tasbeeh_count() -> int:
    try:
        from bot import db, check_db_health
        check_db_health()
        with db.cursor() as cursor:
            cursor.execute("SELECT value_count FROM metrics WHERE key='global_tasbeeh';")
            row = cursor.fetchone()
            return row["value_count"] if row else 0
    except Exception:
        return 0

# 2. زيادة العداد العام عند ضغط أي شخص
def increment_global_tasbeeh_count() -> int:
    try:
        from bot import db, check_db_health
        check_db_health()
        with db.cursor() as cursor:
            cursor.execute("""
            INSERT INTO metrics (key, value_count) VALUES ('global_tasbeeh', 1)
            ON CONFLICT (key) DO UPDATE SET value_count = metrics.value_count + 1
            RETURNING value_count;
            """)
            row = cursor.fetchone()
            return row["value_count"] if row else 1
    except Exception:
        return 1

def get_tasbeeh_markup(count: int):
    return {
        "inline_keyboard": [
            [
                {
                    "text": f"📿 العداد العام: ({count})",
                    "callback_data": "tsb_global",
                    "style": "primary"
                }
            ]
        ]
    }

async def send_random_zikr(client: Client, chat_id: int, user_id: int):
    try:
        count = get_global_tasbeeh_count()
        zikr_text = random.choice(AZKAR_LIST)
        
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": zikr_text,
            "parse_mode": "Markdown",
            "reply_markup": get_tasbeeh_markup(count)
        }
        
        async with ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                await resp.json()
    except Exception as e:
        print(f"Error sending zikr: {e}")

# 3. معالج الضغط على الزر العام
def register_tasbeeh_handlers(bot: Client):
    @bot.on_callback_query(filters.regex(r"^tsb_global$"))
    async def on_tasbeeh_click(client: Client, callback_query: CallbackQuery):
        # زيادة العداد العام المخزن في قاعدة البيانات
        current_count = increment_global_tasbeeh_count()

        await callback_query.answer("تمت إضافة تسبيحتك إلى العداد العام! 🌸")

        try:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageReplyMarkup"
            payload = {
                "chat_id": callback_query.message.chat.id,
                "message_id": callback_query.message.id,
                "reply_markup": get_tasbeeh_markup(current_count)
            }
            async with ClientSession() as session:
                async with session.post(url, json=payload) as resp:
                    await resp.json()
        except Exception:
            pass
