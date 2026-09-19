# =========================================================
# RANDOM WATERMARK (FILMYGREM STYLE)
# =========================================================

def add_watermark(image_bytes):

    _, _, watermark, enabled = get_settings()

    if not enabled:
        return image_bytes

    watermark = watermark.strip()

    if not watermark:
        return image_bytes

    try:
        image = Image.open(
            io.BytesIO(image_bytes)
        ).convert("RGBA")

        width, height = image.size

        # =================================================
        # VERY LARGE BOLD FONT SIZE (Matching reference)
        # =================================================
        font_size = max(
            50,
            int(width * 0.16)
        )

        font = get_font(font_size)
        draw = ImageDraw.Draw(image)

        # =================================================
        # TEXT SIZE & BOUNDING BOX
        # =================================================
        bbox = draw.textbbox(
            (0, 0),
            watermark,
            font=font
        )

        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        # Reduce font if text is too wide for image width
        max_text_width = int(width * 0.85)

        if text_width > max_text_width:
            ratio = max_text_width / text_width
            font_size = max(
                35,
                int(font_size * ratio)
            )
            font = get_font(font_size)

            bbox = draw.textbbox(
                (0, 0),
                watermark,
                font=font
            )
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]

        # =================================================
        # SAFE MARGINS FOR RANDOM POSITION
        # =================================================
        safe_margin_x = max(
            20,
            int(width * 0.05)
        )

        safe_margin_y = max(
            20,
            int(height * 0.05)
        )

        max_x = max(
            safe_margin_x,
            width - text_width - safe_margin_x - 40
        )

        max_y = max(
            safe_margin_y,
            height - text_height - safe_margin_y - 40
        )

        # Random position
        x = random.randint(
            safe_margin_x,
            max_x
        )

        y = random.randint(
            safe_margin_y,
            max_y
        )

        # =================================================
        # PADDING & WHITE BACKGROUND BOX
        # =================================================
        padding_x = max(
            20,
            int(width * 0.03)
        )

        padding_y = max(
            15,
            int(height * 0.02)
        )

        background_box = (
            max(0, x - padding_x),
            max(0, y - padding_y),
            min(width, x + text_width + padding_x),
            min(height, y + text_height + padding_y)
        )

        # White solid rectangle background
        draw.rectangle(
            background_box,
            fill=(255, 255, 255, 255)
        )

        # =================================================
        # BLACK BOLD TEXT
        # =================================================
        draw.text(
            (x, y - (bbox[1])),
            watermark,
            font=font,
            fill=(0, 0, 0, 255)
        )

        # =================================================
        # SAVE IMAGE
        # =================================================
        output = io.BytesIO()
        image = image.convert("RGB")

        image.save(
            output,
            format="JPEG",
            quality=95,
            optimize=True
        )

        output.seek(0)
        return output.getvalue()

    except Exception as e:
        print(f"Watermark error: {e}")
        return image_bytes
