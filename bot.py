import os
import re
import sqlite3
import logging

from telegram import Update, BotCommand
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

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

DB_FILE = "bot.db"

DEFAULT_FOOTER = """Join Backup Channel ❤️👇
@backup_stor

Best loot offers 🛍️ 🤝 💸
📌 @loot_dells
📌 @loot_dells"""


# =========================================================
# LOGGING
# =========================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

logger = logging.getLogger(__name__)


# =========================================================
# DATABASE
# =========================================================

def get_db():
    return sqlite3.connect(DB_FILE)


def init_db():

    conn = get_db()
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
            replace_text TEXT DEFAULT '',
            footer TEXT DEFAULT ''
        )
    """)

    cur.execute("""
        INSERT OR IGNORE INTO settings
        (id, replace_text, footer)
        VALUES (1, '', ?)
    """, (DEFAULT_FOOTER,))

    conn.commit()
    conn.close()


# =========================================================
# SETTINGS
# =========================================================

def get_settings():

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT replace_text, footer
        FROM settings
        WHERE id = 1
    """)

    row = cur.fetchone()

    conn.close()

    if not row:
        return "", DEFAULT_FOOTER

    return row[0] or "", row[1] or ""


def update_setting(column, value):

    allowed = {
        "replace_text",
        "footer"
    }

    if column not in allowed:
        return

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        f"UPDATE settings SET {column} = ? WHERE id = 1",
        (value,)
    )

    conn.commit()
    conn.close()


# =========================================================
# CHANNEL FUNCTIONS
# =========================================================

def add_channel(channel):

    conn = get_db()
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

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "DELETE FROM channels WHERE channel = ?",
        (channel,)
    )

    deleted = cur.rowcount

    conn.commit()
    conn.close()

    return deleted > 0


def get_channels():

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "SELECT channel FROM channels ORDER BY id ASC"
    )

    rows = cur.fetchall()

    conn.close()

    return [row[0] for row in rows]


# =========================================================
# ADMIN CHECK
# =========================================================

def is_admin(update):

    if not update.effective_user:
        return False

    return update.effective_user.id == ADMIN_ID


async def check_admin(update):

    if not is_admin(update):

        if update.message:
            await update.message.reply_text(
                "❌ You are not authorized to use this bot."
            )

        return False

    return True


# =========================================================
# TELEGRAM MENU
# =========================================================

async def setup_commands(app):

    commands = [

        BotCommand(
            "start",
            "🚀 Start bot"
        ),

        BotCommand(
            "help",
            "❓ Help"
        ),

        BotCommand(
            "addchannel",
            "📢 Add Source Channel"
        ),

        BotCommand(
            "channels",
            "📋 My Source Channels"
        ),

        BotCommand(
            "removechannel",
            "🗑️ Remove Channel"
        ),

        BotCommand(
            "setreplace",
            "🔄 Set Replace Text"
        ),

        BotCommand(
            "setfooter",
            "📝 Set Footer"
        ),

        BotCommand(
            "settings",
            "⚙️ Settings"
        )
    ]

    await app.bot.set_my_commands(commands)


# =========================================================
# START
# =========================================================

async def start(update, context):

    if not await check_admin(update):
        return

    await update.message.reply_text(
        """🎬 Movie Auto Poster Bot

Send your movie post directly to this bot.

The bot will automatically:

✅ Make text Bold
✅ Keep TeraBox URLs unchanged
✅ Replace configured source text
✅ Add your footer
✅ Post to ALL added Source Channels

Use the ☰ Menu for settings."""
    )


# =========================================================
# HELP
# =========================================================

async def help_command(update, context):

    if not await check_admin(update):
        return

    await update.message.reply_text(
        """🛠️ HELP

/addchannel
Add a Source Channel.

/channels
See all Source Channels.

/removechannel
Remove a Source Channel.

/setreplace
Set text/username to replace.

/setfooter
Set your automatic footer.

/settings
View current settings.

For posting:
Just send your movie text, photo, video or document directly to this bot."""
    )


# =========================================================
# ADD CHANNEL
# =========================================================

async def add_channel_command(update, context):

    if not await check_admin(update):
        return

    if not context.args:

        context.user_data["waiting_for"] = "add_channel"

        await update.message.reply_text(
            """📢 Send your Source Channel username.

Example:

@MovieSourceHD

Make sure the bot is Admin in that Channel."""
        )

        return

    channel = context.args[0].strip()

    if not channel.startswith("@"):
        channel = "@" + channel

    if add_channel(channel):

        await update.message.reply_text(
            f"✅ Channel added successfully:\n{channel}"
        )

    else:

        await update.message.reply_text(
            "⚠️ This channel is already added."
        )


# =========================================================
# CHANNEL LIST
# =========================================================

async def channels_command(update, context):

    if not await check_admin(update):
        return

    channels = get_channels()

    if not channels:

        await update.message.reply_text(
            "📋 No Source Channels added yet."
        )

        return

    text = "📋 Your Source Channels:\n\n"

    for i, channel in enumerate(channels, 1):

        text += f"{i}. {channel}\n"

    await update.message.reply_text(text)


# =========================================================
# REMOVE CHANNEL
# =========================================================

async def remove_channel_command(update, context):

    if not await check_admin(update):
        return

    if not context.args:

        context.user_data["waiting_for"] = "remove_channel"

        await update.message.reply_text(
            """🗑️ Send the Channel username you want to remove.

Example:

@MovieSourceHD"""
        )

        return

    channel = context.args[0].strip()

    if not channel.startswith("@"):
        channel = "@" + channel

    if remove_channel(channel):

        await update.message.reply_text(
            f"✅ Channel removed:\n{channel}"
        )

    else:

        await update.message.reply_text(
            "❌ Channel not found."
        )


# =========================================================
# SET REPLACE
# =========================================================

async def set_replace_command(update, context):

    if not await check_admin(update):
        return

    if not context.args:

        context.user_data["waiting_for"] = "set_replace"

        await update.message.reply_text(
            """🔄 Send the username/text that should be replaced.

Example:

@OldChannel"""
        )

        return

    value = " ".join(context.args).strip()

    update_setting(
        "replace_text",
        value
    )

    await update.message.reply_text(
        f"✅ Replace text saved:\n{value}"
    )


# =========================================================
# SET FOOTER
# =========================================================

async def set_footer_command(update, context):

    if not await check_admin(update):
        return

    if not context.args:

        context.user_data["waiting_for"] = "set_footer"

        await update.message.reply_text(
            """📝 Send your complete footer.

Example:

Join Backup Channel ❤️👇
@backup_stor

Best loot offers 🛍️ 🤝 💸
📌 @loot_dells
📌 @loot_dells"""
        )

        return

    footer = " ".join(context.args)

    update_setting(
        "footer",
        footer
    )

    await update.message.reply_text(
        "✅ Footer saved successfully."
    )


# =========================================================
# SETTINGS
# =========================================================

async def settings_command(update, context):

    if not await check_admin(update):
        return

    channels = get_channels()

    replace_text, footer = get_settings()

    if channels:

        channel_text = "\n".join(
            f"• {channel}"
            for channel in channels
        )

    else:

        channel_text = "❌ None"

    if not replace_text:
        replace_text = "❌ None"

    await update.message.reply_text(
        f"""⚙️ CURRENT SETTINGS

📢 Source Channels:

{channel_text}

🔄 Replace Text:
{replace_text}

📝 Footer:

{footer}"""
    )


# =========================================================
# HTML ESCAPE
# =========================================================

def escape_html(text):

    if not text:
        return ""

    return (
        text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


# =========================================================
# FORMAT POST
# =========================================================

def format_post(text):

    if not text:
        text = ""

    replace_text, footer = get_settings()

    channels = get_channels()

    # -----------------------------------------------------
    # Replace source text
    # -----------------------------------------------------

    if replace_text and channels:

        replacement = channels[0]

        text = text.replace(
            replace_text,
            replacement
        )

    # -----------------------------------------------------
    # Footer
    # -----------------------------------------------------

    if footer:

        if footer.strip() not in text:

            if text.strip():

                text = (
                    text.rstrip()
                    + "\n\n"
                    + footer
                )

            else:

                text = footer

    # -----------------------------------------------------
    # Bold everything except URLs
    # -----------------------------------------------------

    parts = re.split(
        r"(https?://[^\s]+)",
        text
    )

    result = ""

    for part in parts:

        if re.match(
            r"^https?://",
            part
        ):

            result += escape_html(part)

        else:

            result += (
                "<b>"
                + escape_html(part)
                + "</b>"
            )

    return result


# =========================================================
# SEND TO ALL CHANNELS
# =========================================================

async def send_to_all_channels(
    context,
    text=None,
    photo_id=None,
    video_id=None,
    document_id=None
):

    channels = get_channels()

    if not channels:

        return False, "❌ No Source Channels configured."

    success = 0
    errors = []

    for channel in channels:

        try:

            if photo_id:

                await context.bot.send_photo(
                    chat_id=channel,
                    photo=photo_id,
                    caption=text[:1024] if text else None,
                    parse_mode=ParseMode.HTML
                )

            elif video_id:

                await context.bot.send_video(
                    chat_id=channel,
                    video=video_id,
                    caption=text[:1024] if text else None,
                    parse_mode=ParseMode.HTML
                )

            elif document_id:

                await context.bot.send_document(
                    chat_id=channel,
                    document=document_id,
                    caption=text[:1024] if text else None,
                    parse_mode=ParseMode.HTML
                )

            else:

                await context.bot.send_message(
                    chat_id=channel,
                    text=text,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=False
                )

            success += 1

        except Exception as e:

            logger.exception(
                f"Failed to post to {channel}"
            )

            errors.append(
                f"{channel}: {str(e)}"
            )

    if success > 0:

        message = (
            f"Posted successfully to "
            f"{success}/{len(channels)} channels."
        )

        if errors:

            message += "\n\n⚠️ Failed:\n"
            message += "\n".join(errors)

        return True, message

    return False, "\n".join(errors)


# =========================================================
# TEXT MESSAGE
# =========================================================

async def handle_text(update, context):

    if not await check_admin(update):
        return

    text = update.message.text

    # -----------------------------------------------------
    # Waiting for Add Channel
    # -----------------------------------------------------

    waiting = context.user_data.get(
        "waiting_for"
    )

    if waiting == "add_channel":

        channel = text.strip()

        if not channel.startswith("@"):
            channel = "@" + channel

        if add_channel(channel):

            await update.message.reply_text(
                f"✅ Channel added:\n{channel}"
            )

        else:

            await update.message.reply_text(
                "⚠️ This channel is already added."
            )

        context.user_data.pop(
            "waiting_for",
            None
        )

        return

    # -----------------------------------------------------
    # Waiting for Remove Channel
    # -----------------------------------------------------

    if waiting == "remove_channel":

        channel = text.strip()

        if not channel.startswith("@"):
            channel = "@" + channel

        if remove_channel(channel):

            await update.message.reply_text(
                f"✅ Channel removed:\n{channel}"
            )

        else:

            await update.message.reply_text(
                "❌ Channel not found."
            )

        context.user_data.pop(
            "waiting_for",
            None
        )

        return

    # -----------------------------------------------------
    # Waiting for Replace
    # -----------------------------------------------------

    if waiting == "set_replace":

        update_setting(
            "replace_text",
            text.strip()
        )

        await update.message.reply_text(
            "✅ Replace text saved."
        )

        context.user_data.pop(
            "waiting_for",
            None
        )

        return

    # -----------------------------------------------------
    # Waiting for Footer
    # -----------------------------------------------------

    if waiting == "set_footer":

        update_setting(
            "footer",
            text.strip()
        )

        await update.message.reply_text(
            "✅ Footer saved."
        )

        context.user_data.pop(
            "waiting_for",
            None
        )

        return

    # -----------------------------------------------------
    # NORMAL MOVIE POST
    # -----------------------------------------------------

    formatted = format_post(text)

    success, result = await send_to_all_channels(
        context,
        text=formatted
    )

    await update.message.reply_text(
        ("✅ " if success else "❌ ") + result
    )


# =========================================================
# PHOTO
# =========================================================

async def handle_photo(update, context):

    if not await check_admin(update):
        return

    caption = update.message.caption or ""

    formatted = format_post(caption)

    success, result = await send_to_all_channels(
        context,
        text=formatted,
        photo_id=update.message.photo[-1].file_id
    )

    await update.message.reply_text(
        ("✅ " if success else "❌ ") + result
    )


# =========================================================
# VIDEO
# =========================================================

async def handle_video(update, context):

    if not await check_admin(update):
        return

    caption = update.message.caption or ""

    formatted = format_post(caption)

    success, result = await send_to_all_channels(
        context,
        text=formatted,
        video_id=update.message.video.file_id
    )

    await update.message.reply_text(
        ("✅ " if success else "❌ ") + result
    )


# =========================================================
# DOCUMENT
# =========================================================

async def handle_document(update, context):

    if not await check_admin(update):
        return

    caption = update.message.caption or ""

    formatted = format_post(caption)

    success, result = await send_to_all_channels(
        context,
        text=formatted,
        document_id=update.message.document.file_id
    )

    await update.message.reply_text(
        ("✅ " if success else "❌ ") + result
    )


# =========================================================
# MAIN
# =========================================================

def main():

    if not BOT_TOKEN:

        raise ValueError(
            "BOT_TOKEN is missing."
        )

    if not ADMIN_ID:

        raise ValueError(
            "ADMIN_ID is missing."
        )

    init_db()

    app = (
        Application
        .builder()
        .token(BOT_TOKEN)
        .post_init(setup_commands)
        .build()
    )

    # Commands
    app.add_handler(
        CommandHandler("start", start)
    )

    app.add_handler(
        CommandHandler("help", help_command)
    )

    app.add_handler(
        CommandHandler(
            "addchannel",
            add_channel_command
        )
    )

    app.add_handler(
        CommandHandler(
            "channels",
            channels_command
        )
    )

    app.add_handler(
        CommandHandler(
            "removechannel",
            remove_channel_command
        )
    )

    app.add_handler(
        CommandHandler(
            "setreplace",
            set_replace_command
        )
    )

    app.add_handler(
        CommandHandler(
            "setfooter",
            set_footer_command
        )
    )

    app.add_handler(
        CommandHandler(
            "settings",
            settings_command
        )
    )

    # Photo
    app.add_handler(
        MessageHandler(
            filters.PHOTO,
            handle_photo
        )
    )

    # Video
    app.add_handler(
        MessageHandler(
            filters.VIDEO,
            handle_video
        )
    )

    # Document
    app.add_handler(
        MessageHandler(
            filters.Document.ALL,
            handle_document
        )
    )

    # Normal text
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_text
        )
    )

    print(
        "🤖 Movie Auto Poster Bot is running..."
    )

    app.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


if __name__ == "__main__":
    main()
