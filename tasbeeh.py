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

user_counter = {}

def get_tasbeeh_markup(count: int):
    # استخدام خاصية style: "primary" للحصول على الزر الملون الأزرق
    return {
        "inline_keyboard": [
            [
                {
                    "text": f"📿 ({count})",
                    "callback_data": f"tsb_{count}",
                    "style": "primary"
                }
            ]
        ]
    }

async def send_random_zikr(client: Client, chat_id: int, user_id: int):
    try:
        count = user_counter.get(user_id, 0)
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

def register_tasbeeh_handlers(bot: Client):
    @bot.on_callback_query(filters.regex(r"^tsb_\d+$"))
    async def on_tasbeeh_click(client: Client, callback_query: CallbackQuery):
        user_id = callback_query.from_user.id
        current_count = user_counter.get(user_id, 0) + 1
        user_counter[user_id] = current_count

        await callback_query.answer()

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
