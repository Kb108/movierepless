import os
import sqlite3
import logging
from telegram import Update
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

def db():
    return sqlite3.connect(DB_FILE)


def init_db():
    conn = db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            source_channel TEXT DEFAULT '',
            replace_text TEXT DEFAULT '',
            footer TEXT DEFAULT ''
        )
    """)

    cur.execute("""
        INSERT OR IGNORE INTO settings
        (id, source_channel, replace_text, footer)
        VALUES (1, '', '', ?)
    """, (DEFAULT_FOOTER,))

    conn.commit()
    conn.close()


def get_settings():
    conn = db()
    cur = conn.cursor()

    cur.execute("""
        SELECT source_channel, replace_text, footer
        FROM settings
        WHERE id = 1
    """)

    row = cur.fetchone()
    conn.close()

    if not row:
        return "", "", DEFAULT_FOOTER

    return row[0] or "", row[1] or "", row[2] or ""


def update_setting(column, value):
    allowed = {
        "source_channel",
        "replace_text",
        "footer"
    }

    if column not in allowed:
        return

    conn = db()
    cur = conn.cursor()

    cur.execute(
        f"UPDATE settings SET {column} = ? WHERE id = 1",
        (value,)
    )

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
            await update.message.reply_text(
                "❌ You are not authorized to use this bot."
            )
        return False

    return True


# =========================================================
# START
# =========================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not await admin_only(update):
        return

    text = """🎬 Content Auto Poster Bot

Send a text, TeraBox link, photo or caption here.

The bot will:
✅ Replace configured source text
✅ Add your footer
✅ Send the post to your Source Channel

Commands:

/setsource
/setreplace
/setfooter
/settings
/help
"""

    await update.message.reply_text(text)


# =========================================================
# HELP
# =========================================================

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not await admin_only(update):
        return

    text = """🛠 Commands

/setsource @YourChannel
Set the channel where posts will be published.

/setreplace @OldChannel
Set text that should be replaced.

/setfooter
Set your automatic footer.

/settings
Show current settings.

After setup, simply send your content to this bot.
"""

    await update.message.reply_text(text)


# =========================================================
# SET SOURCE
# =========================================================

async def setsource(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not await admin_only(update):
        return

    if not context.args:
        await update.message.reply_text(
            "Example:\n\n/setsource @MySourceChannel"
        )
        return

    channel = context.args[0].strip()

    update_setting("source_channel", channel)

    await update.message.reply_text(
        f"✅ Source Channel saved:\n{channel}"
    )


# =========================================================
# SET REPLACE
# =========================================================

async def setreplace(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not await admin_only(update):
        return

    if not context.args:
        await update.message.reply_text(
            "Example:\n\n/setreplace @OldChannel"
        )
        return

    replace_text = " ".join(context.args).strip()

    update_setting("replace_text", replace_text)

    await update.message.reply_text(
        f"✅ Replace text saved:\n{replace_text}"
    )


# =========================================================
# SET FOOTER
# =========================================================

async def setfooter(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not await admin_only(update):
        return

    # Everything after /setfooter
    message_text = update.message.text or ""

    footer = message_text[len("/setfooter"):].strip()

    if not footer:
        await update.message.reply_text(
            """Example:

/setfooter Join Backup Channel ❤️👇
@backup_stor

Best loot offers 🛍️ 🤝 💸
📌 @loot_dells
📌 @loot_dells"""
        )
        return

    update_setting("footer", footer)

    await update.message.reply_text(
        "✅ Footer saved successfully."
    )


# =========================================================
# SETTINGS
# =========================================================

async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not await admin_only(update):
        return

    source, replace_text, footer = get_settings()

    if not source:
        source = "❌ Not set"

    if not replace_text:
        replace_text = "❌ Not set"

    if not footer:
        footer = "❌ Not set"

    text = f"""⚙️ Current Settings

📢 Source Channel:
{source}

🔄 Replace Text:
{replace_text}

📝 Footer:

{footer}
"""

    await update.message.reply_text(text)


# =========================================================
# PROCESS CAPTION / TEXT
# =========================================================

def process_text(text):

    source_channel, replace_text, footer = get_settings()

    if not text:
        text = ""

    # Replace configured source
    if replace_text:
        text = text.replace(
            replace_text,
            source_channel
        )

    # Add footer
    if footer:

        # Prevent duplicate footer
        if footer.strip() not in text:

            if text.strip():
                text = text.rstrip() + "\n\n" + footer
            else:
                text = footer

    return text


# =========================================================
# TEXT MESSAGE
# =========================================================

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not await admin_only(update):
        return

    source_channel, _, _ = get_settings()

    if not source_channel:
        await update.message.reply_text(
            "❌ Source Channel is not configured.\n\n"
            "Use:\n"
            "/setsource @YourChannel"
        )
        return

    original_text = update.message.text

    new_text = process_text(original_text)

    try:

        await context.bot.send_message(
            chat_id=source_channel,
            text=new_text,
            disable_web_page_preview=False
        )

        await update.message.reply_text(
            "✅ Posted successfully to Source Channel."
        )

    except Exception as e:

        logger.exception("Posting error")

        await update.message.reply_text(
            "❌ Could not post to Source Channel.\n\n"
            f"Error: {str(e)}"
        )


# =========================================================
# PHOTO MESSAGE
# =========================================================

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not await admin_only(update):
        return

    source_channel, _, _ = get_settings()

    if not source_channel:
        await update.message.reply_text(
            "❌ Source Channel is not configured.\n\n"
            "Use:\n"
            "/setsource @YourChannel"
        )
        return

    photo = update.message.photo[-1]

    caption = update.message.caption or ""

    new_caption = process_text(caption)

    try:

        await context.bot.send_photo(
            chat_id=source_channel,
            photo=photo.file_id,
            caption=new_caption[:1024]
        )

        await update.message.reply_text(
            "✅ Photo posted successfully."
        )

    except Exception as e:

        logger.exception("Photo posting error")

        await update.message.reply_text(
            "❌ Could not post photo.\n\n"
            f"Error: {str(e)}"
        )


# =========================================================
# VIDEO MESSAGE
# =========================================================

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not await admin_only(update):
        return

    source_channel, _, _ = get_settings()

    if not source_channel:
        await update.message.reply_text(
            "❌ Source Channel is not configured."
        )
        return

    video = update.message.video

    caption = update.message.caption or ""

    new_caption = process_text(caption)

    try:

        await context.bot.send_video(
            chat_id=source_channel,
            video=video.file_id,
            caption=new_caption[:1024]
        )

        await update.message.reply_text(
            "✅ Video posted successfully."
        )

    except Exception as e:

        logger.exception("Video posting error")

        await update.message.reply_text(
            "❌ Could not post video.\n\n"
            f"Error: {str(e)}"
        )


# =========================================================
# DOCUMENT MESSAGE
# =========================================================

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not await admin_only(update):
        return

    source_channel, _, _ = get_settings()

    if not source_channel:
        await update.message.reply_text(
            "❌ Source Channel is not configured."
        )
        return

    document = update.message.document

    caption = update.message.caption or ""

    new_caption = process_text(caption)

    try:

        await context.bot.send_document(
            chat_id=source_channel,
            document=document.file_id,
            caption=new_caption[:1024]
        )

        await update.message.reply_text(
            "✅ Document posted successfully."
        )

    except Exception as e:

        logger.exception("Document posting error")

        await update.message.reply_text(
            "❌ Could not post document.\n\n"
            f"Error: {str(e)}"
        )


# =========================================================
# MAIN
# =========================================================

def main():

    if not BOT_TOKEN:
        raise ValueError(
            "BOT_TOKEN environment variable is missing."
        )

    if not ADMIN_ID:
        raise ValueError(
            "ADMIN_ID environment variable is missing."
        )

    init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(
        CommandHandler("start", start)
    )

    app.add_handler(
        CommandHandler("help", help_command)
    )

    app.add_handler(
        CommandHandler("setsource", setsource)
    )

    app.add_handler(
        CommandHandler("setreplace", setreplace)
    )

    app.add_handler(
        CommandHandler("setfooter", setfooter)
    )

    app.add_handler(
        CommandHandler("settings", settings)
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

    print("🤖 Bot is running...")

    app.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


if __name__ == "__main__":
    main()
