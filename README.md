# Post Generator Bot

## Русский

Этот проект — Telegram-бот для быстрого создания и публикации постов на основе статьи по ссылке. Пользователь отправляет URL в личный чат с ботом, бот извлекает заголовок, основной текст и подходящее изображение со страницы, затем передает материал в LLM (Groq) и формирует готовый черновик поста в формате Telegram Markdown.

После генерации бот отправляет предпросмотр с кнопками управления: публикация, перегенерация, ручная правка текста и смена канала публикации. Перед отправкой в канал бот проверяет, что пользователь является администратором выбранного канала, а сам бот имеет права на публикацию. Это снижает риск случайной публикации не тем пользователем.

Архитектура разделена на небольшие сервисы: обработчики Telegram-событий, парсинг веб-страниц, генерация текста через Groq и отдельные утилиты отправки/редактирования сообщений в Telegram. Такой подход упрощает поддержку и доработку проекта.

### Основные файлы

- `bot.py` — точка входа, запуск polling.
- `app_builder.py` — сборка `Application` и `ConversationHandler`.
- `bot_handlers.py` — сценарии бота: старт, обработка URL, правки, публикация, смена канала.
- `parser_service.py` — извлечение контента страницы и картинки (с fallback через `r.jina.ai`).
- `generator_service.py` — обращение к Groq API и генерация текста поста.
- `telegram_utils.py` — клавиатуры, предпросмотр, публикация, fallback при ошибках Telegram.
- `config.py` — переменные окружения, состояния диалога и системный prompt.

### Переменные окружения

Создайте файл `.env` в корне проекта:

```env
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
GROQ_API_KEY=your_groq_api_key
CHANNEL_ID=-1001234567890
```

`CHANNEL_ID` может быть числовым id (например `-100...`) или username канала.

### Запуск

```bash
pip install -r requirements.txt
python bot.py
```

---

## Deutsch

Dieses Projekt ist ein Telegram-Bot, der aus einem Artikel-Link schnell einen fertigen Kanalbeitrag erstellt. Der Nutzer sendet eine URL im privaten Chat, der Bot extrahiert Titel, Hauptinhalt und ein passendes Bild, und gibt diese Informationen an ein LLM (Groq) weiter, um einen strukturierten Entwurf im Telegram-Markdown-Format zu erzeugen.

Nach der Generierung zeigt der Bot eine Vorschau mit Steuerungsbuttons: veröffentlichen, neu generieren, manuell bearbeiten und Zielkanal wechseln. Vor der Veröffentlichung prüft der Bot, ob der Nutzer im gewählten Kanal Administrator ist und ob der Bot selbst Veröffentlichungsrechte besitzt. Dadurch wird das Risiko falscher oder unautorisierter Veröffentlichungen reduziert.

Die Architektur ist in kleine, klare Module aufgeteilt: Telegram-Handler für Dialoglogik, ein Parser-Service für Webseiteninhalt, ein Generator-Service für Groq sowie Utilities für Nachrichtenversand und Vorschauverwaltung. Das erleichtert Wartung, Tests und spätere Erweiterungen.

### Umgebungsvariablen

Erstellen Sie eine `.env`-Datei im Projektverzeichnis:

```env
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
GROQ_API_KEY=your_groq_api_key
CHANNEL_ID=-1001234567890
```

### Start

```bash
pip install -r requirements.txt
python bot.py
```

---

## English

This project is a Telegram bot that creates publish-ready channel posts from a webpage URL. A user sends a link in a private chat, the bot extracts the page title, core text, and a suitable image, and then passes that material to an LLM (Groq) to generate a concise Telegram Markdown draft.

After generation, the bot sends an interactive preview with actions to publish, regenerate, edit the text, or switch the target channel. Before publishing, it verifies that the user is an admin of the selected channel and that the bot has posting rights. This helps prevent unauthorized or accidental publishing.

The codebase is split into focused modules: Telegram conversation handlers, a page parsing service, a Groq generation service, and Telegram utility helpers for previews and robust message/image sending. This modular design makes the project easier to maintain and extend.

### Environment variables

Create a `.env` file in the project root:

```env
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
GROQ_API_KEY=your_groq_api_key
CHANNEL_ID=-1001234567890
```

### Run

```bash
pip install -r requirements.txt
python bot.py
```
