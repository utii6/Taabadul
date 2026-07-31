import asyncio
import io
import logging
import math
import os
from datetime import datetime
import pytz
from PIL import Image, ImageDraw, ImageFont
from pyrogram.errors import FloodWait

logger = logging.getLogger(__name__)

TIMEZONE = pytz.timezone("Asia/Baghdad")
BASE_NAME = ".."
CUSTOM_FONT_PATH = "font.ttf"


def get_custom_font(size: int):
    if os.path.exists(CUSTOM_FONT_PATH):
        try:
            return ImageFont.truetype(CUSTOM_FONT_PATH, size)
        except Exception:
            pass
    try:
        return ImageFont.truetype("arial.ttf", size)
    except IOError:
        return ImageFont.load_default()


def draw_gradient(width, height, top_color, bottom_color):
    base = Image.new("RGB", (width, height), top_color)
    top = Image.new("RGB", (width, height), bottom_color)
    mask = Image.new("L", (width, height))
    mask_draw = ImageDraw.Draw(mask)

    for y in range(height):
        alpha = int(255 * (y / height))
        mask_draw.line([(0, y), (width, y)], fill=alpha)

    base.paste(top, (0, 0), mask)
    return base


def create_time_avatar(time_str: str, is_day: bool) -> io.BytesIO:
    width, height = 1024, 1024

    if is_day:
        top_color = (15, 23, 60)
        bottom_color = (88, 28, 135)
        glow_color = (245, 158, 11, 255)
        mode_icon = "☀️"
    else:
        top_color = (10, 15, 40)
        bottom_color = (35, 10, 65)
        glow_color = (56, 189, 248, 255)
        mode_icon = "🌙"

    img = draw_gradient(width, height, top_color, bottom_color)
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    center_x, center_y = width // 2, height // 2

    # 1. عناصر خلفية تقنية (HUD)
    draw.ellipse(
        [center_x - 450, center_y - 450, center_x + 450, center_y + 450],
        outline=(glow_color[0], glow_color[1], glow_color[2], 60),
        width=4,
    )
    draw.ellipse(
        [center_x - 410, center_y - 410, center_x + 410, center_y + 410],
        outline=(234, 179, 8, 100),
        width=3,
    )

    for angle in range(0, 360, 30):
        rad = math.radians(angle)
        x1 = int(center_x + 420 * math.cos(rad))
        y1 = int(center_y + 420 * math.sin(rad))
        x2 = int(center_x + 445 * math.cos(rad))
        y2 = int(center_y + 445 * math.sin(rad))
        draw.line([(x1, y1), (x2, y2)], fill=(234, 179, 8, 180), width=6)

    # 2. الشعار العلوي (رمز الصاروخ)
    font_rocket = get_custom_font(90)
    draw.text((center_x, center_y - 320), "🚀", font=font_rocket, anchor="mm")

    # 3. المربع الرئيسي الكبير في منتصف الصورة باللون الذهبي الداكن بأسلوب Glassmorphism
    card_box = [center_x - 400, center_y - 230, center_x + 400, center_y + 250]
    gold_border = (234, 179, 8, 255)
    draw.rounded_rectangle(
        card_box, radius=45, fill=(15, 23, 42, 220), outline=gold_border, width=8
    )

    # 4. إطار داخلي رفيع لزيادة الفخامة
    inner_box = [center_x - 385, center_y - 215, center_x + 385, center_y + 235]
    draw.rounded_rectangle(
        inner_box, radius=35, outline=(250, 204, 21, 120), width=3
    )

    # 5. الخطوط للنصوص
    font_username = get_custom_font(85)
    font_time = get_custom_font(180)
    font_footer = get_custom_font(36)

    # يوزر البوت باللون الذهبي في الجزء العلوي من المربع
    bot_username = "@RiRBbot"
    draw.text(
        (center_x, center_y - 120),
        bot_username,
        fill=(250, 204, 21, 255),
        font=font_username,
        anchor="mm",
    )

    # الوقت الحالي في منتصف المربع تحت اليوزر مباشرة
    draw.text(
        (center_x, center_y + 60),
        time_str,
        fill=(255, 255, 255, 255),
        font=font_time,
        anchor="mm",
    )

    # نص التحديث السفلي
    status_text = f"⚡ UPDATED EVERY MINUTE {mode_icon} ⚡"
    draw.text(
        (center_x, center_y + 310),
        status_text,
        fill=(234, 179, 8, 255),
        font=font_footer,
        anchor="mm",
    )

    final_img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

    img_byte_arr = io.BytesIO()
    img_byte_arr.name = "avatar.jpg"
    final_img.save(img_byte_arr, format="JPEG", quality=95)
    img_byte_arr.seek(0)
    return img_byte_arr


async def update_profile_every_minute(userbot_client):
    while True:
        try:
            now = datetime.now(TIMEZONE)
            time_str = now.strftime("%I:%M")
            am_pm = "AM" if now.strftime("%p") == "AM" else "PM"

            is_day = 6 <= now.hour < 18
            time_icon = "☀️" if is_day else "🌙"

            new_name = f"{BASE_NAME} {time_icon} {time_str} {am_pm}"
            await userbot_client.update_profile(first_name=new_name)

            avatar_bytes = create_time_avatar(time_str, is_day)

            await userbot_client.set_profile_photo(photo=avatar_bytes)
            logger.info(
                f"[TIME_AVATAR] Updated profile photo & name: {time_str} {am_pm}"
            )

        except FloodWait as e:
            logger.warning(
                f"[TIME_AVATAR] FloodWait received: waiting {e.value} seconds."
            )
            await asyncio.sleep(e.value)
        except Exception as e:
            logger.error(f"[TIME_AVATAR] Error: {e}")

        await asyncio.sleep(60)
