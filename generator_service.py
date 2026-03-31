from typing import Any

from groq import Groq

from config import GROQ_API_KEY, GROQ_MODEL, SYSTEM_PROMPT

GROQ_CLIENT = Groq(api_key=GROQ_API_KEY)


def _build_generation_prompt(parsed: dict[str, Any], feedback: str | None = None) -> str:
    prompt = (
        f"Ссылка: {parsed['url']}\n"
        f"Заголовок: {parsed['title']}\n\n"
        "Материал страницы (сокращенный):\n"
        f"{parsed['text']}\n"
    )

    if feedback:
        prompt += (
            "\nДополнительные правки от автора. "
            "Учти их при переписывании:\n"
            f"{feedback.strip()}\n"
        )

    return prompt


def generate_post(parsed: dict[str, Any], feedback: str | None = None) -> str:
    completion = GROQ_CLIENT.chat.completions.create(
        model=GROQ_MODEL,
        temperature=0.9,
        max_tokens=900,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _build_generation_prompt(parsed, feedback)},
        ],
    )

    content = completion.choices[0].message.content if completion.choices else None
    if not content or not content.strip():
        raise RuntimeError("Groq вернул пустой ответ")

    return content.strip()
