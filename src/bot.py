#!/usr/bin/env python3
"""The runnable Explain-Back Tutor bot. Polls Telegram, no server/n8n required.

Run with: python src/bot.py
"""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.concepts import ConceptStore  # noqa: E402
from src.conversation import ConversationManager  # noqa: E402
from src.progress import ProgressStore  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("explain-back-tutor")

API_BASE = "https://api.telegram.org/bot{token}"
POLL_TIMEOUT_SECONDS = 30  # long-poll window Telegram holds the request open for
HTTP_TIMEOUT_SECONDS = POLL_TIMEOUT_SECONDS + 10
MAX_MESSAGE_LENGTH = 4000  # stay under Telegram's 4096-char limit with margin
RETRY_BACKOFF_SECONDS = 5


class TelegramClient:
    def __init__(self, token: str):
        self.base_url = API_BASE.format(token=token)

    def get_updates(self, offset: int | None) -> list[dict]:
        params = {"timeout": POLL_TIMEOUT_SECONDS}
        if offset is not None:
            params["offset"] = offset
        resp = requests.get(
            f"{self.base_url}/getUpdates", params=params, timeout=HTTP_TIMEOUT_SECONDS
        )
        resp.raise_for_status()
        payload = resp.json()
        if not payload.get("ok"):
            raise RuntimeError(f"getUpdates failed: {payload}")
        return payload["result"]

    def send_message(self, chat_id: int | str, text: str) -> None:
        for i in range(0, len(text), MAX_MESSAGE_LENGTH):
            chunk = text[i:i + MAX_MESSAGE_LENGTH]
            resp = requests.post(
                f"{self.base_url}/sendMessage",
                json={"chat_id": chat_id, "text": chunk},
                timeout=HTTP_TIMEOUT_SECONDS,
            )
            if not resp.ok:
                log.error("sendMessage failed (%s): %s", resp.status_code, resp.text[:300])


def build_conversation_manager() -> ConversationManager:
    return ConversationManager(ConceptStore(), ProgressStore())


def run(client: TelegramClient, convo: ConversationManager) -> None:
    offset: int | None = None
    log.info("Explain-back tutor is running.")

    while True:
        try:
            updates = client.get_updates(offset)
        except requests.RequestException as exc:
            log.warning("Network error polling Telegram (%s), retrying in %ss", exc, RETRY_BACKOFF_SECONDS)
            time.sleep(RETRY_BACKOFF_SECONDS)
            continue
        except RuntimeError as exc:
            log.error("Telegram API error: %s", exc)
            time.sleep(RETRY_BACKOFF_SECONDS)
            continue

        for update in updates:
            offset = update["update_id"] + 1
            message = update.get("message")
            if not message or "text" not in message:
                continue

            chat_id = message["chat"]["id"]
            text = message["text"]
            log.info("chat=%s: %s", chat_id, text[:120])

            try:
                reply = convo.handle_message(chat_id, text)
            except Exception:  # noqa: BLE001 - one bad message must not kill the bot
                log.exception("Unhandled error handling message from chat %s", chat_id)
                reply = "Something went wrong on my end handling that — try again."

            client.send_message(chat_id, reply)


def main() -> int:
    load_dotenv()
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("TELEGRAM_BOT_TOKEN is not set. Put it in .env (see .env.example).", file=sys.stderr)
        return 1

    client = TelegramClient(token)
    convo = build_conversation_manager()

    try:
        run(client, convo)
    except KeyboardInterrupt:
        log.info("Stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
