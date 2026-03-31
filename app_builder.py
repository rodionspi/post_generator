from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

from bot_handlers import (
    apply_edit,
    cancel,
    handle_url,
    publish_post,
    regenerate_post,
    request_edit,
    start,
)
from config import TELEGRAM_BOT_TOKEN, WAITING_EDIT, WAITING_URL


def build_application() -> Application:
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    conversation = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url),
        ],
        states={
            WAITING_URL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url),
                CallbackQueryHandler(publish_post, pattern=r"^publish$"),
                CallbackQueryHandler(regenerate_post, pattern=r"^regenerate$"),
                CallbackQueryHandler(request_edit, pattern=r"^edit$"),
            ],
            WAITING_EDIT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, apply_edit),
                CallbackQueryHandler(publish_post, pattern=r"^publish$"),
                CallbackQueryHandler(regenerate_post, pattern=r"^regenerate$"),
                CallbackQueryHandler(request_edit, pattern=r"^edit$"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel), CommandHandler("start", start)],
        allow_reentry=True,
    )

    application.add_handler(conversation)
    return application
