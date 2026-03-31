import asyncio

from app_builder import build_application


def main() -> None:
    app = build_application()

    # Python 3.14 no longer creates a default event loop in MainThread.
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    app.run_polling()


if __name__ == "__main__":
    main()
