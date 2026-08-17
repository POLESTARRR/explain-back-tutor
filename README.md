# Explain-Back Tutor

A Telegram study bot built on the Feynman technique: you don't understand
something until you can explain it simply in your own words. You pick a
concept, explain it in text, and the bot grades your explanation against
your own notes — telling you what you got right, where you were vague, and
what you got wrong or left out.

Unlike a flashcard app that tests your *recall*, this grades your
*explanation* — a much harder, more honest test of real understanding.

## How it works

1. You load your notes once (a markdown file, concepts split by `##`
   headings) into the concept store.
2. In Telegram, you send a concept name — e.g. `inflation`.
3. The bot says "explain it in your own words" and does NOT show you the
   notes (that would defeat the point).
4. You type your explanation.
5. The bot grades it strictly against your source notes and replies with
   structured feedback + a score out of 10.
6. It tracks your score per concept over time, so `/weak` shows the
   concepts you keep fumbling — your real study priorities.

## The simple way to run it: no n8n needed

This project runs as ONE program — `src/bot.py`. It talks to Telegram
directly by polling ("any new messages?" on a loop), so there's no n8n, no
web server, and nothing outside needs to reach your computer. It works fine
behind home wifi with zero network setup.

(There's also an optional `server.py` + n8n workflow included, for if you
ever specifically want to route this through n8n. You can ignore both files
entirely for the simple path. Both share the exact same tested conversation
logic in `conversation.py`.)

## Why it's free

- **Grading**: `claude -p` (headless Claude Code) via your Claude
  subscription — NOT the paid per-token API.
- **Interface**: Telegram Bot API — free.
- **Storage**: plain JSON files — no database.

Honest notes:
- This is **interactive**, so `bot.py` needs to be running for the bot to
  reply. Run it on your own machine while studying, or on a free always-on
  cloud VM (e.g. Oracle Cloud free tier) if you want it up 24/7. When it's
  not running, messages just queue and get answered next time it starts.
- Every explanation you send is one `claude -p` call on your subscription.
  Perfect for you (and a few friends) studying; not built to serve a whole
  class at once without a paid API key.

## Commands in the bot

- Send any concept name — start explaining that concept
- `/list` — see all loaded concepts
- `/weak` — see concepts with your lowest average scores
- `/cancel` — abandon the explanation you're mid-way through
- `/help` — usage

## Setup (the simple, no-n8n path)

### 1. Authenticate Claude Code for headless use
```
claude setup-token
claude -p "say hello"     # must print a reply before continuing
```
Put the token in `.env` as `CLAUDE_CODE_OAUTH_TOKEN`.

### 2. Create your Telegram bot
- Message @BotFather → `/newbot` → follow prompts → copy the token.
- Put it in `.env` as `TELEGRAM_BOT_TOKEN`.
- (For a personal tutor you just DM the bot directly — no channel needed.)

### 3. Install and load your notes
```
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then fill in the two tokens above
python src/load_notes.py sample_notes.md    # try the 3 sample concepts first
```
Later, load your real notes the same way. Each concept starts with a
`## Concept Name` heading; everything under it is the source text you'll be
graded against. Add `--replace` to overwrite instead of merge.

### 4. Run the bot
```
python src/bot.py
```
You'll see "Explain-back tutor is running." Now open Telegram, find your
bot, and send it `/start`. Send `inflation`, then explain it — you'll get
graded. Press Ctrl+C in the terminal to stop the bot.

That's the whole thing. No n8n, no server, no self-hosting platform.

## Running the tests

```
pip install -r requirements.txt
pytest -q
```
50 tests cover the concept store, progress tracking, the conversation state
machine, and the grader's JSON parsing/validation — all with the actual
`claude -p` call mocked out, so the suite runs in well under a second with
no network or subscription usage. The grading pipeline itself was also
verified end-to-end against a real `claude -p` call during development.

## Files

- `src/bot.py` — the runnable bot (this is what you start)
- `src/conversation.py` — the shared conversation state machine (used by both bot.py and server.py)
- `src/concepts.py` — loads/searches your notes
- `src/grader.py` — grades your explanation via `claude -p`
- `src/progress.py` — tracks your scores per concept over time
- `src/load_notes.py` — one-time notes loader
- `sample_notes.md` — 3 ready-made concepts to test with
- `src/server.py` + `n8n-workflows/` — OPTIONAL n8n path, ignore for simple use
- `tests/` — unit tests for everything except the live `claude -p` call itself

## What makes this worth building (and not generic)

Most study bots quiz you — question in, did-you-remember out. This inverts
it: you produce the explanation, and the grading is grounded strictly in
your own source, so it distinguishes "you're vague here" from "you're wrong
here" from "the notes don't cover that." That grounding discipline —
separating unsupported from contradicted — is the same principle behind a
good RAG eval, applied to teaching yourself.
