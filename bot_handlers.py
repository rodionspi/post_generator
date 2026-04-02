import logging
import re
import asyncio

import requests
from telegram import Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from config import CHANNEL_ID, WAITING_CHANNEL, WAITING_EDIT, WAITING_URL
from generator_service import generate_post
from parser_service import parse_page
from telegram_utils import (
    edit_preview_message,
    publish_to_channel,
    send_preview,
    settings_keyboard,
)

LOGGER = logging.getLogger(__name__)
CHANNEL_USERNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{4,31}$")


def _extract_url(text: str) -> str | None:
    match = re.search(r"https?://\S+", text)
    if not match:
        return None
    return match.group(0).strip()


def _channel_display(channel_id: int | str) -> str:
    return str(channel_id)


def _get_target_channel(context: ContextTypes.DEFAULT_TYPE) -> int | str:
    value = context.user_data.get("target_channel_id")
    if isinstance(value, (int, str)):
        return value
    context.user_data["target_channel_id"] = CHANNEL_ID
    return CHANNEL_ID


def _normalize_channel_input(text: str) -> int | str | None:
    raw = text.strip()
    if not raw:
        return None

    if re.fullmatch(r"-?\d+", raw):
        return int(raw)

    if raw.startswith("@"): 
        username = raw[1:]
        if CHANNEL_USERNAME_RE.fullmatch(username):
            return f"@{username}"
        return None

    url_match = re.match(r"https?://t\.me/([A-Za-z][A-Za-z0-9_]{4,31})(?:$|[/?#])", raw)
    if url_match:
        return f"@{url_match.group(1)}"

    if CHANNEL_USERNAME_RE.fullmatch(raw):
        return f"@{raw}"

    return None


async def _is_user_channel_admin(
    context: ContextTypes.DEFAULT_TYPE,
    channel_id: int | str,
    user_id: int,
) -> bool | None:
    try:
        member = await context.bot.get_chat_member(chat_id=channel_id, user_id=user_id)
    except TelegramError:
        LOGGER.exception("Не удалось проверить права пользователя %s в канале %s", user_id, channel_id)
        return None

    return member.status in {"administrator", "creator"}


def _welcome_message(channel_id: int | str) -> str:
    return (
        "Привет! Я помогу быстро подготовить пост и опубликовать его в ваш Telegram-канал.\n\n"
        "Что я умею:\n"
        "1) Разбирать страницу по ссылке и вытаскивать полезные факты.\n"
        "2) Генерировать готовый черновик поста.\n"
        "3) Перегенерировать текст по кнопке.\n"
        "4) Вносить правки по вашей инструкции.\n"
        "5) Публиковать пост в выбранный канал.\n\n"
        f"Текущий канал публикации: {_channel_display(channel_id)}\n\n"
        "Как пользоваться:\n"
        "1) Отправьте ссылку на страницу.\n"
        "2) Дождитесь предпросмотра.\n"
        "3) Нажмите «Изменить», «Перегенерировать» или «Опубликовать».\n"
        "4) Если нужен другой канал, нажмите «Сменить канал публикации»."
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.effective_chat is None or update.message is None:
        return WAITING_URL

    if update.effective_chat.type != "private":
        await update.message.reply_text("Этот бот работает только в личных сообщениях.")
        return WAITING_URL

    target_channel = _get_target_channel(context)
    context.user_data.clear()
    context.user_data["target_channel_id"] = target_channel
    await update.message.reply_text(
        _welcome_message(target_channel),
        reply_markup=settings_keyboard(),
    )
    return WAITING_URL


async def request_channel_change(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.effective_chat is None:
        return WAITING_URL

    channel_id = _get_target_channel(context)
    text = (
        f"Текущий канал публикации: {_channel_display(channel_id)}\n\n"
        "Отправьте новый канал одним сообщением. Поддерживаются форматы:\n"
        "• @username\n"
        "• username\n"
        "• https://t.me/username\n"
        "• числовой id, например -1001234567890\n\n"
        "Чтобы отменить, отправьте: отмена"
    )
    if context.user_data.get("draft"):
        text += "\n\nПосле смены канала можно сразу нажать «Опубликовать» на последнем предпросмотре."

    if update.callback_query and update.callback_query.message:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text(text)
        return WAITING_CHANNEL

    if update.message:
        await update.message.reply_text(text)
        return WAITING_CHANNEL

    return WAITING_URL


async def apply_channel_change(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.effective_chat is None or update.message is None:
        return WAITING_CHANNEL

    if update.effective_chat.type != "private":
        await update.message.reply_text("Пожалуйста, используйте бота в личном чате.")
        return WAITING_CHANNEL

    raw_value = (update.message.text or "").strip()
    if not raw_value:
        await update.message.reply_text("Отправьте значение канала одним сообщением.")
        return WAITING_CHANNEL

    if raw_value.lower() in {"отмена", "cancel"}:
        await update.message.reply_text(
            f"Смену канала отменил. Текущий канал: {_channel_display(_get_target_channel(context))}."
        )
        return WAITING_URL

    normalized = _normalize_channel_input(raw_value)
    if normalized is None:
        await update.message.reply_text(
            "Не удалось распознать канал. Отправьте @username, username, "
            "ссылку https://t.me/username или числовой id вида -1001234567890."
        )
        return WAITING_CHANNEL

    context.user_data["target_channel_id"] = normalized
    if context.user_data.get("draft"):
        await update.message.reply_text(
            f"Канал обновлен: {_channel_display(normalized)}.\n"
            "Черновик уже готов: нажмите «Опубликовать» на последнем предпросмотре."
        )
    else:
        await update.message.reply_text(
            f"Канал обновлен: {_channel_display(normalized)}.\n"
            "Теперь отправьте ссылку на страницу для генерации поста."
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
    #update — объект с информацией о том что прислал пользователь (сообщение, нажатие кнопки и т.д.)
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

    target_channel = _get_target_channel(context)
    user = update.effective_user
    if user is None:
        await query.message.reply_text(
            "Не удалось определить пользователя. Попробуйте снова чуть позже."
        )
        return WAITING_URL

    is_admin = await _is_user_channel_admin(context, target_channel, user.id)
    print(f"Is admin: {is_admin}")
    if is_admin is None:
        await query.message.reply_text(
            "Не удалось проверить ваши права в выбранном канале. Проверьте, что бот добавлен в канал "
            "и назначен администратором, а затем попробуйте снова."
        )
        return WAITING_URL

    if not is_admin:
        await query.message.reply_text(
            "Публикация запрещена: только администратор выбранного канала может публиковать посты через бота."
        )
        return WAITING_URL

    try:
        await publish_to_channel(
            context=context,
            channel_id=target_channel,
            post_text=str(draft),
            image_url=context.user_data.get("image_url"),
        )
    except TelegramError:
        LOGGER.exception("Ошибка публикации в канал")
        await query.message.reply_text(
            "Не удалось опубликовать пост в выбранный канал. Проверьте, что бот добавлен в канал "
            "и назначен администратором с правом публикации сообщений."
        )
        return WAITING_URL

    await query.message.reply_text(
        f"Пост успешно опубликован в канал {_channel_display(target_channel)}."
    )
    return WAITING_URL


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    target_channel = _get_target_channel(context)
    if update.message:
        await update.message.reply_text(
            "Остановил текущий сценарий. Пришлите новую ссылку, когда будете готовы."
        )
    context.user_data.clear()
    context.user_data["target_channel_id"] = target_channel
    return WAITING_URL
