import os
import re
import html
import sqlite3
from telegram import Update, ReplyKeyboardRemove, BotCommand, MenuButtonCommands
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
            footer TEXT DEFAULT ''
        )
    """)

    cur.execute("""
        INSERT OR IGNORE INTO settings
        (id, source_url, footer)
        VALUES (1, '', '')
    """)

    conn.commit()
    conn.close()


# =========================================================
# SETTINGS
# =========================================================

def get_source_url():
    conn = db()
    cur = conn.cursor()

    cur.execute("""
        SELECT source_url
        FROM settings
        WHERE id = 1
    """)

    row = cur.fetchone()
    conn.close()

    return row[0] if row else ""


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


def get_footer():
    conn = db()
    cur = conn.cursor()

    cur.execute("""
        SELECT footer
        FROM settings
        WHERE id = 1
    """)

    row = cur.fetchone()
    conn.close()

    return row[0] if row else ""


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
        cur.execute("""
            INSERT INTO channels (channel)
            VALUES (?)
        """, (channel,))

        conn.commit()
        result = True

    except sqlite3.IntegrityError:
        result = False

    conn.close()
    return result


def remove_channel(channel):
    conn = db()
    cur = conn.cursor()

    cur.execute("""
        DELETE FROM channels
        WHERE channel = ?
    """, (channel,))

    deleted = cur.rowcount > 0

    conn.commit()
    conn.close()

    return deleted


# =========================================================
# ADMIN
# =========================================================

def is_admin(update: Update):
    if not update.effective_user:
        return False

    return update.effective_user.id == ADMIN_ID


async def admin_only(update: Update):
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
# TEXT FORMAT
# =========================================================

def escape_bold(text):
    if not text:
        return ""

    return html.escape(str(text))


def replace_telegram_links(text):
    """
    IMPORTANT:
    Only Telegram t.me links are replaced.

    Examples replaced:
    https://t.me/addlist/xxxxx
    https://t.me/xxxxx
    https://t.me/xxxxx/123

    Movie/download links such as:
    terasharefile.com
    terabox.com
    drive.google.com
    mega.nz
    etc.
    are NOT touched.
    """

    if not text:
        return text

    source_url = get_source_url().strip()

    if not source_url:
        return text

    # Telegram links only
    telegram_pattern = re.compile(
        r"https?://t\.me/[^\s<>()]+",
        re.IGNORECASE
    )

    return telegram_pattern.sub(source_url, text)


def format_caption(text):
    if not text:
        return ""

    # First replace ONLY Telegram links
    result = replace_telegram_links(text)

    footer = get_footer().strip()

    if footer:
        result += "\n\n" + footer

    # Escape HTML so user text doesn't break formatting
    result = html.escape(result)

    # Entire caption bold
    return f"<b>{result}</b>"


# =========================================================
# SEND MESSAGE
# =========================================================

async def send_bold_message(message, text):
    await message.reply_text(
        f"<b>{html.escape(text)}</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardRemove()
    )


# =========================================================
# START
# =========================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = """
🎬 <b>MOVIE REPLACE BOT</b>

🚀 <b>Automate Your Movie Channel!</b>

💰 <b>Bot Service — Only ₹20/Month</b>

🎥 Send your movie post to the bot
🤖 Our bot automatically processes it
📢 The post is sent to your Source Channel

✨ <b>Features:</b>
• Replace Telegram source links
• Keep movie/download URLs unchanged
• Customize caption
• Automatic channel posting
• Multiple Source Channels supported

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

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = """
<b>🎬 MOVIE REPLACE BOT</b>

<b>For Users:</b>
Send your movie post to the bot.

<b>For Admin:</b>

/addchannel
/addchannel @channelusername

/channels
/removechannel @channelusername

/setsource
/setsource https://t.me/YourSource

/setfooter
/setfooter Your footer text

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

async def addchannel(update: Update, context: ContextTypes.DEFAULT_TYPE):

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

async def channels(update: Update, context: ContextTypes.DEFAULT_TYPE):

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

    for index, channel in enumerate(channel_list, start=1):
        text += f"{index}. {channel}\n"

    await send_bold_message(
        update.message,
        text
    )


# =========================================================
# REMOVE CHANNEL
# =========================================================

async def removechannel(update: Update, context: ContextTypes.DEFAULT_TYPE):

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

async def setsource(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not await admin_only(update):
        return

    if not context.args:
        await send_bold_message(
            update.message,
            "Usage:\n/setsource https://t.me/YourSourceChannel"
        )
        return

    source_url = context.args[0].strip()

    # Basic validation
    if not re.match(r"^https?://t\.me/", source_url, re.IGNORECASE):
        await send_bold_message(
            update.message,
            "❌ Please provide a valid Telegram URL.\n\nExample:\nhttps://t.me/YourSourceChannel"
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

async def setfooter(update: Update, context: ContextTypes.DEFAULT_TYPE):

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
# SETTINGS
# =========================================================

async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not await admin_only(update):
        return

    source_url = get_source_url()
    footer = get_footer()
    channel_list = get_channels()

    text = "⚙️ SETTINGS\n\n"

    text += "📢 Telegram Source URL:\n"
    text += f"{source_url if source_url else 'Not Set'}\n\n"

    text += "📝 Footer:\n"
    text += f"{footer if footer else 'Not Set'}\n\n"

    text += "📚 Source Channels:\n"

    if channel_list:
        for channel in channel_list:
            text += f"• {channel}\n"
    else:
        text += "No channels added."

    await send_bold_message(
        update.message,
        text
    )


# =========================================================
# PROCESS USER POST
# =========================================================

async def send_to_all_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):

    # IMPORTANT:
    # No admin check here.
    # Everyone can send a post to the bot.

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

        formatted_text = format_caption(message.text)

        for channel in channel_list:
            try:
                await context.bot.send_message(
                    chat_id=channel,
                    text=formatted_text,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=False
                )

            except Exception as e:
                print(f"Channel error {channel}: {e}")

    # =====================================================
    # PHOTO
    # =====================================================

    elif message.photo:

        caption = format_caption(message.caption)

        for channel in channel_list:
            try:
                await context.bot.send_photo(
                    chat_id=channel,
                    photo=message.photo[-1].file_id,
                    caption=caption if caption else None,
                    parse_mode=ParseMode.HTML
                )

            except Exception as e:
                print(f"Photo error {channel}: {e}")

    # =====================================================
    # VIDEO
    # =====================================================

    elif message.video:

        caption = format_caption(message.caption)

        for channel in channel_list:
            try:
                await context.bot.send_video(
                    chat_id=channel,
                    video=message.video.file_id,
                    caption=caption if caption else None,
                    parse_mode=ParseMode.HTML
                )

            except Exception as e:
                print(f"Video error {channel}: {e}")

    # =====================================================
    # DOCUMENT
    # =====================================================

    elif message.document:

        caption = format_caption(message.caption)

        for channel in channel_list:
            try:
                await context.bot.send_document(
                    chat_id=channel,
                    document=message.document.file_id,
                    caption=caption if caption else None,
                    parse_mode=ParseMode.HTML
                )

            except Exception as e:
                print(f"Document error {channel}: {e}")

    # =====================================================
    # AUDIO
    # =====================================================

    elif message.audio:

        caption = format_caption(message.caption)

        for channel in channel_list:
            try:
                await context.bot.send_audio(
                    chat_id=channel,
                    audio=message.audio.file_id,
                    caption=caption if caption else None,
                    parse_mode=ParseMode.HTML
                )

            except Exception as e:
                print(f"Audio error {channel}: {e}")

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
                print(f"Voice error {channel}: {e}")

    # =====================================================
    # OTHER MESSAGE TYPES
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
                print(f"Copy error {channel}: {e}")

    # =====================================================
    # USER CONFIRMATION
    # =====================================================

    await send_bold_message(
        update.message,
        "✅ Your post has been processed successfully."
    )


# =========================================================
# BOT COMMAND MENU
# =========================================================

async def setup_bot(application):

    commands = [
        BotCommand("start", "Start the bot"),
        BotCommand("help", "Help"),
        BotCommand("addchannel", "Add Source Channel"),
        BotCommand("channels", "Show Source Channels"),
        BotCommand("removechannel", "Remove Source Channel"),
        BotCommand("setsource", "Set Telegram Source URL"),
        BotCommand("setfooter", "Set Footer"),
        BotCommand("settings", "Show Settings"),
    ]

    await application.bot.set_my_commands(commands)

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

    # Commands
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
        CommandHandler("settings", settings)
    )

    # ALL users can send posts
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
