import os
import re
import sqlite3
import logging

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    BotCommand,
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
# ADMIN
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
# KEYBOARD
# =========================================================

def main_keyboard():

    keyboard = [
        ["📢 Add Channel", "📋 My Channels"],
        ["🗑️ Remove Channel", "🔄 Set Replace"],
        ["📝 Set Footer", "⚙️ Settings"],
        ["❓ Help", "🚀 Start"]
    ]

    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        is_persistent=True
    )


# =========================================================
# TELEGRAM COMMAND MENU
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
            "📢 Add channel"
        ),

        BotCommand(
            "channels",
            "📋 My channels"
        ),

        BotCommand(
            "removechannel",
            "🗑️ Remove channel"
        ),

        BotCommand(
            "setreplace",
            "🔄 Set replace text"
        ),

        BotCommand(
            "setfooter",
            "📝 Set footer"
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

Just send your movie information normally.

The bot will automatically:

✅ Make the post Bold
✅ Keep TeraBox links unchanged
✅ Replace configured source text
✅ Add your footer
✅ Post to all added Source Channels

Use the buttons below 👇""",
        reply_markup=main_keyboard()
    )


# =========================================================
# HELP
# =========================================================

async def help_command(update, context):

    if not await check_admin(update):
        return

    await update.message.reply_text(
        """🛠️ BOT HELP

📢 Add Channel
Add a Source Channel.

📋 My Channels
See all added channels.

🗑️ Remove Channel
Remove a Source Channel.

🔄 Set Replace
Set text/username that should be replaced.

📝 Set Footer
Set automatic footer.

⚙️ Settings
View all current settings.

After setup, simply send your movie post to the bot."""
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

Make sure the bot is Admin in that channel."""
        )

        return

    channel = context.args[0].strip()

    if not channel.startswith("@"):

        channel = "@" + channel

    if add_channel(channel):

        await update.message.reply_text(
            f"✅ Channel added:\n{channel}",
            reply_markup=main_keyboard()
        )

    else:

        await update.message.reply_text(
            "⚠️ This channel is already added.",
            reply_markup=main_keyboard()
        )


# =========================================================
# LIST CHANNELS
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
            f"✅ Removed:\n{channel}",
            reply_markup=main_keyboard()
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

@OldChannel

After this, the bot will replace it with the first added Source Channel."""
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
        "✅ Footer saved."
    )


# =========================================================
# SETTINGS
# =========================================================

async def settings_command(update, context):

    if not await check_admin(update):
        return

    channels = get_channels()

    replace_text, footer = get_settings()

    channel_text = "\n".join(
        f"• {channel}"
        for channel in channels
    )

    if not channel_text:
        channel_text = "❌ None"

    if not replace_text:
        replace_text = "❌ None"

    await update.message.reply_text(
        f"""⚙️ CURRENT SETTINGS

📢 Source Channels:

{channel_text}

🔄 Replace:
{replace_text}

📝 Footer:

{footer}"""
    )


# =========================================================
# FORMAT TEXT
# =========================================================

def escape_html(text):

    if not text:
        return ""

    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")

    return text


def format_post(text):

    if not text:
        text = ""

    replace_text, footer = get_settings()

    channels = get_channels()

    # -----------------------------------------------------
    # Replace configured username/text
    # -----------------------------------------------------

    if replace_text and channels:

        # Use first Source Channel for replacement
        replacement = channels[0]

        text = text.replace(
            replace_text,
            replacement
        )

    # -----------------------------------------------------
    # Add footer
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
    # Preserve URLs while making text bold
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

            result += part

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

        return False, "No Source Channels configured."

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

        return True, (
            f"Posted successfully to "
            f"{success}/{len(channels)} channels."
        )

    return False, "\n".join(errors)


# =========================================================
# NORMAL TEXT MESSAGE
# =========================================================

async def handle_text(update, context):

    if not await check_admin(update):
        return

    text = update.message.text

    # -----------------------------------------------------
    # Button handling
    # -----------------------------------------------------

    if text == "🚀 Start":

        await start(update, context)
        return

    if text == "❓ Help":

        await help_command(update, context)
        return

    if text == "📢 Add Channel":

        await add_channel_command(update, context)
        return

    if text == "📋 My Channels":

        await channels_command(update, context)
        return

    if text == "🗑️ Remove Channel":

        await remove_channel_command(update, context)
        return

    if text == "🔄 Set Replace":

        await set_replace_command(update, context)
        return

    if text == "📝 Set Footer":

        await set_footer_command(update, context)
        return

    if text == "⚙️ Settings":

        await settings_command(update, context)
        return

    # -----------------------------------------------------
    # Waiting for button input
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
                f"✅ Channel added:\n{channel}",
                reply_markup=main_keyboard()
            )

        else:

            await update.message.reply_text(
                "⚠️ Channel already exists.",
                reply_markup=main_keyboard()
            )

        context.user_data.pop(
            "waiting_for",
            None
        )

        return

    if waiting == "remove_channel":

        channel = text.strip()

        if not channel.startswith("@"):

            channel = "@" + channel

        if remove_channel(channel):

            await update.message.reply_text(
                f"✅ Channel removed:\n{channel}",
                reply_markup=main_keyboard()
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

    if waiting == "set_replace":

        update_setting(
            "replace_text",
            text.strip()
        )

        await update.message.reply_text(
            "✅ Replace text saved.",
            reply_markup=main_keyboard()
        )

        context.user_data.pop(
            "waiting_for",
            None
        )

        return

    if waiting == "set_footer":

        update_setting(
            "footer",
            text.strip()
        )

        await update.message.reply_text(
            "✅ Footer saved.",
            reply_markup=main_keyboard()
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

    if success:

        await update.message.reply_text(
            f"✅ {result}",
            reply_markup=main_keyboard()
        )

    else:

        await update.message.reply_text(
            f"❌ Could not post.\n\n{result}",
            reply_markup=main_keyboard()
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
        ("✅ " if success else "❌ ")
        + result,
        reply_markup=main_keyboard()
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
        ("✅ " if success else "❌ ")
        + result,
        reply_markup=main_keyboard()
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
        ("✅ " if success else "❌ ")
        + result,
        reply_markup=main_keyboard()
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

    # Media
    app.add_handler(
        MessageHandler(
            filters.PHOTO,
            handle_photo
        )
    )

    app.add_handler(
        MessageHandler(
            filters.VIDEO,
            handle_video
        )
    )

    app.add_handler(
        MessageHandler(
            filters.Document.ALL,
            handle_document
        )
    )

    # Text
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_text
        )
    )

    print("🤖 Movie Auto Poster Bot is running...")

    app.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


if __name__ == "__main__":
    main()
