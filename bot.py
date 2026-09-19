import os
import re
import html
import sqlite3
import io
import random

from PIL import Image, ImageDraw, ImageFont

from telegram import (
    Update,
    ReplyKeyboardRemove,
    BotCommand,
    MenuButtonCommands,
)

from telegram.constants import ParseMode

from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)


# =========================================================
# CONFIG
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID_RAW = os.getenv("ADMIN_ID", "").strip()

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is missing")

if not ADMIN_ID_RAW:
    raise ValueError("ADMIN_ID is missing")

try:
    ADMIN_ID = int(ADMIN_ID_RAW)
except ValueError:
    raise ValueError("ADMIN_ID must be a numeric Telegram User ID")


DB_FILE = "bot.db"


# =========================================================
# DATABASE
# =========================================================

def db():
    return sqlite3.connect(DB_FILE)


def init_db():

    conn = db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel TEXT UNIQUE NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            source_url TEXT DEFAULT '',
            footer TEXT DEFAULT '',
            watermark TEXT DEFAULT '@MovieUpdateHD',
            watermark_enabled INTEGER DEFAULT 1
        )
    """)

    cur.execute("""
        INSERT OR IGNORE INTO settings
        (id, source_url, footer, watermark, watermark_enabled)
        VALUES
        (1, '', '', '@MovieUpdateHD', 1)
    """)

    conn.commit()
    conn.close()


# =========================================================
# SETTINGS
# =========================================================

def get_settings():

    conn = db()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            source_url,
            footer,
            watermark,
            watermark_enabled
        FROM settings
        WHERE id = 1
    """)

    row = cur.fetchone()

    conn.close()

    if not row:
        return "", "", "@MovieUpdateHD", 1

    return row


def set_source_url(url):

    conn = db()
    cur = conn.cursor()

    cur.execute("""
        UPDATE settings
        SET source_url = ?
        WHERE id = 1
    """, (url,))

    conn.commit()
    conn.close()


def set_footer(footer):

    conn = db()
    cur = conn.cursor()

    cur.execute("""
        UPDATE settings
        SET footer = ?
        WHERE id = 1
    """, (footer,))

    conn.commit()
    conn.close()


def set_watermark(text):

    conn = db()
    cur = conn.cursor()

    cur.execute("""
        UPDATE settings
        SET watermark = ?
        WHERE id = 1
    """, (text,))

    conn.commit()
    conn.close()


def set_watermark_enabled(enabled):

    conn = db()
    cur = conn.cursor()

    cur.execute("""
        UPDATE settings
        SET watermark_enabled = ?
        WHERE id = 1
    """, (1 if enabled else 0,))

    conn.commit()
    conn.close()


# =========================================================
# CHANNELS
# =========================================================

def get_channels():

    conn = db()
    cur = conn.cursor()

    cur.execute("""
        SELECT channel
        FROM channels
        ORDER BY id ASC
    """)

    rows = cur.fetchall()

    conn.close()

    return [row[0] for row in rows]


def add_channel(channel):

    conn = db()
    cur = conn.cursor()

    try:

        cur.execute(
            "INSERT INTO channels (channel) VALUES (?)"
            (channel,)
        )

        conn.commit()

        result = True

    except sqlite3.IntegrityError:

        result = False

    conn.close()

    return result


def remove_channel(channel):

    conn = db()
    cur = conn.cursor()

    cur.execute(
        "DELETE FROM channels WHERE channel = ?",
        (channel,)
    )

    deleted = cur.rowcount > 0

    conn.commit()
    conn.close()

    return deleted


# =========================================================
# ADMIN
# =========================================================

def is_admin(update):

    if not update.effective_user:
        return False

    return update.effective_user.id == ADMIN_ID


async def admin_only(update):

    if not is_admin(update):

        if update.message:

            await update.message.reply_text(
                "<b>❌ This command is available only to the bot owner.</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=ReplyKeyboardRemove()
            )

        return False

    return True


# =========================================================
# BOLD MESSAGE
# =========================================================

async def send_bold_message(message, text):

    await message.reply_text(
        f"<b>{html.escape(str(text))}</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardRemove()
    )


# =========================================================
# TELEGRAM REPLACEMENT
# =========================================================

def replace_telegram_links(text):

    if not text:
        return text

    source_url, _, _, _ = get_settings()

    source_url = source_url.strip()

    if not source_url:
        return text

    match = re.match(
        r"^https?://t\.me/([A-Za-z0-9_]+)",
        source_url,
        re.IGNORECASE
    )

    if not match:
        return text

    source_username = match.group(1)

    # Replace Telegram links
    text = re.sub(
        r"https?://t\.me/[^\s<>()]+",
        source_url,
        text,
        flags=re.IGNORECASE
    )

    # Replace Telegram usernames
    text = re.sub(
        r"(?<![\w])@[A-Za-z0-9_]{5,32}\b",
        "@" + source_username,
        text
    )

    return text


# =========================================================
# CAPTION
# =========================================================

def format_caption(text):

    if not text:
        return ""

    result = replace_telegram_links(text)

    _, footer, _, _ = get_settings()

    footer = footer.strip()

    if footer:

        result += "\n\n" + footer

    result = html.escape(result)

    return f"<b>{result}</b>"


# =========================================================
# FONT LOADER
# =========================================================

def get_font(size):

    possible_fonts = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "C:\\Windows\\Fonts\\arialbd.ttf"
    ]

    for font_path in possible_fonts:
        if os.path.exists(font_path):
            try:
                return ImageFont.truetype(font_path, size)
            except Exception:
                continue

    return ImageFont.load_default()


# =========================================================
# EXTRA LARGE WATERMARK (FILMYGREM EXACT STYLE)
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

        # -------------------------------------------------
        # EXTRA LARGE DYNAMIC FONT SIZE
        # -------------------------------------------------
        # ছবির প্রস্থের ৩০% ধরে বিশাল ফন্ট তৈরি করা হবে
        font_size = int(width * 0.30)
        font = get_font(font_size)

        draw = ImageDraw.Draw(image)

        # লেখাটির প্রকৃত মাপ জানা
        bbox = draw.textbbox((0, 0), watermark, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        # লেখাটি যদি ছবির প্রস্থের চেয়ে বড় হয়ে যায়, তবে মানানসই আকারে নিয়ে আসা
        max_allowed_width = int(width * 0.82)

        while text_width > max_allowed_width and font_size > 20:
            font_size -= 4
            font = get_font(font_size)
            bbox = draw.textbbox((0, 0), watermark, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]

        # -------------------------------------------------
        # PADDING & MARGINS
        # -------------------------------------------------
        padding_x = int(font_size * 0.25)
        padding_y = int(font_size * 0.15)

        safe_margin_x = max(10, int(width * 0.02))
        safe_margin_y = max(10, int(height * 0.02))

        box_width = text_width + (padding_x * 2)
        box_height = text_height + (padding_y * 2)

        max_x = max(safe_margin_x, width - box_width - safe_margin_x)
        max_y = max(safe_margin_y, height - box_height - safe_margin_y)

        # -------------------------------------------------
        # RANDOM POSITION
        # -------------------------------------------------
        x = random.randint(safe_margin_x, max_x)
        y = random.randint(safe_margin_y, max_y)

        # -------------------------------------------------
        # WHITE SOLID BACKGROUND BOX
        # -------------------------------------------------
        background_box = (
            x,
            y,
            x + box_width,
            y + box_height
        )

        draw.rectangle(
            background_box,
            fill=(255, 255, 255, 255)
        )

        # -------------------------------------------------
        # BOLD BLACK TEXT
        # -------------------------------------------------
        text_x = x + padding_x - bbox[0]
        text_y = y + padding_y - bbox[1]

        draw.text(
            (text_x, text_y),
            watermark,
            font=font,
            fill=(0, 0, 0, 255)
        )

        # -------------------------------------------------
        # SAVE IMAGE
        # -------------------------------------------------
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


# =========================================================
# START
# =========================================================

async def start(update, context):

    text = """
🎬 <b>MOVIE REPLACE BOT</b>

🚀 <b>Automate Your Movie Channel!</b>

💰 <b>Only ₹20/Month</b>

🎥 Send your movie post
🤖 Bot processes it
📢 Automatically posts to your Source Channel

✨ <b>Features:</b>

• Replace Telegram usernames & links
• Keep movie/download URLs unchanged
• Large random poster watermark
• Customize caption
• Multiple Source Channels

📩 <b>Need this bot?</b>

👉 Contact: <b>@share_kb</b>
"""

    await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardRemove()
    )


# =========================================================
# HELP
# =========================================================

async def help_command(update, context):

    text = """
<b>🎬 MOVIE REPLACE BOT</b>

<b>For Users:</b>

Send your movie post to the bot.

<b>Admin Commands:</b>

/addchannel @channel

/channels

/removechannel @channel

/setsource https://t.me/YourSource

/setfooter Your footer

/setwatermark @MovieUpdateHD

/watermark_on

/watermark_off

/settings
"""

    await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardRemove()
    )


# =========================================================
# ADD CHANNEL
# =========================================================

async def addchannel(update, context):

    if not await admin_only(update):
        return

    if not context.args:

        await send_bold_message(
            update.message,
            "Usage:\n/addchannel @YourChannel"
        )

        return

    channel = context.args[0].strip()

    if add_channel(channel):

        await send_bold_message(
            update.message,
            f"✅ Source Channel added:\n{channel}"
        )

    else:

        await send_bold_message(
            update.message,
            "⚠️ This channel is already added."
        )


# =========================================================
# CHANNELS
# =========================================================

async def channels(update, context):

    if not await admin_only(update):
        return

    channel_list = get_channels()

    if not channel_list:

        await send_bold_message(
            update.message,
            "❌ No Source Channel added yet."
        )

        return

    text = "📢 Source Channels:\n\n"

    for index, channel in enumerate(
        channel_list,
        start=1
    ):

        text += f"{index}. {channel}\n"

    await send_bold_message(
        update.message,
        text
    )


# =========================================================
# REMOVE CHANNEL
# =========================================================

async def removechannel(update, context):

    if not await admin_only(update):
        return

    if not context.args:

        await send_bold_message(
            update.message,
            "Usage:\n/removechannel @YourChannel"
        )

        return

    channel = context.args[0].strip()

    if remove_channel(channel):

        await send_bold_message(
            update.message,
            f"✅ Channel removed:\n{channel}"
        )

    else:

        await send_bold_message(
            update.message,
            "❌ Channel not found."
        )


# =========================================================
# SET SOURCE
# =========================================================

async def setsource(update, context):

    if not await admin_only(update):
        return

    if not context.args:

        await send_bold_message(
            update.message,
            "Usage:\n/setsource https://t.me/YourSourceChannel"
        )

        return

    source_url = context.args[0].strip()

    if not re.match(
        r"^https?://t\.me/",
        source_url,
        re.IGNORECASE
    ):

        await send_bold_message(
            update.message,
            "❌ Please provide a valid Telegram URL."
        )

        return

    set_source_url(source_url)

    await send_bold_message(
        update.message,
        f"✅ Telegram Source URL saved:\n{source_url}"
    )


# =========================================================
# SET FOOTER
# =========================================================

async def setfooter(update, context):

    if not await admin_only(update):
        return

    if not context.args:

        await send_bold_message(
            update.message,
            "Usage:\n/setfooter Your footer text"
        )

        return

    footer = " ".join(context.args).strip()

    set_footer(footer)

    await update.message.reply_text(
        "<b>✅ Footer updated successfully.</b>\n\n"
        "<b>Saved Footer:</b>\n"
        + html.escape(footer),
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardRemove()
    )


# =========================================================
# SET WATERMARK
# =========================================================

async def setwatermark(update, context):

    if not await admin_only(update):
        return

    if not context.args:

        await send_bold_message(
            update.message,
            "Usage:\n/setwatermark @MovieUpdateHD"
        )

        return

    watermark = " ".join(
        context.args
    ).strip()

    set_watermark(watermark)

    await send_bold_message(
        update.message,
        f"✅ Watermark changed to:\n{watermark}"
    )


# =========================================================
# WATERMARK ON
# =========================================================

async def watermark_on(update, context):

    if not await admin_only(update):
        return

    set_watermark_enabled(True)

    await send_bold_message(
        update.message,
        "✅ Poster watermark is now ON."
    )


# =========================================================
# WATERMARK OFF
# =========================================================

async def watermark_off(update, context):

    if not await admin_only(update):
        return

    set_watermark_enabled(False)

    await send_bold_message(
        update.message,
        "❌ Poster watermark is now OFF."
    )


# =========================================================
# SETTINGS
# =========================================================

async def settings(update, context):

    if not await admin_only(update):
        return

    source_url, footer, watermark, enabled = get_settings()

    channel_list = get_channels()

    safe_source = html.escape(
        source_url.strip()
    ) if source_url else "Not Set"

    safe_footer = html.escape(
        footer.strip()
    ) if footer else "Not Set"

    safe_watermark = html.escape(
        watermark.strip()
    ) if watermark else "Not Set"

    text = (
        "⚙️ <b>SETTINGS</b>\n\n"

        "📢 <b>Source URL:</b>\n"
        f"{safe_source}\n\n"

        "🖼️ <b>Watermark:</b>\n"
        f"{safe_watermark}\n\n"

        "🔘 <b>Watermark Status:</b>\n"
        f"{'ON ✅' if enabled else 'OFF ❌'}\n\n"

        "📝 <b>Footer:</b>\n"
        f"{safe_footer}\n\n"

        "📚 <b>Source Channels:</b>\n"
    )

    if channel_list:

        for channel in channel_list:

            text += (
                f"• {html.escape(channel)}\n"
            )

    else:

        text += "No channels added."

    await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardRemove()
    )


# =========================================================
# SEND POST
# =========================================================

async def send_to_all_channels(
    update,
    context
):

    if not update.message:
        return

    channel_list = get_channels()

    if not channel_list:

        await send_bold_message(
            update.message,
            "⚠️ The bot is not configured yet.\nPlease contact @share_kb"
        )

        return

    message = update.message


    # =====================================================
    # TEXT
    # =====================================================

    if message.text:

        formatted_text = format_caption(
            message.text
        )

        for channel in channel_list:

            try:

                await context.bot.send_message(
                    chat_id=channel,
                    text=formatted_text,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=False
                )

            except Exception as e:

                print(
                    f"Text error {channel}: {e}"
                )


    # =====================================================
    # PHOTO
    # =====================================================

    elif message.photo:

        try:

            photo = message.photo[-1]

            telegram_file = await context.bot.get_file(
                photo.file_id
            )

            image_bytes = await telegram_file.download_as_bytearray()

            # Process image with watermark
            processed_image = add_watermark(
                bytes(image_bytes)
            )

            caption = format_caption(
                message.caption
            )

            for channel in channel_list:

                try:

                    photo_file = io.BytesIO(
                        processed_image
                    )

                    photo_file.name = "MovieUpdateHD.jpg"

                    await context.bot.send_photo(
                        chat_id=channel,
                        photo=photo_file,
                        caption=caption if caption else None,
                        parse_mode=ParseMode.HTML
                    )

                except Exception as e:

                    print(
                        f"Photo send error {channel}: {e}"
                    )

        except Exception as e:

            print(
                f"Poster processing error: {e}"
            )

            caption = format_caption(
                message.caption
            )

            for channel in channel_list:

                try:

                    await context.bot.send_photo(
                        chat_id=channel,
                        photo=message.photo[-1].file_id,
                        caption=caption if caption else None,
                        parse_mode=ParseMode.HTML
                    )

                except Exception as e:

                    print(
                        f"Fallback photo error {channel}: {e}"
                    )


    # =====================================================
    # VIDEO
    # =====================================================

    elif message.video:

        caption = format_caption(
            message.caption
        )

        for channel in channel_list:

            try:

                await context.bot.send_video(
                    chat_id=channel,
                    video=message.video.file_id,
                    caption=caption if caption else None,
                    parse_mode=ParseMode.HTML
                )

            except Exception as e:

                print(
                    f"Video error {channel}: {e}"
                )


    # =====================================================
    # DOCUMENT
    # =====================================================

    elif message.document:

        caption = format_caption(
            message.caption
        )

        for channel in channel_list:

            try:

                await context.bot.send_document(
                    chat_id=channel,
                    document=message.document.file_id,
                    caption=caption if caption else None,
                    parse_mode=ParseMode.HTML
                )

            except Exception as e:

                print(
                    f"Document error {channel}: {e}"
                )


    # =====================================================
    # AUDIO
    # =====================================================

    elif message.audio:

        caption = format_caption(
            message.caption
        )

        for channel in channel_list:

            try:

                await context.bot.send_audio(
                    chat_id=channel,
                    audio=message.audio.file_id,
                    caption=caption if caption else None,
                    parse_mode=ParseMode.HTML
                )

            except Exception as e:

                print(
                    f"Audio error {channel}: {e}"
                )


    # =====================================================
    # VOICE
    # =====================================================

    elif message.voice:

        for channel in channel_list:

            try:

                await context.bot.send_voice(
                    chat_id=channel,
                    voice=message.voice.file_id
                )

            except Exception as e:

                print(
                    f"Voice error {channel}: {e}"
                )


    # =====================================================
    # OTHER
    # =====================================================

    else:

        for channel in channel_list:

            try:

                await context.bot.copy_message(
                    chat_id=channel,
                    from_chat_id=message.chat_id,
                    message_id=message.message_id
                )

            except Exception as e:

                print(
                    f"Copy error {channel}: {e}"
                )


    # =====================================================
    # SUCCESS
    # =====================================================

    await send_bold_message(
        update.message,
        "✅ Your post has been processed successfully."
    )


# =========================================================
# BOT MENU
# =========================================================

async def setup_bot(application):

    commands = [

        BotCommand(
            "start",
            "Start the bot"
        ),

        BotCommand(
            "help",
            "Help"
        ),

        BotCommand(
            "addchannel",
            "Add Source Channel"
        ),

        BotCommand(
            "channels",
            "Show Source Channels"
        ),

        BotCommand(
            "removechannel",
            "Remove Source Channel"
        ),

        BotCommand(
            "setsource",
            "Set Telegram Source URL"
        ),

        BotCommand(
            "setfooter",
            "Set Footer"
        ),

        BotCommand(
            "setwatermark",
            "Change Watermark"
        ),

        BotCommand(
            "watermark_on",
            "Enable Watermark"
        ),

        BotCommand(
            "watermark_off",
            "Disable Watermark"
        ),

        BotCommand(
            "settings",
            "Show Settings"
        ),
    ]

    await application.bot.set_my_commands(
        commands
    )

    await application.bot.set_chat_menu_button(
        menu_button=MenuButtonCommands()
    )


# =========================================================
# MAIN
# =========================================================

def main():

    init_db()

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(setup_bot)
        .build()
    )

    # Command Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("addchannel", addchannel))
    application.add_handler(CommandHandler("channels", channels))
    application.add_handler(CommandHandler("removechannel", removechannel))
    application.add_handler(CommandHandler("setsource", setsource))
    application.add_handler(CommandHandler("setfooter", setfooter))
    application.add_handler(CommandHandler("setwatermark", setwatermark))
    application.add_handler(CommandHandler("watermark_on", watermark_on))
    application.add_handler(CommandHandler("watermark_off", watermark_off))
    application.add_handler(CommandHandler("settings", settings))

    # All non-command messages
    application.add_handler(
        MessageHandler(
            filters.ALL & ~filters.COMMAND,
            send_to_all_channels
        )
    )

    print("Movie Replace Bot is running...")

    application.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


if __name__ == "__main__":
    main()
