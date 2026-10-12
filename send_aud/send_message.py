

from __future__ import annotations

import logging
import os

import requests
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

API_ROOT = "https://api.telegram.org"
MAX_TEXT_CHARS = 4096  # Telegram: "1-4096 characters after entities parsing"
_PLACEHOLDER_MARKERS = ("PUT_YOUR", "<<", "your_token")


def send_message(text: str) -> bool:
    """Send `text` to the chat named by TELEGRAM_CHAT_ID.

    Returns True when Telegram accepted the message, False when the request or
    the API call failed (both are logged). Raises ValueError for text Telegram
    would reject regardless of the network, and RuntimeError when the bot token
    or chat id is missing or still a placeholder.
    """
    text = (text or "").strip()
    if not text:
        raise ValueError("text must not be empty")
    if len(text) > MAX_TEXT_CHARS:
        raise ValueError(
            f"text is {len(text)} characters; Telegram allows at most {MAX_TEXT_CHARS}"
        )

    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()
    for name, value in (("TELEGRAM_BOT_TOKEN", token), ("TELEGRAM_CHAT_ID", chat_id)):
        if not value or any(marker in value for marker in _PLACEHOLDER_MARKERS):
            raise RuntimeError(
                f"{name} is not set; copy dotenv_sample to .env and fill it in"
            )

    try:
        resp = requests.post(
            f"{API_ROOT}/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=30,
        )
    except requests.RequestException as exc:
        log.error("sendMessage request failed: %s", exc)
        return False

    try:
        body = resp.json()
        if not isinstance(body, dict):
            raise ValueError(f"expected a JSON object, got {type(body).__name__}")
    except ValueError as exc:
        log.error(
            "sendMessage returned an unusable body (HTTP %s): %s",
            resp.status_code,
            exc,
        )
        return False

    if resp.status_code != 200 or not body.get("ok"):
        log.error(
            "Telegram API error (HTTP %s): %s",
            resp.status_code,
            body.get("description"),
        )
        return False

    log.info("Sent message to chat %s", chat_id)
    return True


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    if len(sys.argv) != 2 or not sys.argv[1].strip():
        print('usage: python send_message.py "<text>"', file=sys.stderr)
        sys.exit(2)
    try:
        sys.exit(0 if send_message(sys.argv[1]) else 1)
    except (ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
