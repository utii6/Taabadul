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

# مسار خط مخصص في مجلد المشروع (ضع أي خط تحبه هنا باسم font.ttf)
CUSTOM_FONT_PATH = "font.ttf"


def get_custom_font(size: int):
    """تحميل خط مخصص إذا كان موجوداً في المشروع، أو العودة للخط الافتراضي"""
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
    """إنشاء خلفية متدرجة فخمة"""
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
    """إنشاء تصميم عصري ديناميكي يتغير بين النهار والليل بأسلوب UI فخم"""
    width, height = 1024, 1024

    # 1. تحديث الألوان حسب النهار أو الليل
    if is_day:
        # ثيم النهار: أزرق سماوي مشرق إلى بنفسجي دافئ
        top_color = (15, 23, 60)  # Deep Navy Blue
        bottom_color = (88, 28, 135)  # Violet
        glow_color = (251, 191, 36, 180)  # Amber Gold Glow
        border_color = (245, 158, 11, 150)
        mode_icon = "☀️"
    else:
        # ثيم الليل: أزرق ملكي داكن إلى بنفسجي ليلى
        top_color = (10, 15, 40)  # Dark Royal Blue
        bottom_color = (35, 10, 65)  # Dark Cyber Purple
        glow_color = (56, 189, 248, 180)  # Cyber Cyan Glow
        border_color = (56, 189, 248, 120)
        mode_icon = "🌙"

    img = draw_gradient(width, height, top_color, bottom_color)

    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # 2. عناصر HUD الرقمية والدوارة
    center_x, center_y = width // 2, height // 2

    # دوائر HUD شفافة
    draw.ellipse(
        [center_x - 420, center_y - 420, center_x + 420, center_y + 420],
        outline=(glow_color[0], glow_color[1], glow_color[2], 50),
        width=3,
    )
    draw.ellipse(
        [center_x - 380, center_y - 380, center_x + 380, center_y + 380],
        outline=(168, 85, 247, 70),
        width=2,
    )

    # مؤشرات الدقائق المتوهجة
    for angle in range(0, 360, 30):
        rad = math.radians(angle)
        x1 = int(center_x + 400 * math.cos(rad))
        y1 = int(center_y + 400 * math.sin(rad))
        x2 = int(center_x + 415 * math.cos(rad))
        y2 = int(center_y + 415 * math.sin(rad))
        draw.line([(x1, y1), (x2, y2)], fill=glow_color, width=4)

    # 3. بطاقة زجاجية في المنتصف (Glassmorphism Effect)
    card_box = [center_x - 340, center_y - 250, center_x + 340, center_y + 250]
    draw.rounded_rectangle(
        card_box, radius=40, fill=(15, 23, 42, 190), outline=border_color, width=3
    )

    # 4. تحميل الخطوط المخصصة
    font_large = get_custom_font(130)
    font_sub = get_custom_font(38)
    font_small = get_custom_font(28)

    # العنوان العلوي
    title_text = f"CHANNEL EXCHANGE BOT {mode_icon}"
    draw.text(
        (center_x, center_y - 170),
        title_text,
        fill=glow_color,
        font=font_sub,
        anchor="mm",
    )

    # الساعة الرقمية الكبيرة HH:MM
    draw.text(
        (center_x, center_y - 20),
        time_str,
        fill=(255, 255, 255, 255),
        font=font_large,
        anchor="mm",
    )

    # حالة التحديث المباشر
    status_text = "⚡ UPDATED EVERY MINUTE ⚡"
    draw.text(
        (center_x, center_y + 150),
        status_text,
        fill=(168, 85, 247, 255),
        font=font_small,
        anchor="mm",
    )

    # دمج طبقات التصميم
    final_img = Image.alpha_composite(img.convert("RGBA"), overlay).convert(
        "RGB"
    )

    # حفظ النتيجة في الذاكرة لتمريرها لتليجرام
    img_byte_arr = io.BytesIO()
    img_byte_arr.name = "avatar.jpg"
    final_img.save(img_byte_arr, format="JPEG", quality=95)
    img_byte_arr.seek(0)
    return img_byte_arr


async def update_profile_every_minute(userbot_client):
    """تحديث اسم الحساب والصورة الفخمة مع تمييز الليل والنهار ودعم الخطوط"""
    while True:
        try:
            now = datetime.now(TIMEZONE)
            time_str = now.strftime("%I:%M")
            am_pm = "AM" if now.strftime("%p") == "AM" else "PM"

            # فحص ما إذا كان التوقيت نهاراً (6 ص - 6 م) أم ليلاً
            is_day = 6 <= now.hour < 18
            time_icon = "☀️" if is_day else "🌙"

            # 1. تحديث الاسم الأول للحساب
            new_name = f"{BASE_NAME} {time_icon} {time_str} {am_pm}"
            await userbot_client.update_profile(first_name=new_name)

            # 2. توليد صورة التوقيت بالألوان والخط المناسب
            avatar_bytes = create_time_avatar(time_str, is_day)

            # 3. رفع الصورة مباشرة وتراكمها في الألبوم
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
