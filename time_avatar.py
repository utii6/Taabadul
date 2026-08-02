import asyncio
import io
import logging
import os
from datetime import datetime
import pytz
from PIL import Image, ImageDraw, ImageFont
from pyrogram.errors import FloodWait

logger = logging.getLogger(__name__)

TIMEZONE = pytz.timezone("Asia/Baghdad")
BASE_NAME = ".."
CUSTOM_FONT_PATH = "font.ttf"
TEMPLATE_IMAGE_PATH = "template.jpg"


def get_custom_font(size: int):
    """جلب الخط المخصص أو الافتراضي مع الحجم المحدد"""
    if os.path.exists(CUSTOM_FONT_PATH):
        try:
            return ImageFont.truetype(CUSTOM_FONT_PATH, size)
        except Exception:
            pass
    try:
        return ImageFont.truetype("arial.ttf", size)
    except IOError:
        return ImageFont.load_default()


def create_time_avatar(time_str: str, is_day: bool) -> io.BytesIO:
    """إنشاء صورة الملف الشخصي مع تكبير حجم النص والوقت ليكون واضحاً"""
    if os.path.exists(TEMPLATE_IMAGE_PATH):
        img = Image.open(TEMPLATE_IMAGE_PATH).convert("RGBA")
    else:
        width, height = 1024, 1024
        img = Image.new("RGBA", (width, height), (15, 23, 42, 255))

    width, height = img.size
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    center_x, center_y = width // 2, height // 2

    mode_icon = "☀️" if is_day else "🌙"

    font_username = get_custom_font(95)
    font_time = get_custom_font(170)
    font_footer = get_custom_font(42)

    bot_username = "@RiRBbot"

    # كتابة اليوزر في الأعلى
    draw.text(
        (center_x, center_y - 140),
        bot_username,
        fill=(250, 204, 21, 255),
        font=font_username,
        anchor="mm",
    )

    # كتابة الوقت في المنتصف
    draw.text(
        (center_x, center_y + 30),
        time_str,
        fill=(255, 255, 255, 255),
        font=font_time,
        anchor="mm",
    )

    # كتابة النص السفلي
    status_text = f"UPDATED EVERY MINUTE {mode_icon}"
    draw.text(
        (center_x, center_y + 210),
        status_text,
        fill=(234, 179, 8, 255),
        font=font_footer,
        anchor="mm",
    )

    final_img = Image.alpha_composite(img, overlay).convert("RGB")

    img_byte_arr = io.BytesIO()
    img_byte_arr.name = "avatar.jpg"
    final_img.save(img_byte_arr, format="JPEG", quality=95)
    img_byte_arr.seek(0)
    return img_byte_arr


async def update_profile_every_minute(userbot_client):
    """دالة التحديث الدورية المستمرة بدون أخطاء أو تعليق"""
    photo_counter = 1
    last_updated_min = -1

    while True:
        try:
            now = datetime.now(TIMEZONE)

            if now.minute != last_updated_min:
                time_str = now.strftime("%I:%M")
                am_pm = now.strftime("%p")

                is_day = 6 <= now.hour < 18
                time_icon = "☀️" if is_day else "🌙"

                new_name = f"{BASE_NAME} {time_icon} {time_str} {am_pm} 🎣🐟"

                await userbot_client.update_profile(first_name=new_name)
                last_updated_min = now.minute
                logger.info(f"[TIME_PROFILE] Updated name: {time_str} {am_pm}")

                if photo_counter % 5 == 0:
                    try:
                        avatar_bytes = create_time_avatar(time_str, is_day)
                        await userbot_client.set_profile_photo(photo=avatar_bytes)
                        logger.info("[TIME_PROFILE] Updated profile photo successfully.")
                    except Exception as photo_err:
                        logger.error(f"[TIME_PROFILE] Photo Update Failed: {photo_err}")

                photo_counter += 1

        except FloodWait as e:
            logger.warning(f"[TIME_PROFILE] FloodWait received: waiting {e.value} seconds.")
            await asyncio.sleep(e.value)
        except Exception as e:
            logger.error(f"[TIME_PROFILE] General Error: {e}")

        await asyncio.sleep(5)
