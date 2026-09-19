import os
import sqlite3
import html
import logging

from telegram import (
    Update,
    BotCommand,
    MenuButtonCommands,
    ReplyKeyboardRemove,
)

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

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is missing")

if not ADMIN_ID:
    raise ValueError("ADMIN_ID is missing")

try:
    ADMIN_ID = int(ADMIN_ID)
except ValueError:
    raise ValueError(
        "ADMIN_ID must be a numeric Telegram User ID."
    )

DB_FILE = "bot.db"


# =========================================================
# LOGGING
# =========================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


# =========================================================
# BOLD MESSAGE FUNCTION
# =========================================================

def bold_text(text):
    """
    Makes the complete Telegram message Bold.
    """

    if not text:
        return ""

    return f"<b>{html.escape(str(text))}</b>"


async def send_bold_message(
    message,
    text
):
    """
    Sends every bot message in Bold
    and removes any old Reply Keyboard.
    """

    await message.reply_text(
        bold_text(text),
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove()
    )


# =========================================================
# DATABASE
# =========================================================

def get_db():

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row

    return conn


def init_db():

    conn = get_db()
    cur = conn.cursor()

    # Source Channels
    cur.execute("""
        CREATE TABLE IF NOT EXISTS channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel TEXT UNIQUE NOT NULL
        )
    """)

    # Settings
    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY,
            replace_text TEXT DEFAULT '',
            footer TEXT DEFAULT ''
        )
    """)

    # Default settings
    cur.execute("""
        INSERT OR IGNORE INTO settings
        (id, replace_text, footer)
        VALUES (?, ?, ?)
    """, (
        1,
        "",
        """Join Backup Channel ❤️👇
@backup_stor

Best loot offers 🛍️ 🤝 💸
📌 @loot_dells
📌 @loot_dells"""
    ))

    conn.commit()
    conn.close()


# =========================================================
# ADMIN CHECK
# =========================================================

def is_admin(update: Update):

    if not update.effective_user:
        return False

    return update.effective_user.id == ADMIN_ID


async def admin_only(update: Update):

    if not is_admin(update):

        if update.message:

            await send_bold_message(
                update.message,
                "❌ You are not authorized to use this bot."
            )

        return False

    return True


# =========================================================
# CHANNEL FUNCTIONS
# =========================================================

def get_channels():

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "SELECT channel FROM channels ORDER BY id ASC"
    )

    rows = cur.fetchall()

    conn.close()

    return [
        row["channel"]
        for row in rows
    ]


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

    deleted = cur.rowcount > 0

    conn.commit()
    conn.close()

    return deleted


# =========================================================
# SETTINGS FUNCTIONS
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
        return "", ""

    return (
        row["replace_text"],
        row["footer"]
    )


def set_replace_text(text):

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        UPDATE settings
        SET replace_text = ?
        WHERE id = 1
    """, (text,))

    conn.commit()
    conn.close()


def set_footer(text):

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        UPDATE settings
        SET footer = ?
        WHERE id = 1
    """, (text,))

    conn.commit()
    conn.close()


# =========================================================
# FORMAT MOVIE POST
# =========================================================

def format_post(text):

    replace_text, footer = get_settings()

    text = text or ""

    # -----------------------------------------------------
    # Replace configured text
    # -----------------------------------------------------

    if replace_text.strip():

        channels = get_channels()

        if channels:

            first_channel = channels[0]

            text = text.replace(
                replace_text,
                first_channel
            )

    # -----------------------------------------------------
    # Add Footer
    # -----------------------------------------------------

    if footer.strip():

        if text.strip():

            text = (
                text.rstrip()
                + "\n\n"
                + footer.strip()
            )

        else:

            text = footer.strip()

    # -----------------------------------------------------
    # Everything Bold
    # -----------------------------------------------------

    return bold_text(text)


# =========================================================
# SEND MOVIE POST TO ALL CHANNELS
# =========================================================

async def send_to_all_channels(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = update.message

    if not message:
        return

    # Only Admin can send posts
    if not is_admin(update):
        return

    channels = get_channels()

    if not channels:

        await send_bold_message(
            message,
            "⚠️ No Source Channel has been added yet.\n\n"
            "Open the Telegram Menu and select "
            "Add Source Channel."
        )

        return

    # -----------------------------------------------------
    # Get Text / Caption
    # -----------------------------------------------------

    original_text = (
        message.text
        or message.caption
        or ""
    )

    formatted_text = format_post(
        original_text
    )

    success = 0
    failed = 0


    # =====================================================
    # PHOTO
    # =====================================================

    if message.photo:

        photo = message.photo[-1]

        for channel in channels:

            try:

                await context.bot.send_photo(
                    chat_id=channel,
                    photo=photo.file_id,
                    caption=(
                        formatted_text[:1024]
                        if formatted_text
                        else None
                    ),
                    parse_mode="HTML"
                )

                success += 1

            except Exception as e:

                failed += 1

                logger.error(
                    "Photo error: %s",
                    e
                )


    # =====================================================
    # VIDEO
    # =====================================================

    elif message.video:

        video = message.video

        for channel in channels:

            try:

                await context.bot.send_video(
                    chat_id=channel,
                    video=video.file_id,
                    caption=(
                        formatted_text[:1024]
                        if formatted_text
                        else None
                    ),
                    parse_mode="HTML"
                )

                success += 1

            except Exception as e:

                failed += 1

                logger.error(
                    "Video error: %s",
                    e
                )


    # =====================================================
    # DOCUMENT
    # =====================================================

    elif message.document:

        document = message.document

        for channel in channels:

            try:

                await context.bot.send_document(
                    chat_id=channel,
                    document=document.file_id,
                    caption=(
                        formatted_text[:1024]
                        if formatted_text
                        else None
                    ),
                    parse_mode="HTML"
                )

                success += 1

            except Exception as e:

                failed += 1

                logger.error(
                    "Document error: %s",
                    e
                )


    # =====================================================
    # AUDIO
    # =====================================================

    elif message.audio:

        audio = message.audio

        for channel in channels:

            try:

                await context.bot.send_audio(
                    chat_id=channel,
                    audio=audio.file_id,
                    caption=(
                        formatted_text[:1024]
                        if formatted_text
                        else None
                    ),
                    parse_mode="HTML"
                )

                success += 1

            except Exception as e:

                failed += 1

                logger.error(
                    "Audio error: %s",
                    e
                )


    # =====================================================
    # VOICE
    # =====================================================

    elif message.voice:

        voice = message.voice

        for channel in channels:

            try:

                await context.bot.send_voice(
                    chat_id=channel,
                    voice=voice.file_id,
                    caption=(
                        formatted_text[:1024]
                        if formatted_text
                        else None
                    ),
                    parse_mode="HTML"
                )

                success += 1

            except Exception as e:

                failed += 1

                logger.error(
                    "Voice error: %s",
                    e
                )


    # =====================================================
    # TEXT
    # =====================================================

    elif message.text:

        if not formatted_text:
            return

        for channel in channels:

            try:

                await context.bot.send_message(
                    chat_id=channel,
                    text=formatted_text,
                    parse_mode="HTML",
                    disable_web_page_preview=False
                )

                success += 1

            except Exception as e:

                failed += 1

                logger.error(
                    "Text error: %s",
                    e
                )


    # =====================================================
    # OTHER / FORWARDED CONTENT
    # =====================================================

    else:

        for channel in channels:

            try:

                await context.bot.copy_message(
                    chat_id=channel,
                    from_chat_id=message.chat_id,
                    message_id=message.message_id
                )

                success += 1

            except Exception as e:

                failed += 1

                logger.error(
                    "Copy error: %s",
                    e
                )


    # =====================================================
    # RESULT MESSAGE - BOLD
    # =====================================================

    await send_bold_message(
        message,
        "✅ Movie post processed successfully.\n\n"
        f"📤 Sent: {success}\n"
        f"❌ Failed: {failed}"
    )


# =========================================================
# START
# =========================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not await admin_only(update):
        return

    await send_bold_message(
        update.message,
        "🎬 Movie Update HD Bot\n\n"
        "✅ Old keyboard removed.\n\n"
        "Send your movie post here.\n\n"
        "The movie text/caption will be Bold.\n\n"
        "Use the Telegram Menu (☰) for all commands."
    )


# =========================================================
# HELP
# =========================================================

async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not await admin_only(update):
        return

    await send_bold_message(
        update.message,
        "📚 Bot Commands\n\n"

        "/start - Start the Bot\n"
        "/help - Help\n"
        "/addchannel - Add Source Channel\n"
        "/channels - Show Source Channels\n"
        "/removechannel - Remove Source Channel\n"
        "/setreplace - Set replacement text\n"
        "/setfooter - Set footer\n"
        "/settings - Show current settings\n\n"

        "❌ No Reply Keyboard is used.\n"
        "✅ Only Telegram Menu is used."
    )


# =========================================================
# ADD CHANNEL
# =========================================================

async def addchannel_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not await admin_only(update):
        return

    if not context.args:

        await send_bold_message(
            update.message,
            "➕ Add Source Channel\n\n"

            "Use:\n"
            "/addchannel @yourchannel\n\n"

            "Example:\n"
            "/addchannel @MovieSourceHD\n\n"

            "Make sure the Bot is Administrator "
            "in the channel with Post Messages permission."
        )

        return

    channel = context.args[0].strip()

    if (
        not channel.startswith("@")
        and not channel.startswith("-100")
    ):

        await send_bold_message(
            update.message,
            "❌ Invalid channel format.\n\n"

            "Use:\n"
            "@channelusername\n\n"

            "or:\n"
            "-100xxxxxxxxxx"
        )

        return

    added = add_channel(channel)

    if added:

        await send_bold_message(
            update.message,
            f"✅ Source Channel added successfully.\n\n"
            f"📢 {channel}\n\n"
            "Make sure the Bot is Administrator "
            "with Post Messages permission."
        )

    else:

        await send_bold_message(
            update.message,
            f"⚠️ This Source Channel is already added.\n\n"
            f"📢 {channel}"
        )


# =========================================================
# CHANNELS
# =========================================================

async def channels_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not await admin_only(update):
        return

    channels = get_channels()

    if not channels:

        await send_bold_message(
            update.message,
            "📭 No Source Channels have been added yet."
        )

        return

    text = "📢 Source Channels\n\n"

    for index, channel in enumerate(
        channels,
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

async def removechannel_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not await admin_only(update):
        return

    if not context.args:

        await send_bold_message(
            update.message,
            "🗑 Remove Source Channel\n\n"
            "Use:\n"
            "/removechannel @yourchannel"
        )

        return

    channel = context.args[0].strip()

    removed = remove_channel(channel)

    if removed:

        await send_bold_message(
            update.message,
            f"✅ Source Channel removed.\n\n"
            f"📢 {channel}"
        )

    else:

        await send_bold_message(
            update.message,
            f"❌ Source Channel not found.\n\n"
            f"📢 {channel}"
        )


# =========================================================
# SET REPLACE
# =========================================================

async def setreplace_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not await admin_only(update):
        return

    if not context.args:

        await send_bold_message(
            update.message,
            "✏️ Set Replace Text\n\n"

            "Use:\n"
            "/setreplace @OldChannel\n\n"

            "Example:\n"
            "/setreplace @OldMovieChannel\n\n"

            "This text will be replaced by "
            "the first Source Channel."
        )

        return

    text = " ".join(context.args)

    set_replace_text(text)

    await send_bold_message(
        update.message,
        "✅ Replacement text saved successfully.\n\n"
        f"🔄 Text:\n{text}"
    )


# =========================================================
# SET FOOTER
# =========================================================

async def setfooter_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not await admin_only(update):
        return

    if not context.args:

        await send_bold_message(
            update.message,
            "✏️ Set Footer\n\n"

            "Use:\n"
            "/setfooter Your footer text here"
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

async def settings_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not await admin_only(update):
        return

    replace_text, footer = get_settings()

    channels = get_channels()

    if channels:

        channel_text = "\n".join(
            channels
        )

    else:

        channel_text = "None"

    await send_bold_message(
        update.message,
        "⚙️ Current Settings\n\n"

        "📢 Source Channels:\n"
        f"{channel_text}\n\n"

        "🔄 Replace Text:\n"
        f"{replace_text or 'None'}\n\n"

        "📝 Footer:\n"
        f"{footer or 'None'}"
    )


# =========================================================
# ERROR HANDLER
# =========================================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE
):

    logger.error(
        "Exception while handling update:",
        exc_info=context.error
    )


# =========================================================
# TELEGRAM MENU
# =========================================================

async def setup_bot(
    application: Application
):

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
            "setreplace",
            "Set replacement text"
        ),

        BotCommand(
            "setfooter",
            "Set footer"
        ),

        BotCommand(
            "settings",
            "Show settings"
        ),
    ]

    # Set Telegram Menu Commands
    await application.bot.set_my_commands(
        commands
    )

    # Use native Telegram Menu button
    await application.bot.set_chat_menu_button(
        menu_button=MenuButtonCommands()
    )


# =========================================================
# MAIN
# =========================================================

def main():

    # Initialize database
    init_db()

    # Create Application
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(setup_bot)
        .build()
    )

    # -----------------------------------------------------
    # COMMAND HANDLERS
    # -----------------------------------------------------

    application.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    application.add_handler(
        CommandHandler(
            "help",
            help_command
        )
    )

    application.add_handler(
        CommandHandler(
            "addchannel",
            addchannel_command
        )
    )

    application.add_handler(
        CommandHandler(
            "channels",
            channels_command
        )
    )

    application.add_handler(
        CommandHandler(
            "removechannel",
            removechannel_command
        )
    )

    application.add_handler(
        CommandHandler(
            "setreplace",
            setreplace_command
        )
    )

    application.add_handler(
        CommandHandler(
            "setfooter",
            setfooter_command
        )
    )

    application.add_handler(
        CommandHandler(
            "settings",
            settings_command
        )
    )

    # -----------------------------------------------------
    # ALL CONTENT
    #
    # Text
    # Photo
    # Video
    # Document
    # Audio
    # Voice
    # Forwarded Messages
    #
    # No Reply Keyboard
    # -----------------------------------------------------

    application.add_handler(
        MessageHandler(
            filters.ALL & ~filters.COMMAND,
            send_to_all_channels
        )
    )

    # Error Handler
    application.add_error_handler(
        error_handler
    )

    print(
        "========================================"
    )

    print(
        "Movie Update HD Bot is running..."
    )

    print(
        "Reply Keyboard: DISABLED"
    )

    print(
        "Bot Messages: BOLD"
    )

    print(
        "Movie Captions: BOLD"
    )

    print(
        "Telegram Menu: ENABLED"
    )

    print(
        "========================================"
    )

    # Start Bot
    application.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":
    main()
