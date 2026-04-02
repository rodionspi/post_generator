from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

from bot_handlers import (
    apply_channel_change,
    apply_edit,
    cancel,
    handle_url,
    publish_post,
    regenerate_post,
    request_channel_change,
    request_edit,
    start,
)
from config import TELEGRAM_BOT_TOKEN, WAITING_CHANNEL, WAITING_EDIT, WAITING_URL


def build_application() -> Application:
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    conversation = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url),# старт или сразу ссылка от пользователя
        ],
        states={
            WAITING_URL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url),
                CallbackQueryHandler(publish_post, pattern=r"^publish$"),
                CallbackQueryHandler(regenerate_post, pattern=r"^regenerate$"),
                CallbackQueryHandler(request_edit, pattern=r"^edit$"),
                CallbackQueryHandler(request_channel_change, pattern=r"^change_channel$"),
            ],
            WAITING_EDIT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, apply_edit),
                CallbackQueryHandler(publish_post, pattern=r"^publish$"),
                CallbackQueryHandler(regenerate_post, pattern=r"^regenerate$"),
                CallbackQueryHandler(request_edit, pattern=r"^edit$"),
                CallbackQueryHandler(request_channel_change, pattern=r"^change_channel$"),
            ],
            WAITING_CHANNEL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, apply_channel_change),
                CallbackQueryHandler(publish_post, pattern=r"^publish$"),
                CallbackQueryHandler(regenerate_post, pattern=r"^regenerate$"),
                CallbackQueryHandler(request_edit, pattern=r"^edit$"),
                CallbackQueryHandler(request_channel_change, pattern=r"^change_channel$"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel), CommandHandler("start", start)],
        allow_reentry=False,
    )

    application.add_handler(conversation)
    return application
