import random
from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

AZKAR_LIST = [
    "لا إله إلا أنت سبحانك إني كنت من الظالمين\n\nكـن مـن الـذ ا كـر يـن . .",
    "سبحان الله وبحمده، سبحان الله العظيم\n\nكـن مـن الـذ ا كـر يـن . .",
    "أستغفر الله العظيم وأتوب إليه\n\nكـن مـن الـذ ا كـر يـن . .",
    "لا حول ولا قوة إلا بالله العلي العظيم\n\nكـن مـن الـذ ا كـر يـن . .",
    "اللهم صلِّ وسلم على نبينا محمد\n\nكـن مـن الـذ ا كـر يـن . ."
]

user_counter = {}

async def send_random_zikr(client: Client, chat_id: int, user_id: int):
    count = user_counter.get(user_id, 0)
    zikr_text = random.choice(AZKAR_LIST)
    
    await client.send_message(
        chat_id=chat_id, 
        text=zikr_text, 
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(f"📿 ({count})", callback_data=f"tsb_{count}")]
        ])
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
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(f"📿 ({current_count})", callback_data=f"tsb_{current_count}")]
                ])
            )
        except Exception:
            pass
