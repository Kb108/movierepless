import os
import re
import html
import sqlite3
import io

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
        SELECT source_url,
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
            "INSERT INTO channels (channel) VALUES (?)",
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
# BOLD REPLY
# =========================================================

async def send_bold_message(message, text):

    await message.reply_text(
        f"<b>{html.escape(str(text))}</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardRemove()
    )


# =========================================================
# TELEGRAM USERNAME + URL REPLACEMENT
# =========================================================

def replace_telegram_links(text):

    if not text:
        return text

    source_url, _, _, _ = get_settings()

    source_url = source_url.strip()

    if not source_url:
        return text

    # -----------------------------------------------------
    # Get source username from:
    #
    # https://t.me/MovieUpdateHD
    #
    # Result:
    # MovieUpdateHD
    # -----------------------------------------------------

    match = re.match(
        r"^https?://t\.me/([A-Za-z0-9_]+)",
        source_url,
        re.IGNORECASE
    )

    if not match:
        return text

    source_username = match.group(1)

    # -----------------------------------------------------
    # STEP 1
    #
    # Replace Telegram URL with Telegram URL
    #
    # https://t.me/OldChannel
    # ->
    # https://t.me/MovieUpdateHD
    #
    # Other URLs are untouched.
    # -----------------------------------------------------

    text = re.sub(
        r"https?://t\.me/[^\s<>()]+",
        source_url,
        text,
        flags=re.IGNORECASE
    )

    # -----------------------------------------------------
    # STEP 2
    #
    # Replace @username with @username
    #
    # @OldChannel
    # ->
    # @MovieUpdateHD
    #
    # -----------------------------------------------------

    text = re.sub(
        r"(?<![\w])@[A-Za-z0-9_]{5,32}\b",
        "@" + source_username,
        text
    )

    return text


# =========================================================
# FORMAT CAPTION
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
# WATERMARK FONT
# =========================================================

def get_font(size):

    possible_fonts = [

        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",

        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",

    ]

    for font_path in possible_fonts:

        if os.path.exists(font_path):

            return ImageFont.truetype(
                font_path,
                size
            )

    return ImageFont.load_default()


# =========================================================
# ADD WATERMARK TO POSTER
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

        # Watermark size based on image width
        font_size = max(
            24,
            int(width * 0.045)
        )

        font = get_font(font_size)

        draw = ImageDraw.Draw(image)

        # Text dimensions
        bbox = draw.textbbox(
            (0, 0),
            watermark,
            font=font
        )

        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        # Bottom-right margin
        margin = max(
            20,
            int(width * 0.025)
        )

        x = width - text_width - margin

        y = height - text_height - margin

        padding_x = max(
            10,
            int(width * 0.012)
        )

        padding_y = max(
            6,
            int(width * 0.008)
        )

        background_box = (
            x - padding_x,
            y - padding_y,
            x + text_width + padding_x,
            y + text_height + padding_y
        )

        # Semi-transparent black background
        draw.rounded_rectangle(
            background_box,
            radius=10,
            fill=(0, 0, 0, 150)
        )

        # White watermark
        draw.text(
            (x, y),
            watermark,
            font=font,
            fill=(255, 255, 255, 255)
        )

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

        print(
            f"Watermark error: {e}"
        )

        # If watermark processing fails,
        # return original image.
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
• Automatic poster watermark
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
# CHANNEL LIST
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
# SET SOURCE URL
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

    footer = " ".join(context.args)

    set_footer(footer)

    await send_bold_message(
        update.message,
        "✅ Footer updated successfully."
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

    text = "⚙️ SETTINGS\n\n"

    text += "📢 Source URL:\n"

    text += (
        source_url
        if source_url
        else "Not Set"
    )

    text += "\n\n🖼️ Watermark:\n"

    text += (
        watermark
        if watermark
        else "Not Set"
    )

    text += "\n\n🔘 Watermark Status:\n"

    text += (
        "ON ✅"
        if enabled
        else "OFF ❌"
    )

    text += "\n\n📝 Footer:\n"

    text += (
        footer
        if footer
        else "Not Set"
    )

    text += "\n\n📚 Source Channels:\n"

    if channel_list:

        for channel in channel_list:

            text += f"• {channel}\n"

    else:

        text += "No channels added."

    await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardRemove()
    )


# =========================================================
# PROCESS USER POST
# =========================================================

async def send_to_all_channels(
    update,
    context
):

    # Everyone can send posts

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
    # PHOTO / POSTER
    # =====================================================

    elif message.photo:

        try:

            photo = message.photo[-1]

            telegram_file = await context.bot.get_file(
                photo.file_id
            )

            image_bytes = await telegram_file.download_as_bytearray()

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
# TELEGRAM MENU
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

    # -------------------------
    # Commands
    # -------------------------

    application.add_handler(
        CommandHandler("start", start)
    )

    application.add_handler(
        CommandHandler("help", help_command)
    )

    application.add_handler(
        CommandHandler("addchannel", addchannel)
    )

    application.add_handler(
        CommandHandler("channels", channels)
    )

    application.add_handler(
        CommandHandler("removechannel", removechannel)
    )

    application.add_handler(
        CommandHandler("setsource", setsource)
    )

    application.add_handler(
        CommandHandler("setfooter", setfooter)
    )

    application.add_handler(
        CommandHandler("setwatermark", setwatermark)
    )

    application.add_handler(
        CommandHandler("watermark_on", watermark_on)
    )

    application.add_handler(
        CommandHandler("watermark_off", watermark_off)
    )

    application.add_handler(
        CommandHandler("settings", settings)
    )

    # -------------------------
    # User Posts
    # -------------------------

    application.add_handler(
        MessageHandler(
            filters.ALL & ~filters.COMMAND,
            send_to_all_channels
        )
    )

    print(
        "Movie Replace Bot is running..."
    )

    application.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


if __name__ == "__main__":
    main()
