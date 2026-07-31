def create_time_avatar(time_str: str, is_day: bool) -> io.BytesIO:
    """إنشاء تصميم عصري ديناميكي بأحجام نصوص ضخمة ومقروءة في تليجرام"""
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

    # 1. تكبير وسمك دوائر HUD الفضائية
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

    # 2. تكبير الإطار الزجاجي في المنتصف
    card_box = [center_x - 380, center_y - 300, center_x + 380, center_y + 300]
    draw.rounded_rectangle(
        card_box, radius=50, fill=(15, 23, 42, 210), outline=border_color, width=5
    )

    # 3. أحجام خطوط ضخمة جداً لتحقيق الوضوح (مع احجام احتياطية كبيرة)
    font_large = get_custom_font(240)
    font_sub = get_custom_font(52)
    font_small = get_custom_font(42)

    # النصوص
    title_text = f"CHANNEL EXCHANGE {mode_icon}"
    draw.text(
        (center_x, center_y - 200),
        title_text,
        fill=glow_color,
        font=font_sub,
        anchor="mm",
    )

    # الوقت بحجم عملاق بارز
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

    final_img = Image.alpha_composite(img.convert("RGBA"), overlay).convert(
        "RGB"
    )

    img_byte_arr = io.BytesIO()
    img_byte_arr.name = "avatar.jpg"
    final_img.save(img_byte_arr, format="JPEG", quality=95)
    img_byte_arr.seek(0)
    return img_byte_arr
