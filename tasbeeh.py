import random
from pyrogram import Client, filters
from pyrogram.types import CallbackQuery

# قائمة الأذكار
AZKAR_LIST = [
    "لا إله إلا أنت سبحانك إني كنت من الظالمين\n\nكـن مـن الـذ ا كـر يـن . .",
    "سبحان الله وبحمده، سبحان الله العظيم\n\nكـن مـن الـذ ا كـر يـن . .",
    "أستغفر الله العظيم وأتوب إليه\n\nكـن مـن الـذ ا كـر يـن . .",
    "لا حول ولا قوة إلا بالله العلي العظيم\n\nكـن مـن الـذ ا كـر يـن . .",
    "اللهم صلِّ وسلم على نبينا محمد\n\nكـن مـن الـذ ا كـر يـن . ."
]

# عداد التسبيح
user_counter = {}

def get_tasbeeh_keyboard(count: int):
    return {
        "inline_keyboard": [
            [{"text": f"📿 ({count})", "callback_data": f"tsb_{count}"}]
        ]
    }

async def send_random_zikr(client: Client, chat_id: int, user_id: int):
    count = user_counter.get(user_id, 0)
    zikr_text = random.choice(AZKAR_LIST)
    return await client.send_message(
        chat_id=chat_id,
        text=zikr_text,
        reply_markup=get_tasbeeh_keyboard(count)
    )

def register_tasbeeh_handlers(bot: Client):
    @bot.on_callback_query(filters.regex(r"^tsb_\d+$"))
    async def on_tasbeeh_click(client: Client, callback_query: CallbackQuery):
        user_id = callback_query.from_user.id
        
        current_count = user_counter.get(user_id, 0) + 1
        user_counter[user_id] = current_count

        await callback_query.answer()

        try:
            await callback_query.edit_message_reply_markup(
                reply_markup=get_tasbeeh_keyboard(current_count)
            )
        except Exception:
            pass
