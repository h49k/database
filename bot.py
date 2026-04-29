"""
MediaDrop Bot - بوت التحميل الذكي
"""
import logging
import requests
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters
)
from handlers.download import download_handler
from handlers.admin import (
    admin_panel, admin_callback, broadcast_handler,
    ban_user_handler, unban_user_handler, stats_handler
)
from handlers.start import start_handler, help_handler
from handlers.subscription import (
    sub_callback, verify_callback,
    sub_admin_panel, handle_add_channel_message
)
from database.db import init_db
from utils.config import BOT_TOKEN

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


async def _message_router(update, ctx):
    handled = await handle_add_channel_message(update, ctx)
    if not handled:
        await download_handler(update, ctx)


async def _start_handler(app):
    """حذف أي webhook قديم عند البدء لتجنب Conflict"""
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook",
            json={"drop_pending_updates": True},
            timeout=10
        )
        logger.info("✅ Webhook cleared")
    except Exception as e:
        logger.warning(f"Could not clear webhook: {e}")


def main():
    logger.info("🚀 MediaDrop Bot starting...")
    init_db()

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(_start_handler)
        .build()
    )

    # ── User Handlers ─────────────────────────────────────────────────────────
    app.add_handler(CommandHandler("start",     start_handler))
    app.add_handler(CommandHandler("help",      help_handler))
    app.add_handler(CommandHandler("stats",     stats_handler))

    # ── Admin Handlers ────────────────────────────────────────────────────────
    app.add_handler(CommandHandler("admin",     admin_panel))
    app.add_handler(CommandHandler("broadcast", broadcast_handler))
    app.add_handler(CommandHandler("ban",       ban_user_handler))
    app.add_handler(CommandHandler("unban",     unban_user_handler))
    app.add_handler(CommandHandler("channels",  sub_admin_panel))

    # ── Callback Handlers ─────────────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(verify_callback,  pattern="^sub_verify$"))
    app.add_handler(CallbackQueryHandler(sub_callback,     pattern="^sub_"))
    app.add_handler(CallbackQueryHandler(admin_callback,   pattern="^admin_"))
    app.add_handler(CallbackQueryHandler(download_handler, pattern="^dl_"))

    # ── URL / Message Handler ─────────────────────────────────────────────────
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, _message_router
    ))

    logger.info("✅ Bot is running!")
    app.run_polling(drop_pending_updates=True, allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
