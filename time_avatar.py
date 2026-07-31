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
BASE_NAME = "قاسم"
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
        glow_color = (251, 191, 36, 255)
        border_color = (245, 158, 11, 200)
        mode_icon = "☀️"
    else:
        top_color = (10, 15, 40)
        bottom_color = (35, 10, 65)
        glow_color = (56, 189, 248, 255)
        border_color = (56, 189, 248, 180)
        mode_icon = "🌙"

    img = draw_gradient(width, height, top_color, bottom_color)
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    center_x, center_y = width // 2, height // 2

    draw.ellipse(
        [center_x - 450, center_y - 450, center_x + 450, center_y + 450],
        outline=(glow_color[0], glow_color[1], glow_color[2], 80),
        width=6,
    )
    draw.ellipse(
        [center_x - 410, center_y - 410, center_x + 410, center_y + 410],
        outline=(168, 85, 247, 120),
        width=4,
    )

    for angle in range(0, 360, 30):
        rad = math.radians(angle)
        x1 = int(center_x + 420 * math.cos(rad))
        y1 = int(center_y + 420 * math.sin(rad))
        x2 = int(center_x + 445 * math.cos(rad))
        y2 = int(center_y + 445 * math.sin(rad))
        draw.line([(x1, y1), (x2, y2)], fill=glow_color, width=8)

    card_box = [center_x - 380, center_y - 300, center_x + 380, center_y + 300]
    draw.rounded_rectangle(
        card_box, radius=50, fill=(15, 23, 42, 210), outline=border_color, width=5
    )

    font_large = get_custom_font(240)
    font_sub = get_custom_font(52)
    font_small = get_custom_font(42)

    title_text = f"CHANNEL EXCHANGE {mode_icon}"
    draw.text(
        (center_x, center_y - 200),
        title_text,
        fill=glow_color,
        font=font_sub,
        anchor="mm",
    )

    draw.text(
        (center_x, center_y - 10),
        time_str,
        fill=(255, 255, 255, 255),
        font=font_large,
        anchor="mm",
    )

    status_text = "⚡ UPDATED EVERY MINUTE ⚡"
    draw.text(
        (center_x, center_y + 190),
        status_text,
        fill=(168, 85, 247, 255),
        font=font_small,
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
                f"[TIME_AVATAR] Profile updated successfully ({'Day' if is_day else 'Night'} Theme): {time_str}"
            )

        except FloodWait as e:
            logger.warning(
                f"[TIME_AVATAR] FloodWait received: waiting {e.value} seconds."
            )
            await asyncio.sleep(e.value)
        except Exception as e:
            logger.error(f"[TIME_AVATAR] Error: {e}")

        await asyncio.sleep(60)
