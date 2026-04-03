import logging
import os
import re
import warnings

from dotenv import load_dotenv
from telegram.warnings import PTBUserWarning

WAITING_URL, WAITING_EDIT, WAITING_CHANNEL = range(3)
MAX_SOURCE_TEXT_LEN = 3000
GROQ_MODEL = "llama-3.3-70b-versatile"

SYSTEM_PROMPT = """
Ты опытный автор Telegram-постов.

Задача: на основе исходного материала написать пост для Telegram-канала.
Жесткие требования:
1) Объем: от 30 до 50 слов.
2) Пиши только по фактам из исходного материала, без выдумок.
3) Никакой воды, кликбейта и цепляющих вступлений. Сразу переходи к сути.
4) Делай красивое и удобное оформление: короткие абзацы по 1-3 предложения с пустой строкой между абзацами.
5) Используй форматирование Telegram Markdown (например, *жирный*, _курсив_) только там, где это действительно улучшает читаемость.
6) Тон нейтральный и информативный, без лишней эмоциональности.
7) Эмодзи не обязательны. Если уместно, используй не более 1 эмодзи.

Верни только готовый текст поста без комментариев.
""".strip()

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)

warnings.filterwarnings(
    "ignore",
    message=r"If 'per_message=False', 'CallbackQueryHandler' will not be tracked for every message.*",
    category=PTBUserWarning,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(dotenv_path=os.path.join(BASE_DIR, ".env"))

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
CHANNEL_ID_RAW = os.getenv("CHANNEL_ID", "").strip()

if not TELEGRAM_BOT_TOKEN or not GROQ_API_KEY or not CHANNEL_ID_RAW:
    raise RuntimeError(
        "Отсутствуют обязательные переменные окружения: TELEGRAM_BOT_TOKEN, GROQ_API_KEY, CHANNEL_ID"
    )

CHANNEL_ID: int | str
if re.fullmatch(r"-?\d+", CHANNEL_ID_RAW):
    CHANNEL_ID = int(CHANNEL_ID_RAW)
else:
    CHANNEL_ID = CHANNEL_ID_RAW
