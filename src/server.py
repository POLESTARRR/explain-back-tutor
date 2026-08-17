#!/usr/bin/env python3
"""OPTIONAL n8n-friendly HTTP path. Ignore this entirely if you're using bot.py.

Exposes a single endpoint that reuses the exact same conversation.py logic as the
polling bot, so grading behavior is identical either way:

    POST /webhook
    body: {"chat_id": "123", "text": "inflation"}       -> {"reply": "..."}
    body: <a raw Telegram Update JSON object>            -> {"reply": "..."} (or 204 if not a text message)

Pair this with n8n-workflows/explain-back-tutor.json, which wires a Telegram
Trigger node -> HTTP Request node (calling this endpoint) -> Telegram node (sending
the reply back). Run with: python src/server.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from flask import Flask, jsonify, request

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.concepts import ConceptStore  # noqa: E402
from src.conversation import ConversationManager  # noqa: E402
from src.progress import ProgressStore  # noqa: E402

app = Flask(__name__)
convo = ConversationManager(ConceptStore(), ProgressStore())


def _extract_chat_and_text(body: dict) -> tuple[str, str] | None:
    """Accepts either a plain {"chat_id","text"} payload or a raw Telegram Update."""
    if "chat_id" in body and "text" in body:
        return str(body["chat_id"]), str(body["text"])

    message = body.get("message")
    if message and "text" in message:
        chat_id = message.get("chat", {}).get("id")
        if chat_id is not None:
            return str(chat_id), str(message["text"])

    return None


@app.post("/webhook")
def webhook():
    body = request.get_json(silent=True) or {}
    extracted = _extract_chat_and_text(body)
    if extracted is None:
        return "", 204  # e.g. a non-text Telegram update (photo, sticker, ...) — nothing to grade

    chat_id, text = extracted
    reply = convo.handle_message(chat_id, text)
    return jsonify({"reply": reply})


@app.get("/health")
def health():
    return jsonify({"status": "ok", "concepts_loaded": len(convo.concepts)})


def main() -> int:
    port = int(os.environ.get("PORT", "8000"))
    app.run(host="0.0.0.0", port=port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
