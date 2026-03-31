import asyncio
import logging
import re

import requests
from telegram import Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from config import CHANNEL_ID, WAITING_EDIT, WAITING_URL
from generator_service import generate_post
from parser_service import parse_page
from telegram_utils import edit_preview_message, publish_to_channel, send_preview

LOGGER = logging.getLogger(__name__)


def _extract_url(text: str) -> str | None:
    match = re.search(r"https?://\S+", text)
    if not match:
        return None
    return match.group(0).strip()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.effective_chat is None or update.message is None:
        return WAITING_URL

    if update.effective_chat.type != "private":
        await update.message.reply_text("Этот бот работает только в личных сообщениях.")
        return WAITING_URL

    context.user_data.clear()
    await update.message.reply_text(
        "Привет! Пришлите ссылку на страницу, и я подготовлю пост для Telegram-канала."
    )
    return WAITING_URL


async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.effective_chat is None or update.message is None:
        return WAITING_URL

    if update.effective_chat.type != "private":
        await update.message.reply_text("Пожалуйста, используйте бота в личном чате.")
        return WAITING_URL

    url = _extract_url(update.message.text or "")
    if not url:
        await update.message.reply_text(
            "Пришлите корректную ссылку, которая начинается с http:// или https://"
        )
        return WAITING_URL

    await update.message.reply_text("Секунду, разбираю страницу...")

    try:
        parsed = await asyncio.to_thread(parse_page, url)
    except requests.HTTPError as error:
        LOGGER.exception("HTTP ошибка загрузки страницы: %s", url)
        status = error.response.status_code if error.response is not None else None
        if status in (401, 403, 429):
            await update.message.reply_text(
                "Сайт ограничивает автоматическое чтение. Попробуйте другую ссылку "
                "или откройте страницу публично и без авторизации."
            )
        else:
            await update.message.reply_text(
                "Не удалось открыть страницу. Проверьте ссылку и попробуйте снова."
            )
        return WAITING_URL
    except requests.RequestException:
        LOGGER.exception("Ошибка загрузки страницы: %s", url)
        await update.message.reply_text(
            "Не удалось открыть страницу. Проверьте ссылку и попробуйте снова."
        )
        return WAITING_URL
    except ValueError as error:
        LOGGER.exception("Ошибка парсинга страницы: %s", url)
        await update.message.reply_text(f"Не получилось извлечь данные: {error}")
        return WAITING_URL
    except Exception:
        LOGGER.exception("Неожиданная ошибка парсинга: %s", url)
        await update.message.reply_text("Произошла ошибка при анализе страницы.")
        return WAITING_URL

    await update.message.reply_text("Генерирую черновик поста...")

    try:
        generated = await asyncio.to_thread(generate_post, parsed, None)
    except Exception:
        LOGGER.exception("Ошибка генерации поста")
        await update.message.reply_text(
            "Не удалось сгенерировать пост. Попробуйте еще раз через минуту."
        )
        return WAITING_URL

    context.user_data["parsed"] = parsed
    context.user_data["draft"] = generated
    context.user_data["image_url"] = parsed.get("image_url")

    await send_preview(
        context=context,
        chat_id=update.effective_chat.id,
        post_text=generated,
        image_url=parsed.get("image_url"),
    )
    return WAITING_URL


async def regenerate_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query is None or query.message is None:
        return WAITING_URL

    await query.answer()

    parsed = context.user_data.get("parsed")
    if not parsed:
        await query.message.reply_text("Сначала пришлите ссылку, чтобы подготовить черновик.")
        return WAITING_URL

    try:
        generated = await asyncio.to_thread(generate_post, parsed, None)
    except Exception:
        LOGGER.exception("Ошибка повторной генерации")
        await query.message.reply_text("Не удалось перегенерировать пост. Попробуйте еще раз.")
        return WAITING_URL

    context.user_data["draft"] = generated

    try:
        await edit_preview_message(query.message, generated)
    except TelegramError:
        LOGGER.exception("Не удалось обновить сообщение превью")
        await send_preview(
            context=context,
            chat_id=query.message.chat.id,
            post_text=generated,
            image_url=context.user_data.get("image_url"),
        )

    return WAITING_URL


async def request_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query is None or query.message is None:
        return WAITING_URL

    await query.answer()

    if not context.user_data.get("parsed"):
        await query.message.reply_text("Пока нечего редактировать. Сначала отправьте ссылку.")
        return WAITING_URL

    await query.message.reply_text(
        "Напишите, что изменить в посте. Например: "
        "сделай тон более деловым и добавь акцент на практическую пользу."
    )
    return WAITING_EDIT


async def apply_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.effective_chat is None or update.message is None:
        return WAITING_EDIT

    feedback = (update.message.text or "").strip()
    if not feedback:
        await update.message.reply_text("Напишите, пожалуйста, текст правок.")
        return WAITING_EDIT

    parsed = context.user_data.get("parsed")
    if not parsed:
        await update.message.reply_text("Сначала пришлите ссылку для генерации поста.")
        return WAITING_URL

    await update.message.reply_text("Учитываю правки и обновляю текст...")

    try:
        generated = await asyncio.to_thread(generate_post, parsed, feedback)
    except Exception:
        LOGGER.exception("Ошибка генерации по правкам")
        await update.message.reply_text(
            "Не удалось обновить пост по правкам. Попробуйте сформулировать иначе."
        )
        return WAITING_EDIT

    context.user_data["draft"] = generated
    await send_preview(
        context=context,
        chat_id=update.effective_chat.id,
        post_text=generated,
        image_url=context.user_data.get("image_url"),
    )
    return WAITING_URL


async def publish_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query is None or query.message is None:
        return WAITING_URL

    await query.answer()

    draft = context.user_data.get("draft")
    if not draft:
        await query.message.reply_text("Нет черновика для публикации. Сначала отправьте ссылку.")
        return WAITING_URL

    try:
        await publish_to_channel(
            context=context,
            channel_id=CHANNEL_ID,
            post_text=str(draft),
            image_url=context.user_data.get("image_url"),
        )
    except TelegramError:
        LOGGER.exception("Ошибка публикации в канал")
        await query.message.reply_text(
            "Не удалось опубликовать пост. Проверьте, что бот добавлен в канал "
            "и назначен администратором с правом публикации сообщений."
        )
        return WAITING_URL

    await query.message.reply_text("Пост успешно опубликован в канал.")
    return WAITING_URL


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message:
        await update.message.reply_text(
            "Остановил текущий сценарий. Пришлите новую ссылку, когда будете готовы."
        )
    context.user_data.clear()
    return WAITING_URL
