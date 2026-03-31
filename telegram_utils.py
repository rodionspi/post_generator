import asyncio
import logging
from io import BytesIO
from typing import Any

import requests
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.error import BadRequest, TelegramError
from telegram.ext import ContextTypes

LOGGER = logging.getLogger(__name__)
TELEGRAM_CAPTION_LIMIT = 1024


def preview_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Опубликовать", callback_data="publish"),
                InlineKeyboardButton("🔄 Перегенерировать", callback_data="regenerate"),
            ],
            [InlineKeyboardButton("✏️ Изменить", callback_data="edit")],
        ]
    )


def _is_markdown_error(error: BadRequest) -> bool:
    lowered = str(error).lower()
    return "parse entities" in lowered


def _is_caption_too_long_error(error: BadRequest) -> bool:
    lowered = str(error).lower()
    return "caption is too long" in lowered


def _truncate_caption(text: str, limit: int = TELEGRAM_CAPTION_LIMIT) -> str:
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _download_image_bytes(url: str) -> bytes:
    response = requests.get(
        url,
        timeout=20,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            )
        },
    )
    response.raise_for_status()

    content_type = (response.headers.get("Content-Type") or "").lower()
    if content_type and not content_type.startswith("image/"):
        raise ValueError(f"Ожидалось изображение, но получен Content-Type: {content_type}")

    if not response.content:
        raise ValueError("Изображение пустое")

    return response.content


async def _send_photo_with_fallback(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int | str,
    image_url: str,
    caption: str | None = None,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> bool:
    caption_to_send = caption

    async def _send_with_caption(photo: Any) -> None:
        nonlocal caption_to_send
        while True:
            try:
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=photo,
                    caption=caption_to_send,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=reply_markup,
                )
                return
            except BadRequest as error:
                if _is_caption_too_long_error(error) and caption_to_send:
                    shorter = _truncate_caption(caption_to_send)
                    if shorter == caption_to_send:
                        raise
                    caption_to_send = shorter
                    continue

                if _is_markdown_error(error):
                    await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=photo,
                        caption=caption_to_send,
                        reply_markup=reply_markup,
                    )
                    return

                raise

    try:
        await _send_with_caption(image_url)
        return True
    except TelegramError:
        LOGGER.info("Не удалось отправить изображение по URL, пробую загрузить файл", exc_info=True)

    try:
        image_bytes = await asyncio.to_thread(_download_image_bytes, image_url)
        photo_file = BytesIO(image_bytes)
        photo_file.name = "image.jpg"
        await _send_with_caption(photo_file)
        return True
    except Exception:
        LOGGER.info("Не удалось отправить изображение даже через загрузку файла", exc_info=True)
        return False


async def send_post_text(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int | str,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
            reply_markup=reply_markup,
        )
    except BadRequest as error:
        if _is_markdown_error(error):
            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                disable_web_page_preview=True,
                reply_markup=reply_markup,
            )
        else:
            raise


def _preview_caption(post_text: str) -> str:
    return f"Предпросмотр поста:\n\n{post_text}"


async def edit_preview_message(query_text_message: Any, post_text: str) -> None:
    caption = _preview_caption(post_text)

    if getattr(query_text_message, "photo", None):
        caption_to_send = caption
        while True:
            try:
                await query_text_message.edit_caption(
                    caption=caption_to_send,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=preview_keyboard(),
                )
                return
            except BadRequest as error:
                lowered = str(error).lower()
                if "message is not modified" in lowered:
                    return

                if _is_caption_too_long_error(error):
                    shorter = _truncate_caption(caption_to_send)
                    if shorter == caption_to_send:
                        raise
                    caption_to_send = shorter
                    continue

                if _is_markdown_error(error):
                    await query_text_message.edit_caption(
                        caption=caption_to_send,
                        reply_markup=preview_keyboard(),
                    )
                    return

                raise

    try:
        await query_text_message.edit_text(
            text=caption,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
            reply_markup=preview_keyboard(),
        )
    except BadRequest as error:
        lowered = str(error).lower()
        if "message is not modified" in lowered:
            return
        if _is_markdown_error(error):
            await query_text_message.edit_text(
                text=caption,
                disable_web_page_preview=True,
                reply_markup=preview_keyboard(),
            )
        else:
            raise


async def send_preview(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int | str,
    post_text: str,
    image_url: str | None,
) -> None:
    if image_url:
        sent = await _send_photo_with_fallback(
            context,
            chat_id,
            image_url,
            caption=_preview_caption(post_text),
            reply_markup=preview_keyboard(),
        )
        if sent:
            return

    await send_post_text(
        context,
        chat_id,
        _preview_caption(post_text),
        reply_markup=preview_keyboard(),
    )


async def publish_to_channel(
    context: ContextTypes.DEFAULT_TYPE,
    channel_id: int | str,
    post_text: str,
    image_url: str | None,
) -> None:
    if image_url:
        sent = await _send_photo_with_fallback(
            context,
            channel_id,
            image_url,
            caption=post_text,
            reply_markup=None,
        )
        if sent:
            return

    await send_post_text(context, channel_id, post_text)
